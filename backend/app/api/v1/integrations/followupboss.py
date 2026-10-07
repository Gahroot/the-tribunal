"""Follow Up Boss sync endpoints.

These routes were previously colocated with the realtor onboarding flow in
``app/api/v1/realtor.py``. They are mounted under the same public URL
(``/realtor/...``) for backwards-compatibility with the frontend.
"""

import uuid
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.contact import Contact
from app.models.workspace import Workspace, WorkspaceIntegration
from app.schemas.followupboss import (
    FUBContact,
    FUBImportResponse,
    FUBPeopleResponse,
    FUBVerifyResponse,
)
from app.services.followupboss import FollowUpBossClient
from app.services.onboarding.credentials import store_followupboss_credentials
from app.services.reactivation.drip_bootstrap import auto_create_drip_for_imports

router = APIRouter()
workspace_router = APIRouter()
logger = structlog.get_logger()


async def upsert_fub_integration(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    api_key: str,
) -> None:
    """Create or update a Follow Up Boss WorkspaceIntegration row."""
    await store_followupboss_credentials(db, workspace_id, api_key)


async def _get_fub_integration(
    workspace_id: uuid.UUID,
    db: AsyncSession,
) -> WorkspaceIntegration:
    """Fetch the active Follow Up Boss integration or raise 404."""
    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.integration_type == "followupboss",
            WorkspaceIntegration.is_active.is_(True),
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follow Up Boss not connected",
        )
    return integration


async def _fetch_all_fub_people(
    client: FollowUpBossClient,
) -> list[dict]:  # type: ignore[type-arg]
    """Paginate through all FUB contacts and return as a flat list."""
    all_people: list[dict] = []  # type: ignore[type-arg]
    page_offset = 0
    while True:
        data = await client.get_people(limit=100, offset=page_offset)
        people = data.get("people", [])
        if not people:
            break
        all_people.extend(people)
        page_offset += 100
        metadata: dict[str, int] = data.get("_metadata", {})
        if page_offset >= metadata.get("total", 0):
            break
    return all_people


async def _import_single_fub_contact(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    fub_person: dict,  # type: ignore[type-arg]
) -> tuple[str, int | None]:
    """Import a single FUB contact.

    Returns ``(status, contact_id)`` where status is one of
    ``"imported"``, ``"skipped"`` or ``"failed"``.
    """
    phones: list[dict[str, str]] = fub_person.get("phones", [])
    emails: list[dict[str, str]] = fub_person.get("emails", [])
    phone = phones[0]["value"] if phones else None
    email = emails[0]["value"] if emails else None

    if not phone and not email:
        return "failed", None

    conditions = []
    if phone:
        conditions.append(Contact.phone_number == phone)
    if email:
        conditions.append(Contact.email == email)

    existing = await db.execute(
        select(Contact).where(
            Contact.workspace_id == workspace_id,
            or_(*conditions),
        )
    )
    if existing.scalar_one_or_none():
        return "skipped", None

    contact = Contact(
        workspace_id=workspace_id,
        first_name=fub_person.get("firstName", ""),
        last_name=fub_person.get("lastName"),
        phone_number=phone or "",
        email=email,
        source=f"Follow Up Boss (ID: {fub_person.get('id', 'unknown')})",
        notes=fub_person.get("background"),
    )
    db.add(contact)
    await db.flush()
    return "imported", contact.id


@router.post("/verify-fub", response_model=FUBVerifyResponse)
async def verify_fub(
    current_user: CurrentUser,
    api_key: str = Body(..., embed=True),
) -> FUBVerifyResponse:
    """Verify a Follow Up Boss API key by calling the /me endpoint."""
    client = FollowUpBossClient(api_key)
    try:
        data = await client.verify()
        return FUBVerifyResponse(
            valid=True,
            name=data.get("name"),
            email=data.get("email"),
        )
    except httpx.HTTPStatusError:
        return FUBVerifyResponse(valid=False, name=None, email=None)
    finally:
        await client.close()


