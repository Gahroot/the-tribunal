"""Realtor self-serve onboarding endpoints."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.db.scope import apply_workspace_scope
from app.models.appointment import Appointment, AppointmentStatus
from app.models.contact import Contact
from app.models.conversation import Conversation, Message, MessageDirection
from app.models.workspace import Workspace
from app.schemas.realtor import (
    FUBCampaignRequest,
    FUBCampaignResponse,
    ParseCalcomUrlRequest,
    ParseCalcomUrlResponse,
    RealtorCampaignResponse,
    RealtorOnboardRequest,
    RealtorOnboardResponse,
    VerifyCalcomResponse,
)
from app.services.onboarding.credentials import get_workspace_calcom_api_key
from app.services.onboarding.exceptions import OnboardingServiceError
from app.services.onboarding.external_checks import (
    resolve_calcom_event_type_id,
    verify_calcom_api_key,
)
from app.services.onboarding.fub_launch import launch_fub_campaign
from app.services.onboarding.route_responses import (
    parse_calcom_url_response,
    raise_onboarding_http_error,
    realtor_campaign_response,
    realtor_onboard_response,
    verify_calcom_response,
)
from app.services.onboarding.workspace_setup import (
    RealtorCampaignInput,
    RealtorOnboardingInput,
    complete_realtor_onboarding,
    get_user_workspace,
    launch_realtor_campaign_from_csv,
)

router = APIRouter()
workspace_router = APIRouter()


class RealtorStatsResponse(BaseModel):
    """Realtor dashboard stats."""

    leads_uploaded: int
    texts_sent: int
    replies_received: int
    appointments_booked: int


@workspace_router.get("/stats", response_model=RealtorStatsResponse)
async def get_realtor_stats(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> RealtorStatsResponse:
    """Get realtor dashboard statistics for a workspace."""
    leads_result = await db.execute(
        apply_workspace_scope(
            select(func.count()).select_from(Contact),
            Contact,
            workspace_id,
        )
    )
    leads_uploaded = leads_result.scalar() or 0

    workspace_conversations = apply_workspace_scope(
        select(Conversation.id), Conversation, workspace_id
    )

    texts_sent_result = await db.execute(
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id.in_(workspace_conversations),
            Message.direction == MessageDirection.OUTBOUND,
        )
    )
    texts_sent = texts_sent_result.scalar() or 0

    replies_result = await db.execute(
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id.in_(workspace_conversations),
            Message.direction == MessageDirection.INBOUND,
        )
    )
    replies_received = replies_result.scalar() or 0

    appointments_result = await db.execute(
        apply_workspace_scope(
            select(func.count()).select_from(Appointment),
            Appointment,
            workspace_id,
        ).where(
            Appointment.status.in_(
                [
                    AppointmentStatus.SCHEDULED,
                    AppointmentStatus.COMPLETED,
                ]
            ),
        )
    )
    appointments_booked = appointments_result.scalar() or 0

    return RealtorStatsResponse(
        leads_uploaded=leads_uploaded,
        texts_sent=texts_sent,
        replies_received=replies_received,
        appointments_booked=appointments_booked,
    )


async def _run_realtor_onboarding(
    *,
    request: RealtorOnboardRequest,
    current_user: CurrentUser,
    db: DB,
    workspace_id: uuid.UUID | None,
) -> RealtorOnboardResponse:
    try:
        result = await complete_realtor_onboarding(
            db=db,
            current_user_id=current_user.id,
            workspace_id=workspace_id,
            request=RealtorOnboardingInput(
                calcom_api_key=request.calcom_api_key,
                calcom_event_type_id=request.calcom_event_type_id,
                area_code=request.area_code,
                fub_api_key=request.fub_api_key,
            ),
        )
    except OnboardingServiceError as exc:
        raise_onboarding_http_error(exc)
    return realtor_onboard_response(result)


@workspace_router.post(
    "/onboard",
    response_model=RealtorOnboardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def realtor_onboard_workspace(
    request: RealtorOnboardRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> RealtorOnboardResponse:
    """Complete realtor onboarding for an explicitly selected workspace.

    Idempotent: retrying reuses the workspace's realtor agent and SMS number.
    """
    return await _run_realtor_onboarding(
        request=request, current_user=current_user, db=db, workspace_id=workspace.id
    )


@router.post(
    "/onboard",
    response_model=RealtorOnboardResponse,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
)
async def realtor_onboard(
    request: RealtorOnboardRequest,
    current_user: CurrentUser,
    db: DB,
) -> RealtorOnboardResponse:
    """Legacy: onboard the caller's default workspace.

    Use ``POST /workspaces/{workspace_id}/realtor/onboard`` to target a workspace.
    """
    return await _run_realtor_onboarding(
        request=request, current_user=current_user, db=db, workspace_id=None
    )


async def _read_csv_upload(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file.",
        )

    try:
        return await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {exc!s}",
        ) from exc


async def _run_realtor_campaign(
    *,
    current_user: CurrentUser,
    db: DB,
    file: UploadFile,
    skip_duplicates: bool,
    campaign_name: str | None,
    workspace_id: uuid.UUID | None,
) -> RealtorCampaignResponse:
    content = await _read_csv_upload(file)
    try:
        result = await launch_realtor_campaign_from_csv(
            db=db,
            current_user_id=current_user.id,
            workspace_id=workspace_id,
            request=RealtorCampaignInput(
                file_content=content,
                skip_duplicates=skip_duplicates,
                campaign_name=campaign_name,
            ),
        )
    except OnboardingServiceError as exc:
        raise_onboarding_http_error(exc)
    return realtor_campaign_response(result)


@workspace_router.post(
    "/campaigns",
    response_model=RealtorCampaignResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_realtor_campaign_workspace(
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    file: UploadFile,
    skip_duplicates: bool = Form(default=True),
    campaign_name: str | None = Form(default=None),
) -> RealtorCampaignResponse:
    """Upload a CSV and launch a realtor campaign in an explicitly selected workspace."""
    return await _run_realtor_campaign(
        current_user=current_user,
        db=db,
        file=file,
        skip_duplicates=skip_duplicates,
        campaign_name=campaign_name,
        workspace_id=workspace.id,
    )


@workspace_router.post("/campaigns/fub", response_model=FUBCampaignResponse)
async def launch_realtor_fub_campaign(
    request: FUBCampaignRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> FUBCampaignResponse:
    """Launch or recover the workspace's guided FUB campaign without reimporting."""
    result = await launch_fub_campaign(db, workspace.id, request.contact_ids, request.campaign_name)
    return FUBCampaignResponse(**asdict(result))


