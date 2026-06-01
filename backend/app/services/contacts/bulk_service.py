"""Bulk contact mutation service."""

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.contacts.contact_repository import (
    bulk_delete_contacts as repo_bulk_delete_contacts,
)
from app.services.contacts.contact_repository import (
    bulk_update_status as repo_bulk_update_status,
)
from app.services.contacts.exceptions import ContactValidationError

logger = structlog.get_logger()


class ContactBulkService:
    """Bulk update/delete operations for contacts."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.log = logger.bind(service="contact_bulk")

    async def bulk_delete_contacts(
        self,
        contact_ids: list[int],
        workspace_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Delete multiple contacts in a workspace."""
        if not contact_ids:
            raise ContactValidationError("No contact IDs provided")

        deleted, errors = await repo_bulk_delete_contacts(
            contact_ids=contact_ids,
            workspace_id=workspace_id,
            db=self.db,
        )

        return {"deleted": deleted, "failed": len(errors), "errors": errors}

    async def bulk_update_status(
        self,
        contact_ids: list[int],
        workspace_id: uuid.UUID,
        new_status: str,
    ) -> dict[str, Any]:
        """Update the lifecycle status for multiple contacts in a workspace."""
        if not contact_ids:
            raise ContactValidationError("No contact IDs provided")

        updated, errors = await repo_bulk_update_status(
            contact_ids=contact_ids,
            workspace_id=workspace_id,
            new_status=new_status,
            db=self.db,
        )

        return {"updated": updated, "failed": len(errors), "errors": errors}