async def _list_fub_contacts(
    workspace_id: uuid.UUID, db: AsyncSession, limit: int, offset: int
) -> FUBPeopleResponse:
    integration = await _get_fub_integration(workspace_id, db)

    client = FollowUpBossClient(integration.credentials["api_key"])
    try:
        data = await client.get_people(limit=limit, offset=offset)
        people = data.get("people", [])
        contacts: list[FUBContact] = []
        for p in people:
            phones: list[dict[str, str]] = p.get("phones", [])
            emails: list[dict[str, str]] = p.get("emails", [])
            contacts.append(
                FUBContact(
                    id=p["id"],
                    first_name=p.get("firstName"),
                    last_name=p.get("lastName"),
                    email=emails[0]["value"] if emails else None,
                    phone=phones[0]["value"] if phones else None,
                    stage=p.get("stage"),
                    tags=p.get("tags", []),
                    last_activity=p.get("lastActivity"),
                    source=p.get("source"),
                )
            )

        metadata: dict[str, int] = data.get("_metadata", {})
        total = metadata.get("total", len(contacts))

        return FUBPeopleResponse(
            contacts=contacts,
            total=total,
            has_more=(offset + limit) < total,
        )
    finally:
        await client.close()


async def _import_fub_contacts(
    *,
    workspace_id: uuid.UUID,
    db: AsyncSession,
    contact_ids: list[int] | None,
    import_all: bool,
) -> FUBImportResponse:
    integration = await _get_fub_integration(workspace_id, db)

    client = FollowUpBossClient(integration.credentials["api_key"])
    try:
        people_to_import: list[dict] = []  # type: ignore[type-arg]

        if import_all:
            people_to_import = await _fetch_all_fub_people(client)
        elif contact_ids:
            for cid in contact_ids:
                data = await client.get_person(cid)
                people_to_import.append(data.get("person", data))

        counts = {"imported": 0, "skipped": 0, "failed": 0}
        imported_contact_ids: list[int] = []
        for p in people_to_import:
            result, contact_id = await _import_single_fub_contact(db, workspace_id, p)
            counts[result] += 1
            if result == "imported" and contact_id is not None:
                imported_contact_ids.append(contact_id)

        # Auto-create drip campaign for imported contacts
        if imported_contact_ids:
            await auto_create_drip_for_imports(db, workspace_id, imported_contact_ids)

        await db.commit()
        return FUBImportResponse(**counts)
    finally:
        await client.close()


@workspace_router.get("/fub-contacts", response_model=FUBPeopleResponse)
async def get_fub_contacts_workspace(
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> FUBPeopleResponse:
    """Fetch Follow Up Boss contacts using the selected workspace's credentials."""
    return await _list_fub_contacts(workspace.id, db, limit, offset)


@workspace_router.post("/import-fub-contacts", response_model=FUBImportResponse)
async def import_fub_contacts_workspace(
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    contact_ids: list[int] | None = Body(None),
    import_all: bool = Body(False),
    api_key: str | None = Body(None, min_length=1),
) -> FUBImportResponse:
    """Import Follow Up Boss contacts into the selected workspace.

    When ``api_key`` is supplied (guided setup), it is stored on this workspace
    first so the import and later syncs use the selected workspace's credentials.
    """
    if api_key:
        await upsert_fub_integration(db, workspace.id, api_key)
        await db.flush()
    return await _import_fub_contacts(
        workspace_id=workspace.id,
        db=db,
        contact_ids=contact_ids,
        import_all=import_all,
    )


@router.get("/fub-contacts", response_model=FUBPeopleResponse, deprecated=True)
async def get_fub_contacts(
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> FUBPeopleResponse:
    """Legacy: fetch FUB contacts for the ``workspace_id`` query parameter."""
    return await _list_fub_contacts(workspace.id, db, limit, offset)


@router.post("/import-fub-contacts", response_model=FUBImportResponse, deprecated=True)
async def import_fub_contacts(
    http_request: Request,
    current_user: CurrentUser,
    db: DB,
    workspace_id: uuid.UUID = Body(...),
    contact_ids: list[int] | None = Body(None),
    import_all: bool = Body(False),
) -> FUBImportResponse:
    """Legacy: import FUB contacts into the body ``workspace_id``.

    Membership is enforced with the same check as workspace-scoped routes.
    """
    workspace = await get_workspace(http_request, workspace_id, current_user, db)
    return await _import_fub_contacts(
        workspace_id=workspace.id,
        db=db,
        contact_ids=contact_ids,
        import_all=import_all,
    )
