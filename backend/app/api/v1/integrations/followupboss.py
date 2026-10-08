"""Follow Up Boss sync endpoints.

These routes were previously colocated with the realtor onboarding flow in
``app/api/v1/realtor.py``. They are mounted under the same public URL
(``/realtor/...``) for backwards-compatibility with the frontend.
"""

import uuid
from typing import Annotated, NoReturn

import httpx
import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser, WorkspaceAdminAccess, get_workspace
from app.core.encryption import hash_phone, hash_value
from app.models.contact import Contact
from app.models.workspace import Workspace, WorkspaceIntegration
from app.schemas.followupboss import (
    FUBConnectionStatus,
    FUBConnectRequest,
    FUBContact,
    FUBImportFailure,
    FUBImportResponse,
    FUBPeopleResponse,
    FUBVerifyResponse,
)
from app.services.followupboss import FollowUpBossClient
from app.services.onboarding.credentials import store_followupboss_credentials
from app.services.reactivation.drip_bootstrap import auto_create_drip_for_imports
from app.utils.phone import normalize_phone_safe

router = APIRouter()
workspace_router = APIRouter()
logger = structlog.get_logger()

# Cap on per-row failure details returned to the client.
MAX_REPORTED_FAILURES = 50


def _fub_source(fub_id: object) -> str:
    """Stable per-person source marker; also the primary re-import dedupe key."""
    return f"Follow Up Boss (ID: {fub_id})"


def _raise_for_fub_error(exc: httpx.HTTPError, *, stored_key: bool) -> NoReturn:
    """Translate a Follow Up Boss transport/HTTP error into a client error.

    Never mutates the saved connection: a rejected or unreachable key leaves the
    workspace's existing integration exactly as it was.
    """
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403):
        if stored_key:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Follow Up Boss rejected the saved API key. "
                    "Reconnect Follow Up Boss and try again."
                ),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Follow Up Boss rejected this API key. Double-check it and try again.",
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Couldn't reach Follow Up Boss. Nothing was changed; please try again.",
    ) from exc


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


def _first_value(items: object) -> str | None:
    """Return the first non-empty ``value`` of a FUB phones/emails list."""
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict):
            value = item.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


async def _import_single_fub_contact(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    fub_person: dict,  # type: ignore[type-arg]
) -> tuple[str, int | None, str | None]:
    """Import a single FUB contact.

    Returns ``(status, contact_id, failure_reason)`` where status is one of
    ``"imported"``, ``"skipped"`` or ``"failed"``.

    Dedupe uses the FUB-ID source marker plus the deterministic lookup hashes
    (``phone``/``email`` are Fernet-encrypted, so comparing them directly never
    matches). That makes re-running the same import a no-op instead of
    duplicating every lead.
    """
    fub_id = fub_person.get("id")
    raw_phone = _first_value(fub_person.get("phones"))
    email = _first_value(fub_person.get("emails"))
    phone = normalize_phone_safe(raw_phone) if raw_phone else None

    conditions = []
    if fub_id is not None:
        conditions.append(Contact.source == _fub_source(fub_id))
    if phone:
        conditions.append(Contact.phone_hash == hash_phone(phone))
    if email:
        conditions.append(Contact.email_hash == hash_value(email))

    if conditions:
        existing = await db.execute(
            select(Contact.id)
            .where(Contact.workspace_id == workspace_id, or_(*conditions))
            .limit(1)
        )
        existing_id = existing.scalar_one_or_none()
        if existing_id is not None:
            return "skipped", existing_id, None

    # Contacts require a phone number (SMS reactivation is the whole point).
    if not phone:
        reason = "invalid_phone" if raw_phone else "missing_phone"
        return "failed", None, reason

    contact = Contact(
        workspace_id=workspace_id,
        first_name=(fub_person.get("firstName") or "")[:100],
        last_name=(fub_person.get("lastName") or "")[:100] or None,
        phone_number=phone,
        phone_hash=hash_phone(phone),
        email=email,
        email_hash=hash_value(email) if email else None,
        source=_fub_source(fub_id if fub_id is not None else "unknown"),
        notes=fub_person.get("background"),
    )
    try:
        # One bad row rolls back only its savepoint, not the whole import.
        async with db.begin_nested():
            db.add(contact)
            await db.flush()
    except Exception as exc:
        logger.warning(
            "fub_contact_import_failed",
            workspace_id=str(workspace_id),
            fub_id=fub_id,
            error_type=type(exc).__name__,
        )
        return "failed", None, "save_failed"
    return "imported", contact.id, None


