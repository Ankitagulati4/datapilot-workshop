# Standard-library helpers
import asyncio     # MCP servers talk over async stdio; we need an event loop
import json        # parse mcp.json
import os          # read environment variables (for ${VAR} substitution)
import threading   # run ONE long-lived event loop in a background thread
from contextlib import AsyncExitStack  # keep N sessions open together
from pathlib import Path  # cross-platform file paths

# `langchain-mcp-adapters` is the glue: it speaks MCP to N servers and
# returns each remote tool wrapped as a LangChain BaseTool the agent can call.
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools as _load_tools_from_session

# config/ is a sibling of THIS file (student/app/config/mcp.json).
# Using __file__ makes the path correct no matter where Streamlit is launched from.
CONFIG = Path(__file__).parent / "config" / "mcp.json"


def _load_config() -> dict:
    """Read mcp.json and replace every ${VAR} placeholder with the env value."""
    raw = CONFIG.read_text()
    # expand ${VAR} from environment.
    # On Windows the value (e.g. C:\Users\...) contains backslashes;
    # JSON requires them escaped (\\), so we double-up before substituting.
    for k, v in os.environ.items():
        raw = raw.replace(f"${{{k}}}", v.replace("\\", "\\\\"))
    # Parse the substituted text and return only the servers dict.
    return json.loads(raw)["mcpServers"]


# --- ONE persistent event loop for the whole app ---------------------------
# Why: MCP stdio servers are subprocesses reached over an asyncio session.
# If we spawned a new server (or a new event loop) on every tool call, each
# call would pay a full process-spawn + MCP handshake (~3 seconds on Windows)
# and could intermittently deadlock. Instead we start ONE background event
# loop, open the server sessions ONCE, and keep them alive for the app's
# lifetime. Every later tool call is then a fast round-trip (~20 ms).
_loop: asyncio.AbstractEventLoop | None = None
_ready = threading.Event()   # set once the sessions are open (or failed)
_tools: list | None = None
_cfg: dict | None = None
_error: BaseException | None = None


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """Start (once) a background thread running a forever event loop."""
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop.run_forever, daemon=True).start()
    return _loop


def run_sync(coro):
    """Run a coroutine on the persistent loop and block for its result.

    The chat agent uses this to drive `graph.ainvoke(...)` so the graph AND
    the MCP tool sessions all live on the SAME loop (mixing loops hangs).
    """
    return asyncio.run_coroutine_threadsafe(coro, _ensure_loop()).result()


async def _server_main():
    """Long-lived task: open a session per server, publish the tools, then
    stay alive forever so the sessions (and their subprocesses) don't close.

    The sessions' background read/write tasks are children of THIS task, so
    this task must never return -- if it did, those children get cancelled
    and every later tool call fails with 'Connection closed'.
    """
    global _tools, _cfg, _error
    try:
        cfg = _load_config()
        client = MultiServerMCPClient(cfg)
        async with AsyncExitStack() as stack:
            tools: list = []
            for name in cfg:
                # Forks the server subprocess + MCP handshake ONCE.
                session = await stack.enter_async_context(client.session(name))
                tools.extend(await _load_tools_from_session(session))
            _tools, _cfg = tools, cfg
            _ready.set()                 # signal load_mcp_tools() it can return
            await asyncio.Event().wait()  # park here forever, keeping sessions open
    except BaseException as e:           # noqa: BLE001 - report boot failures
        _error = e
        _ready.set()


def load_mcp_tools():
    """Spawn every MCP server in mcp.json ONCE and return the discovered tools.

    Returns (tools, cfg). Idempotent: repeated calls reuse the same live
    sessions instead of spawning the servers again.
    """
    if not _ready.is_set():
        # Kick off the forever-running session owner on the background loop.
        asyncio.run_coroutine_threadsafe(_server_main(), _ensure_loop())
        _ready.wait(timeout=60)          # block until sessions are ready
    if _error is not None:
        raise _error
    return _tools, _cfg