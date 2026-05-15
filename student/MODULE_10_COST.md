# Module 10 — Cost badge (10 min)

> Goal: every answer shows ~tokens used and ~USD spent. Builds instinct that LLM calls cost money.

## 1. Create `student/app/cost.py`
```python
"""Cheap, no-tokenizer cost estimate. Good enough for a dashboard.

Groq openai/gpt-oss-20b is currently free; we use Groq's published
list price for `llama-3.3-70b` as a stand-in so the badge isn't 0.
"""
PRICE_INPUT_PER_M = 0.59   # USD / 1M input tokens
PRICE_OUTPUT_PER_M = 0.79  # USD / 1M output tokens

def crude_token_count(text: str) -> int:
    # ~4 chars per token rule of thumb
    return max(1, len(text) // 4)

def estimate_usd(input_text: str, output_text: str) -> tuple[int, int, float]:
    i = crude_token_count(input_text)
    o = crude_token_count(output_text)
    usd = i * PRICE_INPUT_PER_M / 1e6 + o * PRICE_OUTPUT_PER_M / 1e6
    return i, o, usd
```

## 2. Show after every answer (`streamlit_app.py`)
```python
from app.cost import estimate_usd

# right after st.markdown(r.answer):
all_in = q + "\n".join(c["tool"]+str(c["input"]) for c in r.tool_calls)
all_out = r.answer + "\n".join(str(c["output"]) for c in r.tool_calls)
i, o, usd = estimate_usd(all_in, all_out)
st.caption(f"⚡ {r.latency_ms} ms · 🧠 {i}+{o} tok · 💲 ${usd:.5f}")
```

## ✅ CHECK
- Ask any question — see the badge.
- Ask a chatty one ("explain everything you know about orders") — token count jumps; USD goes up.
