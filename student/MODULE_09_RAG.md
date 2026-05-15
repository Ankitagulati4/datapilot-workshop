# Module 09 — Build a RAG MCP server (25 min)

> Goal: a **second** in-house MCP server that answers *conceptual* questions
> from your documentation, not from SQL. Then both servers (DQ + RAG) live
> side by side. Module 10 plugs both into Claude Desktop.

## Why this matters

Module 07 published one MCP server (data quality). Module 09 publishes a
second one of a completely different shape (semantic search). The point:
**MCP is a contract, not a database trick**. You can wrap any capability —
SQL, vector search, web fetch, file I/O — behind the same `@mcp.tool()`
decorator and every MCP-aware client gets it for free.

## RAG in 3 sentences

1. **Embed** your documents: turn each into a list of numbers that encode
   meaning. Similar texts get similar vectors.
2. **Store** the vectors in a vector store (we use ChromaDB — a file on
   disk).
3. **Search**: at query time, embed the *question* and ask the store for
   the closest documents. Stick those documents in the LLM's context.

That's it. No fine-tuning, no model training. The LLM doesn't know about
your docs until your tool hands them over.

## What you'll build

```
docs/                                ← corpus (7 small markdown files)
└── 01_about_shopflow.md … 07_freshness_slas.md

student/mcp_servers/
├── build_rag_index.py               ← run once to embed docs
└── rag_server.py                    ← MCP server: 2 tools, ~50 lines

student/app/config/mcp.json          ← add 3rd entry: datapilot-rag
student/app/chat_agent.py            ← add 2 names to SAFE_TOOL_NAMES
```

Time: 25 min in 5 sub-steps.

## 1. Install dependencies

```powershell
pip install "chromadb>=0.5"
```

(Already in `requirements.txt` — this line is just in case you skipped it
during setup.) ChromaDB ships its own ONNX-runtime embedding model
(`all-MiniLM-L6-v2`, ~120MB). No torch, no `sentence-transformers`. The
first call downloads the model; subsequent calls are offline.

## 2. Copy the corpus

The repo already contains a `docs/` folder with 7 short markdown files
(returns policy, channel definitions, segment glossary, etc.). Open one
to skim:

```powershell
code docs/03_segment_glossary.md
```

This is the kind of content RAG is *for*: definitions, policies, glossary
items the database doesn't know about.

## 3. Create `student/mcp_servers/build_rag_index.py`

```python
"""Build the RAG vector index from docs/*.md. Run once.

    python student/mcp_servers/build_rag_index.py
"""
from pathlib import Path
import chromadb

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"
INDEX_DIR = ROOT / "data" / "rag.chroma"
COLLECTION = "shopflow_docs"


def main() -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(INDEX_DIR))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    coll = client.create_collection(name=COLLECTION)

    ids, docs, metas = [], [], []
    for md in sorted(DOCS_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        ids.append(md.stem)
        docs.append(text)
        metas.append({"title": title, "file": md.name})

    coll.add(ids=ids, documents=docs, metadatas=metas)
    print(f"Indexed {len(ids)} docs into {INDEX_DIR}")


if __name__ == "__main__":
    main()
```

Run it:
```powershell
python student/mcp_servers/build_rag_index.py
```

Expected output: `Indexed 7 docs into ...\data\rag.chroma`. First run
takes ~30 sec (downloading the embedding model). Subsequent runs:
< 2 sec.

## 4. Create `student/mcp_servers/rag_server.py`

