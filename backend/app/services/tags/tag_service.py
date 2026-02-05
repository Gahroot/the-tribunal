"""Tag service - business logic orchestration layer."""

import uuid
from typing import Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.tag import TagResponse
from app.services.tags.tag_repository import (
    bulk_add_tags,
    bulk_remove_tags,
    create_tag,
    delete_tag,
    get_tag_by_id,
    list_tags,
    update_tag,
)

logger = structlog.get_logger()


class TagService:
    """High-level tag service for orchestrating business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.log = logger.bind(service="tag")

    async def list_tags(
        self,
        workspace_id: uuid.UUID,
    ) -> dict[str, Any]:
        """List all tags for a workspace with contact counts."""
        rows = await list_tags(workspace_id, self.db)

        items = []
        for tag, contact_count in rows:
            tag_response = TagResponse.model_validate(tag)
            tag_response.contact_count = contact_count
            items.append(tag_response)

        return {
            "items": items,
            "total": len(items),
        }

    async def get_tag(
        self,
        tag_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> TagResponse:
        """Get a specific tag."""
        tag = await get_tag_by_id(tag_id, workspace_id, self.db)
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tag not found",
            )
        return TagResponse.model_validate(tag)

    async def create_tag(
        self,
        workspace_id: uuid.UUID,
        name: str,
        color: str = "#6366f1",
    ) -> TagResponse:
        """Create a new tag."""
        tag = await create_tag(
            workspace_id=workspace_id,
            name=name,
            color=color,
            db=self.db,
        )
        return TagResponse.model_validate(tag)

    async def update_tag(
        self,
        tag_id: uuid.UUID,
        workspace_id: uuid.UUID,
        update_data: dict[str, str],
    ) -> TagResponse:
        """Update a tag."""
        tag = await get_tag_by_id(tag_id, workspace_id, self.db)
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tag not found",
            )
        updated = await update_tag(tag, self.db, update_data)
        return TagResponse.model_validate(updated)

    async def delete_tag(
        self,
        tag_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None:
        """Delete a tag."""
        tag = await get_tag_by_id(tag_id, workspace_id, self.db)
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tag not found",
            )
        await delete_tag(tag, self.db)

    async def bulk_tag_contacts(
        self,
        workspace_id: uuid.UUID,
        contact_ids: list[int],
        add_tag_ids: list[uuid.UUID] | None = None,
        remove_tag_ids: list[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        """Bulk add/remove tags on contacts."""
        updated = 0
        errors: list[str] = []

        if add_tag_ids:
            try:
                added = await bulk_add_tags(
                    contact_ids=contact_ids,
                    tag_ids=add_tag_ids,
                    workspace_id=workspace_id,
                    db=self.db,
                )
                updated += added
            except Exception as e:
                errors.append(f"Failed to add tags: {e!s}")

        if remove_tag_ids:
            try:
                removed = await bulk_remove_tags(
                    contact_ids=contact_ids,
                    tag_ids=remove_tag_ids,
                    workspace_id=workspace_id,
                    db=self.db,
                )
                updated += removed
            except Exception as e:
                errors.append(f"Failed to remove tags: {e!s}")

        return {
            "updated": updated,
            "errors": errors,
        }
