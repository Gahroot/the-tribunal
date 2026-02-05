"""Campaign post-mortem intelligence report endpoints."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.db.pagination import paginate
from app.models.campaign import Campaign
from app.models.campaign_report import CampaignReport
from app.models.workspace import Workspace
from app.services.ai.campaign_report_service import CampaignReportService

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class CampaignReportResponse(BaseModel):
    """Full campaign report response."""

    id: uuid.UUID
    campaign_id: uuid.UUID
    workspace_id: uuid.UUID
    campaign_name: str | None = None
    campaign_type: str | None = None

    status: str
    error_message: str | None = None

    metrics_snapshot: dict[str, Any] | None = None
    executive_summary: str | None = None
    key_findings: list[dict[str, Any]] | None = None
    what_worked: list[dict[str, Any]] | None = None
    what_didnt_work: list[dict[str, Any]] | None = None
    recommendations: list[dict[str, Any]] | None = None
    segment_analysis: list[dict[str, Any]] | None = None
    timing_analysis: dict[str, Any] | None = None
    prompt_performance: list[dict[str, Any]] | None = None

    generated_suggestion_ids: list[str] | None = None

    generated_at: str | None = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class CampaignReportSummary(BaseModel):
    """Lighter summary for list views."""

    id: uuid.UUID
    campaign_id: uuid.UUID
    campaign_name: str | None = None
    campaign_type: str | None = None
    status: str
    executive_summary: str | None = None
    generated_at: str | None = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class CampaignReportListResponse(BaseModel):
    """Paginated report list."""

    items: list[CampaignReportSummary]
    total: int
    page: int
    page_size: int
    pages: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=CampaignReportListResponse)
async def list_reports(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> CampaignReportListResponse:
    """List campaign reports for the workspace."""
    query = (
        select(CampaignReport)
        .where(CampaignReport.workspace_id == workspace_id)
        .order_by(CampaignReport.created_at.desc())
    )

    if status_filter:
        query = query.where(CampaignReport.status == status_filter)

    result = await paginate(db, query, page=page, page_size=page_size)

    # Gather campaign names for the summaries
    campaign_ids = [r.campaign_id for r in result.items]
    campaign_info: dict[uuid.UUID, tuple[str, str]] = {}
    if campaign_ids:
        camp_result = await db.execute(
            select(Campaign.id, Campaign.name, Campaign.campaign_type).where(
                Campaign.id.in_(campaign_ids)
            )
        )
        for row in camp_result.all():
            campaign_info[row.id] = (row.name, row.campaign_type)

    return CampaignReportListResponse(
        items=[
            CampaignReportSummary(
                id=r.id,
                campaign_id=r.campaign_id,
                campaign_name=campaign_info.get(r.campaign_id, (None, None))[0],
                campaign_type=campaign_info.get(r.campaign_id, (None, None))[1],
                status=r.status,
                executive_summary=r.executive_summary,
                generated_at=r.generated_at.isoformat() if r.generated_at else None,
                created_at=r.created_at.isoformat(),
            )
            for r in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        pages=result.pages,
    )


@router.get("/count")
async def get_report_count(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, int]:
    """Get count of completed reports for the workspace."""
    result = await db.execute(
        select(func.count(CampaignReport.id)).where(
            CampaignReport.workspace_id == workspace_id,
            CampaignReport.status == "completed",
        )
    )
    count = result.scalar() or 0
    return {"report_count": count}


@router.get("/campaign/{campaign_id}", response_model=CampaignReportResponse)
async def get_report_by_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> CampaignReportResponse:
    """Get report by campaign ID."""
    result = await db.execute(
        select(CampaignReport).where(
            CampaignReport.campaign_id == campaign_id,
            CampaignReport.workspace_id == workspace_id,
        )
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found for this campaign",
        )

    return await _build_report_response(db, report)


@router.get("/{report_id}", response_model=CampaignReportResponse)
async def get_report(
    workspace_id: uuid.UUID,
    report_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> CampaignReportResponse:
    """Get a full campaign report."""
    result = await db.execute(
        select(CampaignReport).where(
            CampaignReport.id == report_id,
            CampaignReport.workspace_id == workspace_id,
        )
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    return await _build_report_response(db, report)


@router.post(
    "/campaign/{campaign_id}/generate",
    response_model=CampaignReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_report(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> CampaignReportResponse:
    """Trigger report generation for a campaign."""
    # Verify campaign belongs to workspace
    camp_result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.workspace_id == workspace_id,
        )
    )
    campaign = camp_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    try:
        service = CampaignReportService()
        report = await service.generate_report(db, campaign_id)
        await db.commit()
        return await _build_report_response(db, report)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


async def _build_report_response(
    db: DB, report: CampaignReport
) -> CampaignReportResponse:
    """Build a full report response with joined campaign info."""
    camp_result = await db.execute(
        select(Campaign.name, Campaign.campaign_type).where(
            Campaign.id == report.campaign_id
        )
    )
    camp_row = camp_result.one_or_none()

    return CampaignReportResponse(
        id=report.id,
        campaign_id=report.campaign_id,
        workspace_id=report.workspace_id,
        campaign_name=camp_row.name if camp_row else None,
        campaign_type=camp_row.campaign_type if camp_row else None,
        status=report.status,
        error_message=report.error_message,
        metrics_snapshot=report.metrics_snapshot,
        executive_summary=report.executive_summary,
        key_findings=report.key_findings,
        what_worked=report.what_worked,
        what_didnt_work=report.what_didnt_work,
        recommendations=report.recommendations,
        segment_analysis=report.segment_analysis,
        timing_analysis=report.timing_analysis,
        prompt_performance=report.prompt_performance,
        generated_suggestion_ids=report.generated_suggestion_ids,
        generated_at=report.generated_at.isoformat() if report.generated_at else None,
        created_at=report.created_at.isoformat(),
    )
