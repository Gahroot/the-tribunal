"""Reusable Pydantic v2 base classes and mixins for API schemas.

This module provides building blocks that future schema refactors can compose
to reduce duplication across `app/schemas/`:

- `TimestampMixin`: adds `created_at` / `updated_at` fields.
- `WorkspaceScopedMixin`: adds `workspace_id` for multi-tenant entities.
- `BaseEntityResponse`: combines both mixins with a UUID `id` field and
  `from_attributes=True` so it can be returned directly from ORM models.
- `Paginated[T]`: generic container mirroring the existing hand-written
  `*ListResponse` shape (`items`, `total`, `page`, `page_size`, `pages`).

Existing schemas are intentionally left untouched; adopt these incrementally
in new code or follow-up refactors.
"""

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class TimestampMixin(BaseModel):
    """Mixin for entities that track creation and update timestamps."""

    created_at: datetime
    updated_at: datetime


class WorkspaceScopedMixin(BaseModel):
    """Mixin for entities scoped to a workspace (multi-tenant)."""

    workspace_id: uuid.UUID


class BaseEntityResponse(TimestampMixin, WorkspaceScopedMixin):
    """Base response schema for UUID-keyed, workspace-scoped entities."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class Paginated(BaseModel, Generic[T]):  # noqa: UP046
    """Generic paginated response container."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int
