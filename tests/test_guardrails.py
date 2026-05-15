"""Tests for read-only SQL guardrails (Module 03)."""
import pytest

from solution.app.guardrails import (
    GuardrailConfig, GuardrailError, validate_and_fix,
)


def test_simple_select_gets_limit():
    out = validate_and_fix("SELECT * FROM customers")
    assert "LIMIT" in out.upper()


def test_existing_limit_preserved():
    out = validate_and_fix("SELECT * FROM customers LIMIT 5")
    assert out.upper().count("LIMIT") == 1


def test_with_cte_allowed():
    out = validate_and_fix("WITH x AS (SELECT 1) SELECT * FROM x")
    assert "LIMIT" in out.upper()


@pytest.mark.parametrize("sql", [
    "DROP TABLE customers",
    "DELETE FROM orders",
    "UPDATE products SET price = 0",
    "INSERT INTO orders VALUES (1)",
    "SELECT * FROM customers; DROP TABLE orders",
    "PRAGMA table_info(orders)",
    "ATTACH DATABASE 'evil.db' AS evil",
])
def test_dangerous_blocked(sql):
    with pytest.raises(GuardrailError):
        validate_and_fix(sql)


def test_table_allow_list():
    cfg = GuardrailConfig(allowed_tables={"customers"})
    validate_and_fix("SELECT * FROM customers", cfg)
    with pytest.raises(GuardrailError):
        validate_and_fix("SELECT * FROM secret_table", cfg)
