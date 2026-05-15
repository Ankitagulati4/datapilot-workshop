"""Build the RAG vector index from `docs/*.md`.

Run once (or after editing the docs):
    python solution/mcp_servers/build_rag_index.py

Output: `data/rag.chroma/` — a persistent ChromaDB collection named
`shopflow_docs`. The `rag_server.py` MCP server reads from this same path.

We use ChromaDB's default embedding function (ONNX runtime version of
`all-MiniLM-L6-v2`, ~120MB, downloaded on first use). No torch dependency.
"""
from __future__ import annotations

import sys
from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"
INDEX_DIR = ROOT / "data" / "rag.chroma"
COLLECTION = "shopflow_docs"


def main() -> int:
    if not DOCS_DIR.exists():
        print(f"ERROR: docs/ not found at {DOCS_DIR}", file=sys.stderr)
        return 1

    md_files = sorted(DOCS_DIR.glob("*.md"))
    if not md_files:
        print(f"ERROR: no .md files in {DOCS_DIR}", file=sys.stderr)
        return 1

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(INDEX_DIR))

    # Reset for deterministic rebuilds
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    coll = client.create_collection(name=COLLECTION)

    ids, docs, metas = [], [], []
    for md in md_files:
        text = md.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip() if text else md.stem
        ids.append(md.stem)
        docs.append(text)
        metas.append({"title": title, "file": md.name})

    coll.add(ids=ids, documents=docs, metadatas=metas)
    print(f"Indexed {len(ids)} documents into {INDEX_DIR}")
    for m in metas:
        print(f"  - {m['file']:30s}  {m['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
