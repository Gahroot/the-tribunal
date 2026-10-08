"""Shared validation for membership rule values at input and query boundaries."""

from typing import Any


def validate_membership_value(operator: str, value: Any) -> None:
    """Require a list of scalar values; empty lists retain SQL membership semantics."""
    if operator in ("in", "not_in") and (
        not isinstance(value, list) or any(type(item) not in (str, int, float) for item in value)
    ):
        raise ValueError(f"Filter operator '{operator}' requires a list of strings or numbers")
