# Standard-library helpers
import asyncio   # MCP servers talk over async stdio; we need an event loop
import json      # parse mcp.json
import os        # read environment variables (for ${VAR} substitution)
from pathlib import Path  # cross-platform file paths

# `langchain-mcp-adapters` is the glue: it speaks MCP to N servers and
# returns each remote tool wrapped as a LangChain BaseTool the agent can call.
from langchain_mcp_adapters.client import MultiServerMCPClient

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


def load_mcp_tools():
    """Spawn every MCP server in mcp.json and return the discovered tools."""
    cfg = _load_config()
    # MultiServerMCPClient forks each server as a subprocess, opens stdio
    # pipes, does the MCP handshake, and asks each server for its tool list.
    client = MultiServerMCPClient(cfg)
    # `get_tools()` is async (it awaits handshakes); asyncio.run drives it
    # from our synchronous Streamlit thread.
    tools = asyncio.run(client.get_tools())
    return tools, cfg
