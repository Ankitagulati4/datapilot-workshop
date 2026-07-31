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