@router.post(
    "/campaigns",
    response_model=RealtorCampaignResponse,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
)
async def create_realtor_campaign(
    current_user: CurrentUser,
    db: DB,
    file: UploadFile,
    skip_duplicates: bool = Form(default=True),
    campaign_name: str | None = Form(default=None),
) -> RealtorCampaignResponse:
    """Legacy: launch a realtor campaign in the caller's default workspace.

    Use ``POST /workspaces/{workspace_id}/realtor/campaigns`` to target a workspace.
    """
    return await _run_realtor_campaign(
        current_user=current_user,
        db=db,
        file=file,
        skip_duplicates=skip_duplicates,
        campaign_name=campaign_name,
        workspace_id=None,
    )


def _missing_calcom_key() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            "No Cal.com API key found for this workspace. "
            "Provide one via the api_key field or connect Cal.com in Settings first."
        ),
    )


@workspace_router.post("/parse-calcom-url", response_model=ParseCalcomUrlResponse)
async def parse_calcom_url_workspace(
    request: ParseCalcomUrlRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> ParseCalcomUrlResponse:
    """Resolve a Cal.com booking URL using the selected workspace's credentials.

    An in-form ``api_key`` wins because it is the key onboarding will store for
    this workspace; the workspace's saved key is the fallback.
    """
    try:
        api_key = request.api_key or await get_workspace_calcom_api_key(workspace.id, db)
        if not api_key:
            raise _missing_calcom_key()
        result = await resolve_calcom_event_type_id(url=request.url, api_key=api_key)
    except OnboardingServiceError as exc:
        raise_onboarding_http_error(exc)
    return parse_calcom_url_response(result)


@router.post("/parse-calcom-url", response_model=ParseCalcomUrlResponse, deprecated=True)
async def parse_calcom_url(
    request: ParseCalcomUrlRequest,
    current_user: CurrentUser,
    db: DB,
) -> ParseCalcomUrlResponse:
    """Legacy: parse a Cal.com booking URL using the default workspace's key."""
    try:
        workspace = await get_user_workspace(current_user.id, db)
        api_key = await get_workspace_calcom_api_key(workspace.id, db)
        if api_key is None:
            api_key = request.api_key
        if not api_key:
            raise _missing_calcom_key()
        result = await resolve_calcom_event_type_id(url=request.url, api_key=api_key)
    except OnboardingServiceError as exc:
        raise_onboarding_http_error(exc)
    return parse_calcom_url_response(result)


@router.get("/verify-calcom", response_model=VerifyCalcomResponse)
async def verify_calcom(
    current_user: CurrentUser,
    api_key: str = Query(..., min_length=1, description="Cal.com API key to verify"),
) -> VerifyCalcomResponse:
    """Verify a Cal.com API key by calling the /me endpoint."""
    try:
        result = await verify_calcom_api_key(api_key)
    except OnboardingServiceError as exc:
        raise_onboarding_http_error(exc)
    return verify_calcom_response(result)
