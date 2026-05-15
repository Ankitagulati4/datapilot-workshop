"""DataPilot Chat Agent.

A single LangGraph ReAct agent. It does NOT define any tools of its own —
it gets them from MCP servers (see mcp_clients.py).

Pattern:
  question --> LLM picks tool(s) --> call MCP --> use result --> answer

The trace of every tool call is captured for the UI's "Show steps" expander.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import nest_asyncio
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from solution.app.guardrails import GuardrailError, validate_and_fix
from solution.app.llm import get_llm

nest_asyncio.apply()

SYSTEM_PROMPT = """You are DataPilot, an analytics colleague for the ShopFlow team.

You answer business questions about the ShopFlow SQLite database using the tools below.

Schema (read once, then trust it):
  customers(customer_id, name, email, country, signup_date, segment)
  products(product_id, name, category, price, cost, active)
  orders(order_id, customer_id, order_date, channel, status, total_amount)
  order_items(order_id, product_id, quantity, unit_price)
  returns(...), support_tickets(...), web_sessions(...)

Workflow:
  1. Skim schema with list_tables/describe_table only if you're uncertain.
  2. Write ONE SQL SELECT and call read_query. Always alias aggregates.
     For 'category revenue' join order_items → products and SUM(quantity*unit_price).
     For time series use date(order_date) or strftime('%Y-%m', order_date).
  3. For data-quality questions, pick a check_* tool instead of writing SQL.
  4. As soon as you have the numbers, STOP calling tools and answer.
  5. Final answer: max 3 sentences. Include the actual numbers.

Never call the same tool with the same arguments twice. Never invent numbers."""

# Tools the agent is allowed to use. Anything not on this list is hidden,
# so the model literally cannot pick `write_query` or `drop` anything.
SAFE_TOOL_NAMES = {
    "list_tables",
    "describe_table",
    "read_query",
    "check_freshness",
    "check_nulls",
    "check_duplicates",
    "count_rows",
    "search_docs",
    "list_docs",
}


@dataclass
class TurnResult:
    answer: str = ""
    error: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: int = 0


def _wrap_read_query(read_query_tool):
    """Module 03: wrap the SQLite MCP `read_query` tool input with our guardrail.

    The model can call read_query freely; if its SQL is dangerous, the
    guardrail raises before the call ever leaves our process.
    """
    original = read_query_tool.coroutine

    async def guarded(query: str, **kw):
        try:
            safe = validate_and_fix(query)
        except GuardrailError as e:
            # The MCP tool uses response_format='content_and_artifact', so
            # we must return a (content, artifact) tuple. None artifact is fine.
            return f"GUARDRAIL BLOCK: {e}", None
        return await original(query=safe, **kw)

    read_query_tool.coroutine = guarded
    return read_query_tool


def filter_and_guard(tools: list) -> list:
    """Keep only safe tools and wrap read_query with the SQL guardrail."""
    kept = [t for t in tools if t.name in SAFE_TOOL_NAMES]
    for t in kept:
        if t.name == "read_query":
            _wrap_read_query(t)
    return kept


class ChatAgent:
    """Stateful chat agent. Holds conversation history across turns."""

    def __init__(self, tools: list) -> None:
        self.llm = get_llm(temperature=0.0)
        self.tools = tools
        self.graph = create_react_agent(self.llm, self.tools, prompt=SYSTEM_PROMPT)
        self.history: list = []   # accumulated Human/AI messages

    def reset(self) -> None:
        self.history = []

    def ask(self, question: str) -> TurnResult:
        t0 = time.perf_counter()
        out = TurnResult()
        try:
            messages = list(self.history) + [HumanMessage(content=question)]
            state = asyncio.run(self.graph.ainvoke(
                {"messages": messages},
                config={"recursion_limit": 25},
            ))
            new_msgs = state["messages"][len(messages):]   # only new ones from this turn

            # Walk new messages: collect tool calls and final assistant text
            pending: dict[str, dict[str, Any]] = {}
            final_text = ""
            for msg in new_msgs:
                if isinstance(msg, AIMessage):
                    if msg.content:
                        final_text = (
                            msg.content if isinstance(msg.content, str)
                            else "".join(p.get("text", "") for p in msg.content if isinstance(p, dict))
                        )
                    for tc in (msg.tool_calls or []):
                        pending[tc["id"]] = {
                            "tool": tc["name"], "input": tc["args"], "output": "",
                        }
                elif isinstance(msg, ToolMessage):
                    if msg.tool_call_id in pending:
                        pending[msg.tool_call_id]["output"] = str(msg.content)[:600]
                    else:
                        pending[msg.tool_call_id or f"orphan_{len(pending)}"] = {
                            "tool": msg.name or "?", "input": {},
                            "output": str(msg.content)[:600],
                        }
                    out.tool_calls.append(pending[msg.tool_call_id])

            out.answer = final_text.strip() or "(no answer)"
            self.history = messages + [AIMessage(content=out.answer)]
        except Exception as e:
            out.error = f"{type(e).__name__}: {e}"
        out.latency_ms = int((time.perf_counter() - t0) * 1000)
        return out
