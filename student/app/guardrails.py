import re
from dataclasses import dataclass, field

# Deny-list of write / DDL / admin keywords. \b = word boundary, so we match
# 'delete' but NOT 'deleted_at'. Compiled once at import for speed.
DANGEROUS = re.compile(
    r"\b(drop|delete|update|insert|alter|truncate|create|attach|detach|pragma|vacuum|replace)\b",
    re.IGNORECASE,
)
# Detects a semicolon followed by more non-whitespace -> a 2nd statement.
# After stripping one trailing ';' we use this to catch 'SELECT 1; DROP ...'
MULTI_STMT = re.compile(r";\s*\S")

class GuardrailError(ValueError):
    """Raised when SQL fails a safety check. Subclasses ValueError on purpose."""
    pass

@dataclass
class GuardrailConfig:
    # Hard ceiling we inject as LIMIT when the model forgets one.
    max_rows: int = 1000
    # Optional allow-list of tables that may appear after FROM/JOIN.
    allowed_tables: set[str] | None = None

def validate_and_fix(sql: str, cfg: GuardrailConfig | None = None) -> str:
    """Validate read-only SQL and inject LIMIT if missing.

    Returns the cleaned-up SQL. Raises GuardrailError on anything dangerous.
    Think of this as a firewall between the LLM and the database.
    """
    cfg = cfg or GuardrailConfig()
    # Normalise: trim whitespace + one trailing semicolon.
    s = sql.strip().rstrip(";").strip()
    if not s: raise GuardrailError("empty SQL")

    # Check 1 -- reject stacked statements like "SELECT 1; DROP ...".
    if MULTI_STMT.search(sql): raise GuardrailError("multiple statements")
    # Check 2 -- reject any write/DDL/admin keyword anywhere in the query.
    if DANGEROUS.search(s): raise GuardrailError("write/DDL keyword blocked")
    # Check 3 -- must START with SELECT or WITH (positive allow-list).
    if not re.match(r"^\s*(with|select)\b", s, re.IGNORECASE):
        raise GuardrailError("only SELECT / WITH allowed")

    # Check 4 -- optional table allow-list. Walks every FROM <name> and
    # rejects anything not on the list.
    if cfg.allowed_tables:
        for t in re.findall(r"\bfrom\s+([a-zA-Z_][\w]*)", s, re.IGNORECASE):
            if t.lower() not in {x.lower() for x in cfg.allowed_tables}:
                raise GuardrailError(f"table {t!r} not allowed")

    # Fix-up -- append LIMIT if the model forgot one, so an accidental giant
    # result set can't blow up the UI.
    if not re.search(r"\blimit\b", s, re.IGNORECASE):
        s += f" LIMIT {cfg.max_rows}"
    return s
