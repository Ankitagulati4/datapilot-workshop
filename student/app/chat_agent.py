"""DataPilot chat agent — Module 03: tool allow-list + SQL guardrail."""
import time
from dataclasses import dataclass, field

# LangGraph gives us a ready-made ReAct loop (reason -> act -> observe -> ...)
from langgraph.prebuilt import create_react_agent
# In-memory store for conversation state (per thread_id). Survives one app run.
from langgraph.checkpoint.memory import InMemorySaver
# LangChain message classes the agent reasons over.
from langchain_core.messages import HumanMessage, SystemMessage
# Tools to cap how much history we send to the LLM each turn (see pre_model_hook).
from langchain_core.messages.utils import trim_messages, count_tokens_approximately

from app.llm import get_llm
# `run_sync` drives coroutines on the ONE persistent MCP event loop so the
# graph and the long-lived tool sessions all share the same loop.
from app.mcp_clients import load_mcp_tools, run_sync
# NEW in Module 03: the SQL firewall.
from app.guardrails import validate_and_fix, GuardrailError

SYSTEM = """You are DataPilot, a careful data analyst.
- Use list_tables / describe_table to discover schema before SELECTing.
- Always answer in 1-2 sentences plus a short table when relevant.
- Never invent columns. If a tool errors, fix and retry once.
"""

# Allow-list of tool names the LLM is even ALLOWED to see. Anything not here
# (e.g. write_query, create_table, append_insight) is hidden -> the model
# literally CAN'T pick it. Defence in depth alongside the SQL guardrail.
SAFE = {"read_query", "list_tables", "describe_table"}

# Free Groq tiers cap requests at ~8000 tokens/minute. The agent's memory keeps
# the WHOLE conversation (including big schema dumps + query rows), and re-sends
# it every turn -> the payload snowballs past the limit (HTTP 413). This hook
# runs right before each LLM call and trims the messages sent to the model down
# to the most recent ~3000 tokens. It returns `llm_input_messages`, so ONLY the
# LLM's view is trimmed -- the full history stays in state for the UI trace.
def _trim_history(state):
    trimmed = trim_messages(
        state["messages"],
        max_tokens=3000,                       # comfortably under the 8000 TPM cap
        strategy="last",                       # keep the most RECENT messages
        token_counter=count_tokens_approximately,
        start_on="human",                      # never begin on an orphan tool/ai msg
        allow_partial=False,
    )
    return {"llm_input_messages": trimmed}


@dataclass
class TurnResult:
    """Plain-data container for one chat turn. Easy for the UI to render."""
    answer: str
    tool_calls: list = field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None


def _wrap_read_query(tool):
    """Wrap the MCP read_query tool's coroutine with the SQL guardrail.

    The model can call read_query freely; if its SQL is dangerous, the
    guardrail raises BEFORE the call ever leaves our process. From the
    LLM's perspective the tool just returned an error message it can
    react to and retry with safer SQL.
    """
    # Keep a reference to the ORIGINAL async impl -- we'll delegate to it
    # only after validation succeeds.
    original = tool.coroutine

    async def guarded(query: str, _orig=original, **kw):
        try:
            # Run the SQL through the firewall first.
            safe = validate_and_fix(query)
        except GuardrailError as e:
            # mcp-server-sqlite's read_query uses content_and_artifact
            # response shape -> must return a (content, artifact) tuple.
            # Returning (instead of raising) lets the LLM see the rejection
            # and try a corrected query on the next loop iteration.
            return f"GUARDRAIL BLOCK: {e}", None
        # SQL is clean -> forward to the real MCP tool.
        return await _orig(query=safe, **kw)

    # Monkey-patch the coroutine in place. The tool object identity is
    # unchanged, so any existing LangChain bindings stay valid.
    tool.coroutine = guarded
    return tool


class ChatAgent:
    """One agent instance per Streamlit session. Holds tools + memory."""

    def __init__(self):
        # 1. Spawn MCP servers ONCE.
        self.tools, _ = load_mcp_tools()

        # 2. Drop dangerous tools so the model can't even SEE them.
        #    Sidebar tools count will drop from 6 to 3.
        self.tools = [t for t in self.tools if t.name in SAFE]

        # 3. For the one tool that CAN touch the DB, install the guardrail.
        for t in self.tools:
            if t.name == "read_query":
                _wrap_read_query(t)

        # 4. Usual setup -- LLM, memory, graph.
        self.llm = get_llm()
        self.memory = InMemorySaver()
        self.graph = create_react_agent(
            self.llm, self.tools,
            checkpointer=self.memory,
            prompt=SystemMessage(SYSTEM),
            pre_model_hook=_trim_history,
        )
        self.thread = {"configurable": {"thread_id": "main"}}
        # How many messages we've already reported. InMemorySaver returns the
        # FULL history every turn, so we slice off only THIS turn's new
        # messages -- otherwise tool-call counts accumulate and the UI would
        # render a stale table from an earlier question.
        self._processed = 0

    def ask(self, q: str) -> TurnResult:
        """Run one reason-act loop for the user's question."""
        t0 = time.time()
        try:
            # MCP tools are async-only (StructuredTool has no sync impl).
            # Drive the graph on the SAME persistent loop that owns the MCP
            # sessions (run_sync blocks until the turn completes). Reusing one
            # loop keeps the servers alive between turns -> fast, no hangs.
            state = run_sync(self.graph.ainvoke(
                {"messages": [HumanMessage(q)]}, self.thread))

            # InMemorySaver returns the ENTIRE conversation. Only walk the
            # messages appended during THIS turn so the trace + table reflect
            # the current question, not a previous one.
            msgs = state["messages"]
            new_msgs = msgs[self._processed:]
            self._processed = len(msgs)

            # Walk this turn's messages and pair each tool call with its output
            # so the UI can show "this tool was called with these args, result was X".
            calls = []
            for m in new_msgs:
                if hasattr(m, "tool_calls") and m.tool_calls:
                    for tc in m.tool_calls:
                        calls.append({"tool": tc["name"], "input": tc["args"], "output": ""})
                if m.__class__.__name__ == "ToolMessage" and calls:
                    calls[-1]["output"] = m.content

            return TurnResult(
                answer=msgs[-1].content,
                tool_calls=calls,
                latency_ms=int((time.time() - t0) * 1000),
            )
        except Exception as e:
            # Surface ANY failure in the UI instead of crashing Streamlit.
            return TurnResult(answer="", error=f"{type(e).__name__}: {e}",
                              latency_ms=int((time.time() - t0) * 1000))