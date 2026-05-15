# Module 03 — Guardrails (15 min)

> Goal: even if the LLM tries `DROP TABLE customers`, your app refuses.

## 1. Create `student/app/guardrails.py`
```python
import re
from dataclasses import dataclass, field

DANGEROUS = re.compile(
    r"\b(drop|delete|update|insert|alter|truncate|create|attach|detach|pragma|vacuum|replace)\b",
    re.IGNORECASE,
)
MULTI_STMT = re.compile(r";\s*\S")

class GuardrailError(ValueError): pass

@dataclass
class GuardrailConfig:
    max_rows: int = 1000
    allowed_tables: set[str] | None = None

def validate_and_fix(sql: str, cfg: GuardrailConfig | None = None) -> str:
    cfg = cfg or GuardrailConfig()
    s = sql.strip().rstrip(";").strip()
    if not s: raise GuardrailError("empty SQL")
    if MULTI_STMT.search(sql): raise GuardrailError("multiple statements")
    if DANGEROUS.search(s): raise GuardrailError("write/DDL keyword blocked")
    if not re.match(r"^\s*(with|select)\b", s, re.IGNORECASE):
        raise GuardrailError("only SELECT / WITH allowed")
    if cfg.allowed_tables:
        for t in re.findall(r"\bfrom\s+([a-zA-Z_][\w]*)", s, re.IGNORECASE):
            if t.lower() not in {x.lower() for x in cfg.allowed_tables}:
                raise GuardrailError(f"table {t!r} not allowed")
    if not re.search(r"\blimit\b", s, re.IGNORECASE):
        s += f" LIMIT {cfg.max_rows}"
    return s
```

## 2. Wrap the MCP `read_query` in `chat_agent.py`
At the top of `ChatAgent.__init__`, after loading tools:
```python
from app.guardrails import validate_and_fix, GuardrailError

SAFE = {"read_query","list_tables","describe_table"}  # whitelist
self.tools = [t for t in self.tools if t.name in SAFE]

for t in self.tools:
    if t.name == "read_query":
        original = t.coroutine
        async def guarded(query: str, _orig=original, **kw):
            try:
                safe = validate_and_fix(query)
            except GuardrailError as e:
                return f"GUARDRAIL BLOCK: {e}", None  # MCP needs (content, artifact)
            return await _orig(query=safe, **kw)
        t.coroutine = guarded
```

## 3. Test it
```bash
pytest tests/test_guardrails.py -v
```
All 11 tests should pass.

## ✅ CHECK
- Sidebar **Tools** count drops from 6 → 3.
- Ask in chat: **"run this SQL: drop table customers"** → answer mentions
  `GUARDRAIL BLOCK` (or the agent refuses politely).
- The DB is untouched.