def _connection_status(integration: WorkspaceIntegration | None) -> FUBConnectionStatus:
    if integration is None or not integration.is_active:
        return FUBConnectionStatus(connected=False)
    credentials = integration.safe_credentials()
    if not credentials or not credentials.get("api_key"):
        return FUBConnectionStatus(connected=False)
    account_name = credentials.get("account_name")
    return FUBConnectionStatus(
        connected=True,
        account_name=account_name if isinstance(account_name, str) else None,
    )


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
    auto_enroll_drip: bool = True,
) -> FUBImportResponse:
    integration = await _get_fub_integration(workspace_id, db)

    client = FollowUpBossClient(integration.credentials["api_key"])
    try:
        people_to_import: list[dict] = []  # type: ignore[type-arg]

        # Fetch everything before writing anything: a FUB failure mid-fetch
        # imports nothing, so a retry starts clean.
        try:
            if import_all:
                people_to_import = await _fetch_all_fub_people(client)
            elif contact_ids:
                for cid in contact_ids:
                    data = await client.get_person(cid)
                    people_to_import.append(data.get("person", data))
        except httpx.HTTPError as exc:
            logger.warning(
                "fub_import_fetch_failed",
                workspace_id=str(workspace_id),
                error_type=type(exc).__name__,
            )
            _raise_for_fub_error(exc, stored_key=True)

        counts = {"imported": 0, "skipped": 0, "failed": 0}
        failures: list[FUBImportFailure] = []
        imported_contact_ids: list[int] = []
        audience_ids: set[int] = set()
        for p in people_to_import:
            result, contact_id, reason = await _import_single_fub_contact(db, workspace_id, p)
            counts[result] += 1
            if contact_id is not None:
                audience_ids.add(contact_id)
            if result == "imported" and contact_id is not None:
                imported_contact_ids.append(contact_id)
            elif result == "failed" and len(failures) < MAX_REPORTED_FAILURES:
                fub_id = p.get("id")
                failures.append(
                    FUBImportFailure(
                        fub_id=fub_id if isinstance(fub_id, int) else None,
                        reason=reason or "unknown",
                    )
                )

        # Auto-create drip campaign for imported contacts
        if auto_enroll_drip and imported_contact_ids:
            await auto_create_drip_for_imports(db, workspace_id, imported_contact_ids)

        await db.commit()
        logger.info(
            "fub_import_completed",
            workspace_id=str(workspace_id),
            **counts,
        )
        return FUBImportResponse(**counts, failures=failures, contact_ids=sorted(audience_ids))
    finally:
        await client.close()


@workspace_router.get("/fub-connection", response_model=FUBConnectionStatus)
async def get_fub_connection(
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> FUBConnectionStatus:
    """Report whether the selected workspace has a saved FUB connection.

    Reads only the stored encrypted integration (no call to Follow Up Boss), so
    a FUB outage can't make a previously valid connection look disconnected.
    """
    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace.id,
            WorkspaceIntegration.integration_type == "followupboss",
        )
    )
    return _connection_status(result.scalar_one_or_none())


@workspace_router.put("/fub-connection", response_model=FUBConnectionStatus)
async def connect_fub(
    body: FUBConnectRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: WorkspaceAdminAccess,
) -> FUBConnectionStatus:
    """Verify a FUB API key, then save it (encrypted) on the selected workspace.

    The key is only written after Follow Up Boss accepts it. A rejected key
    (422) or an unreachable FUB (502) writes nothing, so an existing valid
    connection is preserved. Returns ``connected`` only after the commit.
    """
    api_key = body.api_key.strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Paste your Follow Up Boss API key first.",
        )

    client = FollowUpBossClient(api_key)
    try:
        me = await client.verify()
    except httpx.HTTPError as exc:
        logger.info(
            "fub_connect_verify_failed",
            workspace_id=str(workspace.id),
            error_type=type(exc).__name__,
        )
        _raise_for_fub_error(exc, stored_key=False)
    finally:
        await client.close()

    name = me.get("name") if isinstance(me, dict) else None
    account_name = name if isinstance(name, str) and name else None
    try:
        integration = await store_followupboss_credentials(
            db, workspace.id, api_key, account_name=account_name
        )
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error(
            "fub_integration_save_failed",
            workspace_id=str(workspace.id),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Your key works, but we couldn't save the connection. Please try again.",
        ) from exc
    logger.info(
        "fub_integration_connected",
        workspace_id=str(workspace.id),
        user_id=current_user.id,
    )
    return FUBConnectionStatus(
        connected=bool(integration.is_active),
        account_name=account_name,
    )


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
    auto_enroll_drip: bool = Body(True),
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
        auto_enroll_drip=auto_enroll_drip,
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
