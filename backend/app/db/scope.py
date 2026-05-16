"""Workspace-scoping helpers for tenant-isolated queries.

Every workspace-owned ORM model declares a ``workspace_id`` column. Endpoints
historically hand-roll ``where(Model.workspace_id == workspace_id)`` on every
list, get, update, and delete query. That repetition is a tenancy-leak risk:
one missed ``where`` clause exposes cross-workspace data.

:func:`apply_workspace_scope` centralizes that predicate. The helper validates
at runtime that the model actually carries a ``workspace_id`` column — so a
typo or accidental use on a non-tenant model fails loudly at import-time test
coverage rather than silently returning unscoped rows.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select
from sqlalchemy.orm import DeclarativeBase

_WORKSPACE_COLUMN = "workspace_id"


def apply_workspace_scope[SelectT: Select](  # type: ignore[type-arg]
    query: SelectT,
    model: type[DeclarativeBase],
    workspace_id: uuid.UUID,
) -> SelectT:
    """Append a ``Model.workspace_id == workspace_id`` predicate to ``query``.

    Args:
        query: SQLAlchemy ``Select`` statement to constrain.
        model: ORM model class that must declare a ``workspace_id`` column.
        workspace_id: The workspace UUID to scope rows to.

    Returns:
        A new ``Select`` with the workspace predicate appended. The original
        ``query`` is left unmodified (SQLAlchemy ``Select`` is immutable).

    Raises:
        TypeError: If ``model`` does not declare a ``workspace_id`` column.
            Treating this as a programmer error — surfacing it loudly is the
            whole point of the helper.
    """
    table = getattr(model, "__table__", None)
    if table is None or _WORKSPACE_COLUMN not in table.columns:
        raise TypeError(
            f"{model.__name__} has no 'workspace_id' column; "
            "apply_workspace_scope cannot be used on non-tenant models."
        )

    column = table.columns[_WORKSPACE_COLUMN]
    return query.where(column == workspace_id)