```python
"""DataPilot RAG MCP Server: semantic search over docs/."""
import contextlib
import os
import sys
from pathlib import Path

# Silence ChromaDB telemetry before importing it — ANY stray write to stdout
# corrupts the JSON-RPC stream this server speaks over stdio.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")

# Redirect stdout to stderr while chromadb (and onnxruntime) imports
# — same reason: keep stdout MCP-clean.
with contextlib.redirect_stdout(sys.stderr):
    import chromadb

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = ROOT / "data" / "rag.chroma"
COLLECTION = "shopflow_docs"

mcp = FastMCP("datapilot-rag")

# Lazy-init chromadb on first tool call — fast startup + stdout-clean.
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
    k = max(1, min(int(k), 5))
    res = _coll_ready().query(query_texts=[query], n_results=k)
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    if not docs:
        return "No matching documents found."
    out = []
    for doc, meta in zip(docs, metas):
        title = (meta or {}).get("title", "(untitled)")
        out.append(f"--- {title} ---\n{doc.strip()}")
    return "\n\n".join(out)


@mcp.tool()
def list_docs() -> str:
    """List the titles of all documents available for RAG search."""
    res = _coll_ready().get(include=["metadatas"])
    metas = res.get("metadatas", []) or []
    lines = [f"- {m.get('title', '?')} ({m.get('file', '?')})" for m in metas]
    return "Available documents:\n" + "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
```

> 🐛 **Why the `redirect_stdout` dance?** MCP servers speak JSON-RPC over
> **stdout**. If chromadb (or its bundled onnxruntime) prints *anything*
> there during import or init, the client sees garbage and aborts with
> `Connection closed`. We send those prints to stderr instead.

Smoke-test it standalone (no agent):
```powershell
python student/mcp_servers/rag_server.py
```
It sits silently on stdin (waiting for JSON-RPC). Ctrl+C to exit.

## 5. Register it in `student/app/config/mcp.json`

Add the 3rd entry:
```json
{
  "mcpServers": {
    "shopflow-sqlite": { "command": "uvx", "args": ["mcp-server-sqlite", "--db-path", "${SHOPFLOW_DB}"], "transport": "stdio" },
    "datapilot-dq":   { "command": "python", "args": ["student/mcp_servers/dq_server.py", "${SHOPFLOW_DB}"], "transport": "stdio" },
    "datapilot-rag":  { "command": "python", "args": ["student/mcp_servers/rag_server.py"], "transport": "stdio" }
  }
}
```

Then update `SAFE_TOOL_NAMES` in `student/app/chat_agent.py`:
```python
SAFE_TOOL_NAMES = {
    "list_tables", "describe_table", "read_query",
    "check_freshness", "check_nulls", "check_duplicates", "count_rows",
    "search_docs", "list_docs",   # NEW Module 09
}
```

> 🐛 **One more tweak** — in `student/app/mcp_clients.py`, the JSON says
> `"command": "python"`. On Windows that resolves via `PATH`, which may not
> point at your venv (so chromadb isn't found). Add this just before
> `MultiServerMCPClient(...)`:
> ```python
> import sys
> for spec in cfg["mcpServers"].values():
>     if spec.get("command") == "python":
>         spec["command"] = sys.executable
> ```
> This forces every Python-based MCP server to use *this* interpreter.

Restart the app.

## ✅ CHECK

Sidebar now shows **three** MCP servers and a tool count of **9**.

**Conceptual question** (RAG should win, not SQL):
> "what does VIP segment mean?"

Expected: agent picks `search_docs("VIP segment")` → returns the
"Customer segment glossary" excerpt → answers with the >$2,000 lifetime
revenue rule.

**Database question** (SQL should still win):
> "how many VIP customers do we have?"

Expected: agent picks `read_query` and counts.

**Documentation listing**:
> "list the docs"

Expected: agent picks `list_docs` → 7 titles.

## Talking points

- **You just shipped a second MCP server.** Different domain (semantic
  search vs SQL), identical pattern (FastMCP, stdio, @mcp.tool()).
- **The agent autonomously chose between SQL and RAG** based on the
  question shape. That's the value of giving it different-flavored tools
  side by side.
- In Module 10, we plug **both** custom servers into Claude Desktop —
  one config edit, two new capabilities for Claude.

## What we deliberately skipped

This is a *beginner* RAG module. Topics for a future deep dive:
- **Chunking** — splitting long docs into smaller chunks (we use one
  chunk per file)
- **Hybrid search** — combining vector search with keyword search
- **Re-ranking** — using a second model to reorder top-k results
- **Evaluation** — measuring retrieval quality (precision@k, MRR, …)
- **Streaming embeddings** — for very large corpora

Each of those is its own session.
