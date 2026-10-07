"""Phone number management endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_workspace
from app.db.pagination import paginate
from app.models.phone_number import PhoneNumber
from app.models.workspace import Workspace
from app.schemas.phone_number import (
    EligibleVoiceAgentResponse,
    PaginatedPhoneNumbers,
    PhoneNumberInboundReadinessResponse,
    PhoneNumberInfoResponse,
    PhoneNumberPurchaseResponse,
    PhoneNumberResponse,
    PhoneNumbersInboundReadinessResponse,
    PhoneNumberTelephonyStatusResponse,
    PhoneNumberUpdate,
    PurchasePhoneNumberRequest,
    SearchPhoneNumbersRequest,
    TelephonyUnavailableDetail,
)
from app.services.telephony.availability import (
    TELEPHONY_ENABLED_MESSAGE,
    TELEPHONY_PROVIDER,
    TELEPHONY_SETUP_ACTION_HREF,
    TELEPHONY_SETUP_ACTION_LABEL,
    TELEPHONY_UNAVAILABLE_MESSAGE,
    get_telnyx_api_key_for_workspace,
    telephony_unavailable_detail,
)
from app.services.telephony.phone_number_assignment import (
    AgentAssignmentError,
    get_assignable_agent,
    get_inbound_voice_readiness,
    list_eligible_voice_agents,
    plan_purchase_assignment,
)
from app.services.telephony.telnyx import TelnyxSMSService

router = APIRouter()


_TELEPHONY_UNAVAILABLE_RESPONSE = {
    "model": TelephonyUnavailableDetail,
    "description": "Telephony provider credentials are not configured for this workspace.",
}


async def _get_telnyx_api_key_or_raise(db: DB, workspace_id: uuid.UUID) -> str:
    api_key = await get_telnyx_api_key_for_workspace(db, workspace_id)
    if api_key:
        return api_key

    raise HTTPException(
        status_code=status.HTTP_424_FAILED_DEPENDENCY,
        detail=telephony_unavailable_detail(),
    )


@router.get("", response_model=PaginatedPhoneNumbers)
async def list_phone_numbers(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    sms_enabled: bool | None = None,
    active_only: bool = True,
) -> PaginatedPhoneNumbers:
    """List phone numbers (shared across workspaces for now)."""
    # Phone numbers are shared across workspaces - don't filter by workspace_id
    query = select(PhoneNumber)

    if active_only:
        query = query.where(PhoneNumber.is_active.is_(True))

    if sms_enabled is not None:
        query = query.where(PhoneNumber.sms_enabled == sms_enabled)

    query = query.order_by(PhoneNumber.created_at.desc())
    result = await paginate(db, query, page=page, page_size=page_size)

    return PaginatedPhoneNumbers(**result.to_response(PhoneNumberResponse))


@router.get("/telephony-status", response_model=PhoneNumberTelephonyStatusResponse)
async def get_phone_number_telephony_status(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PhoneNumberTelephonyStatusResponse:
    """Return whether this workspace can perform Telnyx phone-number actions."""
    enabled = bool(await get_telnyx_api_key_for_workspace(db, workspace_id))
    return PhoneNumberTelephonyStatusResponse(
        enabled=enabled,
        provider=TELEPHONY_PROVIDER,
        message=TELEPHONY_ENABLED_MESSAGE if enabled else TELEPHONY_UNAVAILABLE_MESSAGE,
        action_label=None if enabled else TELEPHONY_SETUP_ACTION_LABEL,
        action_href=None if enabled else TELEPHONY_SETUP_ACTION_HREF,
    )


@router.get("/inbound-readiness", response_model=PhoneNumbersInboundReadinessResponse)
async def get_phone_numbers_inbound_readiness(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PhoneNumbersInboundReadinessResponse:
    """Report which of this workspace's numbers will have an agent answer inbound calls.

    Provider capability (``voice_enabled``) alone is not readiness: a number is
    ready only when its assigned agent is active, voice-capable, and owned by
    this workspace.
    """
    result = await db.execute(
        select(PhoneNumber)
        .where(PhoneNumber.workspace_id == workspace_id)
        .order_by(PhoneNumber.created_at.desc())
    )
    phones = list(result.scalars().all())
    eligible_agents = await list_eligible_voice_agents(db, workspace_id)
    readiness = await get_inbound_voice_readiness(db, workspace_id, phones, eligible_agents)
    return PhoneNumbersInboundReadinessResponse(
        eligible_agents=[EligibleVoiceAgentResponse.model_validate(a) for a in eligible_agents],
        numbers=[PhoneNumberInboundReadinessResponse.model_validate(r) for r in readiness],
    )


@router.get("/{phone_number_id}", response_model=PhoneNumberResponse)
async def get_phone_number(
    workspace_id: uuid.UUID,
    phone_number_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PhoneNumber:
    """Get a phone number by ID (shared across workspaces)."""
    # Phone numbers are shared across workspaces - don't filter by workspace_id
    result = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.id == phone_number_id,
        )
    )
    phone_number = result.scalar_one_or_none()

    if not phone_number:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not found",
        )

    return phone_number


@router.put("/{phone_number_id}", response_model=PhoneNumberResponse)
async def update_phone_number(
    workspace_id: uuid.UUID,
    phone_number_id: uuid.UUID,
    phone_number_in: PhoneNumberUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PhoneNumber:
    """Update a phone number."""
    result = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.id == phone_number_id,
            PhoneNumber.workspace_id == workspace_id,
        )
    )
    phone_number = result.scalar_one_or_none()

    if not phone_number:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not found",
        )

    update_data = phone_number_in.model_dump(exclude_unset=True)
    new_agent_id = update_data.get("assigned_agent_id")
    if new_agent_id is not None:
        try:
            await get_assignable_agent(db, workspace_id, new_agent_id)
        except AgentAssignmentError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
    for field, value in update_data.items():
        setattr(phone_number, field, value)

    await db.commit()
    await db.refresh(phone_number)

    return phone_number


@router.post(
    "/search",
    response_model=list[PhoneNumberInfoResponse],
    responses={status.HTTP_424_FAILED_DEPENDENCY: _TELEPHONY_UNAVAILABLE_RESPONSE},
)
async def search_phone_numbers(
    workspace_id: uuid.UUID,
    request_data: SearchPhoneNumbersRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> list[PhoneNumberInfoResponse]:
    """Search for available phone numbers to purchase."""
    telnyx_api_key = await _get_telnyx_api_key_or_raise(db, workspace_id)

    service = TelnyxSMSService(telnyx_api_key)
    try:
        numbers = await service.search_phone_numbers(
            country=request_data.country,
            area_code=request_data.area_code,
            contains=request_data.contains,
            limit=request_data.limit,
        )
        return [
            PhoneNumberInfoResponse(
                id=n.id,
                phone_number=n.phone_number,
                friendly_name=n.friendly_name,
                capabilities=n.capabilities,
            )
            for n in numbers
        ]
    finally:
        await service.close()


@router.post(
    "/purchase",
    response_model=PhoneNumberPurchaseResponse,
    responses={status.HTTP_424_FAILED_DEPENDENCY: _TELEPHONY_UNAVAILABLE_RESPONSE},
)
async def purchase_phone_number(
    workspace_id: uuid.UUID,
    request_data: PurchasePhoneNumberRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PhoneNumberPurchaseResponse:
    """Purchase a phone number from Telnyx and assign its inbound agent.

    The agent assignment is validated before the paid purchase so an invalid
    agent never leaves a bought-but-misconfigured number behind.
    """
    telnyx_api_key = await _get_telnyx_api_key_or_raise(db, workspace_id)

    try:
        plan = await plan_purchase_assignment(
            db,
            workspace_id,
            requested_agent_id=request_data.assigned_agent_id,
            skip_agent_assignment=request_data.skip_agent_assignment,
        )
    except AgentAssignmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    service = TelnyxSMSService(telnyx_api_key)
    try:
        # Purchase from Telnyx
        purchased = await service.purchase_phone_number(request_data.phone_number)

        # Create database record
        phone_number = PhoneNumber(
            workspace_id=workspace_id,
            phone_number=purchased.phone_number,
            telnyx_phone_number_id=purchased.id,
            sms_enabled=True,
            voice_enabled=True,
            is_active=True,
            assigned_agent_id=plan.agent_id,
        )
        db.add(phone_number)
        await db.commit()
        await db.refresh(phone_number)

        [readiness] = await get_inbound_voice_readiness(db, workspace_id, [phone_number])
        return PhoneNumberPurchaseResponse.model_validate(
            {
                **PhoneNumberResponse.model_validate(phone_number).model_dump(),
                "agent_assignment": plan.source,
                "inbound_voice": PhoneNumberInboundReadinessResponse.model_validate(readiness),
            }
        )
    finally:
        await service.close()


@router.delete(
    "/{phone_number_id}",
    responses={status.HTTP_424_FAILED_DEPENDENCY: _TELEPHONY_UNAVAILABLE_RESPONSE},
)
async def release_phone_number(
    workspace_id: uuid.UUID,
    phone_number_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, bool]:
    """Release a phone number back to Telnyx."""
    result = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.id == phone_number_id,
            PhoneNumber.workspace_id == workspace_id,
        )
    )
    phone_number = result.scalar_one_or_none()

    if not phone_number:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not found",
        )

    telnyx_api_key = await _get_telnyx_api_key_or_raise(db, workspace_id)

    # Release from Telnyx if we have the provider ID
    if phone_number.telnyx_phone_number_id:
        service = TelnyxSMSService(telnyx_api_key)
        try:
            await service.release_phone_number(phone_number.telnyx_phone_number_id)
        finally:
            await service.close()

    # Delete from database
    await db.delete(phone_number)
    await db.commit()

    return {"success": True}


@router.post(
    "/sync",
    responses={status.HTTP_424_FAILED_DEPENDENCY: _TELEPHONY_UNAVAILABLE_RESPONSE},
)
async def sync_phone_numbers(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, int]:
    """Sync phone numbers from Telnyx account."""
    telnyx_api_key = await _get_telnyx_api_key_or_raise(db, workspace_id)

    service = TelnyxSMSService(telnyx_api_key)
    try:
        telnyx_numbers = await service.list_phone_numbers()
    finally:
        await service.close()

    synced = 0
    for tn in telnyx_numbers:
        # Check if phone number already exists globally (unique constraint is on phone_number)
        result = await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.phone_number == tn.phone_number,
            )
        )
        existing = result.scalar_one_or_none()

        if not existing:
            # Phone number doesn't exist anywhere - create it for this workspace
            phone_number = PhoneNumber(
                workspace_id=workspace_id,
                phone_number=tn.phone_number,
                friendly_name=tn.friendly_name,
                telnyx_phone_number_id=tn.id,
                sms_enabled=tn.capabilities.get("sms", False) if tn.capabilities else False,
                voice_enabled=tn.capabilities.get("voice", False) if tn.capabilities else False,
                is_active=True,
            )
            db.add(phone_number)
            synced += 1
        elif existing.workspace_id != workspace_id:
            # Phone number exists in another workspace - skip (shared phone numbers)
            pass

    await db.commit()
    return {"synced": synced}
