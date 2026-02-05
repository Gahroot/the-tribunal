"""Contact filtering engine - shared by contacts API and segment resolution."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, func, or_, select

from app.models.contact import Contact
from app.models.tag import ContactTag


def apply_contact_filters(
    query: Select[Any],
    workspace_id: uuid.UUID,
    *,
    # Simple filters (query params)
    tags: list[uuid.UUID] | None = None,
    tags_match: str = "any",  # "any", "all", "none"
    lead_score_min: int | None = None,
    lead_score_max: int | None = None,
    is_qualified: bool | None = None,
    source: str | None = None,
    company_name: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    enrichment_status: str | None = None,
    # Complex filter definition (JSON)
    filter_rules: list[dict[str, Any]] | None = None,
    filter_logic: str = "and",
) -> Select[Any]:
    """Apply contact filters to a SQLAlchemy query.

    This function is the single source of truth for all contact filtering.
    Used by both the contacts API and segment resolution.
    """
    # Simple tag filtering
    if tags:
        query = _apply_tag_filter(query, tags, tags_match)

    # Lead score range
    if lead_score_min is not None:
        query = query.where(Contact.lead_score >= lead_score_min)
    if lead_score_max is not None:
        query = query.where(Contact.lead_score <= lead_score_max)

    # Boolean filter
    if is_qualified is not None:
        query = query.where(Contact.is_qualified == is_qualified)

    # Text filters
    if source:
        query = query.where(Contact.source == source)
    if company_name:
        query = query.where(Contact.company_name.ilike(f"%{company_name}%"))
    if enrichment_status:
        query = query.where(Contact.enrichment_status == enrichment_status)

    # Date range filters
    if created_after:
        query = query.where(Contact.created_at >= created_after)
    if created_before:
        query = query.where(Contact.created_at <= created_before)

    # Complex filter rules
    if filter_rules:
        query = _apply_filter_rules(query, filter_rules, filter_logic)

    return query


def _apply_tag_filter(
    query: Select[Any],
    tag_ids: list[uuid.UUID],
    match_mode: str,
) -> Select[Any]:
    """Apply tag-based filtering."""
    if match_mode == "none":
        # Contacts that do NOT have any of these tags
        has_tag_subq = (
            select(ContactTag.contact_id)
            .where(ContactTag.tag_id.in_(tag_ids))
            .distinct()
        )
        query = query.where(Contact.id.notin_(has_tag_subq))
    elif match_mode == "all":
        # Contacts that have ALL of these tags
        has_all_subq = (
            select(ContactTag.contact_id)
            .where(ContactTag.tag_id.in_(tag_ids))
            .group_by(ContactTag.contact_id)
            .having(func.count(func.distinct(ContactTag.tag_id)) == len(tag_ids))
        )
        query = query.where(Contact.id.in_(has_all_subq))
    else:
        # "any" - contacts that have at least one of these tags
        has_any_subq = (
            select(ContactTag.contact_id)
            .where(ContactTag.tag_id.in_(tag_ids))
            .distinct()
        )
        query = query.where(Contact.id.in_(has_any_subq))

    return query


def _apply_filter_rules(
    query: Select[Any],
    rules: list[dict[str, Any]],
    logic: str,
) -> Select[Any]:
    """Apply complex filter rules from a FilterDefinition."""
    conditions = []

    for rule in rules:
        field = rule.get("field", "")
        operator = rule.get("operator", "")
        value = rule.get("value")

        condition = _build_condition(field, operator, value)
        if condition is not None:
            conditions.append(condition)

    if not conditions:
        return query

    combined = or_(*conditions) if logic == "or" else and_(*conditions)
    return query.where(combined)


def _build_condition(field: str, operator: str, value: Any) -> Any:  # noqa: PLR0911, PLR0912
    """Build a single SQLAlchemy condition from a filter rule."""
    column_map: dict[str, Any] = {
        "status": Contact.status,
        "lead_score": Contact.lead_score,
        "is_qualified": Contact.is_qualified,
        "source": Contact.source,
        "company_name": Contact.company_name,
        "created_at": Contact.created_at,
        "enrichment_status": Contact.enrichment_status,
        "email": Contact.email,
        "first_name": Contact.first_name,
        "last_name": Contact.last_name,
    }

    column = column_map.get(field)
    if column is None:
        return _build_tag_condition(operator, value) if field == "tags" else None

    # Comparison operators
    comparison_ops: dict[str, Any] = {
        "equals": lambda c, v: c == v,
        "not_equals": lambda c, v: c != v,
        "contains": lambda c, v: c.ilike(f"%{v}%"),
        "starts_with": lambda c, v: c.ilike(f"{v}%"),
        "gte": lambda c, v: c >= v,
        "lte": lambda c, v: c <= v,
        "gt": lambda c, v: c > v,
        "lt": lambda c, v: c < v,
        "after": lambda c, v: c >= v,
        "before": lambda c, v: c <= v,
        "is_true": lambda c, _v: c.is_(True),
        "is_false": lambda c, _v: c.is_(False),
        "is_null": lambda c, _v: c.is_(None),
        "is_not_null": lambda c, _v: c.isnot(None),
    }

    if operator == "in" and isinstance(value, list):
        return column.in_(value)

    op_fn = comparison_ops.get(operator)
    if op_fn is not None:
        return op_fn(column, value)

    return None


def _build_tag_condition(operator: str, value: Any) -> Any:
    """Build a tag-based filter condition."""
    if not isinstance(value, list) or not value:
        return None

    tag_ids = [uuid.UUID(v) if isinstance(v, str) else v for v in value]

    if operator == "has_any":
        subq = (
            select(ContactTag.contact_id)
            .where(ContactTag.tag_id.in_(tag_ids))
            .distinct()
        )
        return Contact.id.in_(subq)
    elif operator == "has_all":
        subq = (
            select(ContactTag.contact_id)
            .where(ContactTag.tag_id.in_(tag_ids))
            .group_by(ContactTag.contact_id)
            .having(func.count(func.distinct(ContactTag.tag_id)) == len(tag_ids))
        )
        return Contact.id.in_(subq)
    elif operator == "has_none":
        subq = (
            select(ContactTag.contact_id)
            .where(ContactTag.tag_id.in_(tag_ids))
            .distinct()
        )
        return Contact.id.notin_(subq)

    return None
