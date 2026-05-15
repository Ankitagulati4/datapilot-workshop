"""Read-only SQL guardrails.

Wraps the input to the SQLite MCP server's `read_query` tool so a malicious
or careless model cannot drop a table or smuggle in a second statement.

This is the production safety layer. 11 unit tests in tests/.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


class GuardrailError(ValueError):
    """Raised when SQL fails a safety check."""


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|replace|"
    r"grant|revoke|attach|detach|pragma|copy|vacuum|reindex)\b",
    re.IGNORECASE,
)
_MULTI_STMT = re.compile(r";\s*\S")


@dataclass
class GuardrailConfig:
    max_rows: int = 1000
    allowed_tables: set[str] | None = None


def validate_and_fix(sql: str, cfg: GuardrailConfig | None = None) -> str:
    """Validate read-only SQL and inject LIMIT if missing.

    Raises GuardrailError on dangerous SQL. Returns the (possibly modified)
    safe SQL ready to execute.
    """
    cfg = cfg or GuardrailConfig()
    s = sql.strip().rstrip(";").strip()
    if not s:
        raise GuardrailError("Empty query")

    if _MULTI_STMT.search(s):
        raise GuardrailError("Multiple statements are not allowed.")
    if _FORBIDDEN.search(s):
        raise GuardrailError("Only read-only SELECT/WITH queries are allowed.")
    if not re.match(r"^\s*(select|with)\b", s, re.IGNORECASE):
        raise GuardrailError("Query must start with SELECT or WITH.")

    if cfg.allowed_tables:
        used = set(re.findall(r"\b(?:from|join)\s+([A-Za-z_][\w]*)", s, re.IGNORECASE))
        bad = used - cfg.allowed_tables
        if bad:
            raise GuardrailError(f"Tables not in allow-list: {sorted(bad)}")

    if not re.search(r"\blimit\b", s, re.IGNORECASE):
        s = f"{s}\nLIMIT {cfg.max_rows}"
    return s
