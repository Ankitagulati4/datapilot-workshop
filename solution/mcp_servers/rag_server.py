"""DataPilot RAG MCP Server.

A second MCP server that exposes 2 semantic-search tools backed by a
ChromaDB vector index of `docs/*.md`.

Build the index first:
    python solution/mcp_servers/build_rag_index.py

Run standalone:
    python solution/mcp_servers/rag_server.py

Same FastMCP pattern as `dq_server.py` — this is the "second MCP server"
lesson in Module 09. Different domain (semantic search vs SQL), same
shape: subprocess + stdio + @mcp.tool() decorator.
"""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

# Silence ChromaDB telemetry before importing it -- ANY stray write to stdout
# corrupts the JSON-RPC stream this server speaks over stdio.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")

# Redirect stdout to stderr for the ENTIRE chromadb import + init path.
# chromadb (and its bundled onnxruntime) prints status to stdout on first
# load, which would otherwise corrupt the JSON-RPC stream.
with contextlib.redirect_stdout(sys.stderr):
    import chromadb

from mcp.server.fastmcp import FastMCP

_REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = _REPO_ROOT / "data" / "rag.chroma"
COLLECTION = "shopflow_docs"

if not INDEX_DIR.exists():
    raise FileNotFoundError(
        f"RAG index not found at {INDEX_DIR}. "
        "Run: python solution/mcp_servers/build_rag_index.py"
    )

mcp = FastMCP("datapilot-rag")

# Lazy-init chromadb on first tool call. Doing it eagerly at import time
# can write to stdout (which corrupts the MCP stdio JSON-RPC stream) and
# also makes server startup slower than the client's handshake timeout.
_coll = None


def _get_coll():
    global _coll
    if _coll is None:
        with contextlib.redirect_stdout(sys.stderr):
            client = chromadb.PersistentClient(path=str(INDEX_DIR))
            _coll = client.get_collection(COLLECTION)
    return _coll


@mcp.tool()
def search_docs(query: str, k: int = 3) -> str:
    """Semantic search over ShopFlow documentation.

    Use this when the user asks about *concepts*, *policies*, or
    *definitions* rather than facts in the database. Examples:
    "what does VIP segment mean?", "returns policy", "channel definitions".

    Returns the top `k` most relevant document excerpts joined by separators.
    """
    k = max(1, min(int(k), 5))
    res = _get_coll().query(query_texts=[query], n_results=k)
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    if not docs:
        return "No matching documents found."
    parts = []
    for doc, meta in zip(docs, metas):
        title = (meta or {}).get("title", "(untitled)")
        file = (meta or {}).get("file", "")
        parts.append(f"--- {title} ({file}) ---\n{doc.strip()}")
    return "\n\n".join(parts)


@mcp.tool()
def list_docs() -> str:
    """List the titles of all documents available for RAG search."""
    res = _get_coll().get(include=["metadatas"])
    metas = res.get("metadatas", []) or []
    if not metas:
        return "No documents indexed."
    lines = [f"- {m.get('title', '?')}  ({m.get('file', '?')})" for m in metas]
    return "Available documents:\n" + "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
