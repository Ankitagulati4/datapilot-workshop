"""DataPilot RAG MCP Server: semantic search over docs/.

Same FastMCP pattern as dq_server.py -- subprocess + stdio + @mcp.tool() --
but the tools wrap a vector store instead of a SQL database.
"""
import contextlib
import os
import sys
from pathlib import Path

# --- stdout hygiene (CRITICAL for MCP over stdio) -------------------------
# Silence ChromaDB telemetry before importing it — ANY stray write to stdout
# corrupts the JSON-RPC stream this server speaks over stdio.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")

# Redirect stdout to stderr while chromadb (and its bundled onnxruntime)
# imports — same reason: keep stdout MCP-clean. Otherwise the parent process
# receives garbage before our first JSON message and aborts the connection.
with contextlib.redirect_stdout(sys.stderr):
    import chromadb

from mcp.server.fastmcp import FastMCP

# Locate the index built by build_rag_index.py.
ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = ROOT / "data" / "rag.chroma"
COLLECTION = "shopflow_docs"

# Server name visible to MCP clients (chat agent, Claude Desktop, etc.).
mcp = FastMCP("datapilot-rag")

# Lazy-init chromadb on first tool call. Reasons:
#   1. Faster startup -> less chance of client handshake timeout.
#   2. Avoids any stdout writes during module import.
# `_coll` is module-level singleton; built once, reused for every call.
_coll = None
def _coll_ready():
    global _coll
    if _coll is None:
        with contextlib.redirect_stdout(sys.stderr):
            client = chromadb.PersistentClient(path=str(INDEX_DIR))
            _coll = client.get_collection(COLLECTION)
    return _coll


@mcp.tool()
def search_docs(query: str, k: int = 3) -> str:
    """Semantic search over ShopFlow documentation.

    Use when the user asks about *concepts*, *policies*, or *definitions*
    (e.g. 'what does VIP mean?', 'returns policy', 'channel definitions')
    rather than database facts.
    """
    # Clamp k to a safe range -- the LLM occasionally passes nonsense values.
    k = max(1, min(int(k), 5))
    # `query_texts` triggers Chroma to embed the query with the SAME model used
    # at index time. n_results = how many top-k matches to return.
    res = _coll_ready().query(query_texts=[query], n_results=k)
    docs = res.get("documents", [[]])[0]   # ranked list of doc bodies
    metas = res.get("metadatas", [[]])[0]  # parallel list of {title, file}
    if not docs:
        return "No matching documents found."
    # Format hits as readable text the LLM can quote in its final answer.
    out = []
    for doc, meta in zip(docs, metas):
        title = (meta or {}).get("title", "(untitled)")
        out.append(f"--- {title} ---\n{doc.strip()}")
    return "\n\n".join(out)


@mcp.tool()
def list_docs() -> str:
    """List the titles of all documents available for RAG search."""
    # `get(include=["metadatas"])` returns every document's metadata
    # without paying the cost of fetching the full text.
    res = _coll_ready().get(include=["metadatas"])
    metas = res.get("metadatas", []) or []
    lines = [f"- {m.get('title', '?')} ({m.get('file', '?')})" for m in metas]
    return "Available documents:\n" + "\n".join(lines)


if __name__ == "__main__":
    # Default transport is stdio -- the chat agent forks us and pipes JSON-RPC
    # over our stdin/stdout. Nothing else should ever write to stdout.
    mcp.run()