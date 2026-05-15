"""Saved questions (Module 09).

Tiny JSON-backed persistence so users can ★ a turn and replay it later.
No DB, no ORM — a file in the repo. That's enough for a workshop product.
"""
from __future__ import annotations

import json
from pathlib import Path

STORE = Path("data") / "saved_questions.json"


def load() -> list[str]:
    if not STORE.exists():
        return []
    try:
        return json.loads(STORE.read_text())
    except json.JSONDecodeError:
        return []


def save(items: list[str]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(items, indent=2))


def add(question: str) -> list[str]:
    items = load()
    if question and question not in items:
        items.append(question)
        save(items)
    return items


def remove(question: str) -> list[str]:
    items = [q for q in load() if q != question]
    save(items)
    return items
