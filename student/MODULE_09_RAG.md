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

Output: data/rag.chroma/ -- a persistent ChromaDB collection that
rag_server.py will read at query time.
"""
from __future__ import annotations

import sys
from pathlib import Path

import chromadb   # tiny on-disk vector store; ships its own ONNX embedding model

# Resolve repo paths regardless of where the script is run from.
ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"                      # source markdown
INDEX_DIR = ROOT / "data" / "rag.chroma"      # persistent index location
COLLECTION = "shopflow_docs"                  # logical name inside the DB


def main() -> int:
    # Fail fast with a helpful message if the corpus is missing.
    if not DOCS_DIR.exists():
        print(f"ERROR: docs/ not found at {DOCS_DIR}", file=sys.stderr)
        return 1
    md_files = sorted(DOCS_DIR.glob("*.md"))
    if not md_files:
        print(f"ERROR: no .md files in {DOCS_DIR}", file=sys.stderr)
        return 1

    # Make sure the index folder exists; PersistentClient writes files here.
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    # `flush=True` so progress lines appear immediately even on Windows.
    print(f"[1/3] Opening Chroma at {INDEX_DIR}", flush=True)
    client = chromadb.PersistentClient(path=str(INDEX_DIR))

    # Deterministic rebuilds: wipe any previous version of the collection
    # so re-running this script gives you the same starting state.
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        # First-run case: collection didn't exist yet. That's fine.
        pass
    coll = client.create_collection(name=COLLECTION)

    # Gather every markdown file into 3 parallel lists Chroma wants:
    #   ids  -> stable unique key per document
    #   docs -> the raw text we'll embed and later return as search hits
    #   metas -> arbitrary key/value metadata (we keep title + filename)
    ids, docs, metas = [], [], []
    for md in md_files:
        text = md.read_text(encoding="utf-8")
        # First markdown heading becomes the human-readable title.
        title = text.splitlines()[0].lstrip("# ").strip() if text else md.stem
        ids.append(md.stem)               # e.g. '03_segment_glossary'
        docs.append(text)
        metas.append({"title": title, "file": md.name})

    # One call does ALL the work. First run downloads ~80MB embedding model
    # (all-MiniLM-L6-v2 via ONNX runtime) to %USERPROFILE%\.cache\chroma\
    # — can take 1–5 min on a slow connection. Subsequent runs: < 2 sec.
    print(f"[2/3] Embedding {len(ids)} docs (first run downloads ~80MB model)...", flush=True)
    coll.add(ids=ids, documents=docs, metadatas=metas)

    print(f"[3/3] Indexed {len(ids)} documents into {INDEX_DIR}")
    for m in metas:
        print(f"  - {m['file']:30s}  {m['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run it:
```powershell
python student/mcp_servers/build_rag_index.py
```

Expected output:
```
[1/3] Opening Chroma at ...\data\rag.chroma
[2/3] Embedding 7 docs (first run downloads ~80MB model)...
[3/3] Indexed 7 documents into ...\data\rag.chroma
  - 01_about_shopflow.md           About ShopFlow
  - 02_channel_definitions.md      Channel definitions
  ...
```

> ⚠️ **First run can take 1–5 minutes** at the `[2/3]` step while Chroma
> downloads the ONNX embedding model (~80 MB) into
> `%USERPROFILE%\.cache\chroma\`. It's NOT hung — don't Ctrl+C. To
> confirm it's downloading, open another PowerShell and run:
> ```powershell
> Get-ChildItem "$env:USERPROFILE\.cache\chroma" -Recurse -ErrorAction SilentlyContinue
> ```
> Files there with growing sizes → download in progress.
>
> Subsequent runs finish in < 2 sec.
>
> ⚠️ **Don't copy `rag_server.py`'s code into this file.** They live
> next to each other but do opposite things: this script *writes* the
> index and exits; `rag_server.py` *reads* the index and stays alive on
> stdio. Mixing them up makes "build_rag_index" appear to hang forever
> (it's actually a silent MCP server waiting for JSON-RPC).

## 4. Create `student/mcp_servers/rag_server.py`

```python
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

Then update the `SAFE` allow-list in `student/app/chat_agent.py` to
include the two new RAG tool names (keep the variable name the same — it's
the one Module 03 created and Module 07 already extended):
```python
SAFE = {
    # shopflow-sqlite (Module 03)
    "read_query", "list_tables", "describe_table",
    # datapilot-dq (Module 07)
    "count_rows", "check_freshness", "check_nulls", "check_duplicates",
    # datapilot-rag (Module 09) — NEW
    "search_docs", "list_docs",
}
```

> ⚠️ Do **not** rename `SAFE` to `SAFE_TOOL_NAMES` — `chat_agent.py`
> references the existing name on line ~86 (`if t.name in SAFE`). Renaming
> raises `NameError: name 'SAFE' is not defined`.

> 🐛 **One more tweak** — in `student/app/mcp_clients.py`, the JSON says
> `"command": "python"`. On Windows that resolves via `PATH`, which may not
> point at your venv (so chromadb isn't found). At the top of the file add:
> ```python
> import sys
> ```
> Then inside `load_mcp_tools()`, **right after** `cfg = _load_config()`,
> add:
> ```python
> for spec in cfg.values():
>     if spec.get("command") == "python":
>         spec["command"] = sys.executable
> ```
> This forces every Python-based MCP server to use *this* interpreter.
>
> ⚠️ Note: iterate `cfg.values()` — NOT `cfg["mcpServers"].values()` —
> because `_load_config()` already returns the inner servers dict. The
> wrong form raises `KeyError: 'mcpServers'`.

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
