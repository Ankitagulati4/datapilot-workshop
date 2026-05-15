# Module 09 — Save & replay questions (15 min)

> Goal: a ★ button after every answer that pins the question to the sidebar. Click to re-ask.

## 1. Create `student/app/storage.py`
```python
import json
from pathlib import Path

PATH = Path("data/saved_questions.json")

def load() -> list[str]:
    if not PATH.exists(): return []
    try: return json.loads(PATH.read_text())
    except json.JSONDecodeError: return []

def save(q: str) -> None:
    items = load()
    if q in items: return
    items.insert(0, q)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(items[:25], indent=2))

def remove(q: str) -> None:
    PATH.write_text(json.dumps([x for x in load() if x != q], indent=2))
```

## 2. Add ★ button after each assistant message (`streamlit_app.py`)
```python
from app import storage

# inside the assistant block, after rendering the answer:
if st.button("★ Save", key=f"save_{len(st.session_state.history)}"):
    storage.save(q); st.toast("Saved.")
```

## 3. Sidebar replay
```python
with st.sidebar:
    st.divider()
    st.subheader("★ Saved")
    for sq in storage.load():
        cols = st.columns([5,1])
        if cols[0].button(sq, key=f"replay_{sq}", width="stretch"):
            st.session_state.replay = sq
        if cols[1].button("✕", key=f"del_{sq}"):
            storage.remove(sq); st.rerun()

# at the top of the chat-input handling:
q = st.session_state.pop("replay", None) or st.chat_input("Ask...")
```

## ✅ CHECK
- Ask a question, click ★ Save → it appears in sidebar.
- Reload the page → the saved question is still there (persisted to JSON).
- Click the saved question → it re-asks itself.
