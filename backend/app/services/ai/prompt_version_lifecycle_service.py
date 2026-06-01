"""Workspace-scoped prompt version lifecycle, stats, and comparison service."""

import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.pagination import paginate
from app.models.agent import Agent
from app.models.prompt_version import PromptVersion
from app.models.prompt_version_stats import PromptVersionStats
from app.schemas.prompt_version import (
    ArmStatusUpdate,
    PromptVersionActivateResponse,
    PromptVersionCreate,
    PromptVersionListResponse,
    PromptVersionResponse,
    PromptVersionRollbackResponse,
    PromptVersionStatsResponse,
    PromptVersionUpdate,
    VersionComparisonItem,
    VersionComparisonResponse,
    WinnerDetectionResponse,
)
from app.services.ai.bandit_statistics import BanditStatisticsService
from app.services.ai.prompt_version_service import PromptVersionService
from app.services.exceptions import NotFoundError, ValidationError


class PromptVersionLifecycleService:
    """Domain service for workspace-scoped prompt version operations.

    The lower-level :class:`PromptVersionService` owns prompt-version persistence
    primitives. This service owns API-facing lifecycle rules, workspace scoping,
    aggregate statistics, and statistical comparison response mapping.
    """

    def __init__(
        self,
        prompt_versions: PromptVersionService | None = None,
        statistics_factory: Callable[[], BanditStatisticsService] | None = None,
    ) -> None:
        self._prompt_versions = prompt_versions or PromptVersionService()
        self._statistics_factory = statistics_factory or BanditStatisticsService

    async def _ensure_agent_in_workspace(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None:
        """Raise if an agent is not owned by the requested workspace."""
        result = await db.execute(
            select(Agent.id).where(
                Agent.id == agent_id,
                Agent.workspace_id == workspace_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError("Agent not found")

    async def _get_version_for_agent(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> PromptVersion:
        """Fetch a prompt version scoped to an agent or raise NotFoundError."""
        result = await db.execute(
            select(PromptVersion).where(
                PromptVersion.id == version_id,
                PromptVersion.agent_id == agent_id,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise NotFoundError("Prompt version not found")
        return version

    @staticmethod
    def _stats_response(
        version: PromptVersion,
        *,
        total_calls: int | None,
        completed_calls: int | None,
        failed_calls: int | None,
        appointments_booked: int | None,
        leads_qualified: int | None,
        avg_duration_seconds: float | None,
        avg_quality_score: float | None,
        min_date: date | None,
        max_date: date | None,
    ) -> PromptVersionStatsResponse:
        """Build a stats response from aggregate stats and version counters."""
        call_count = total_calls or 0
        completed_count = completed_calls or 0
        appointments = appointments_booked or 0
        qualified = leads_qualified or 0

        booking_rate = (appointments / completed_count) if completed_count > 0 else None
        qualification_rate = (qualified / completed_count) if completed_count > 0 else None
        completion_rate = (completed_count / call_count) if call_count > 0 else None

        if call_count == 0:
            call_count = version.total_calls
            completed_count = version.successful_calls
            appointments = version.booked_appointments
            booking_rate = (appointments / completed_count) if completed_count > 0 else None
            completion_rate = (completed_count / call_count) if call_count > 0 else None

        return PromptVersionStatsResponse(
            prompt_version_id=version.id,
            version_number=version.version_number,
            is_active=version.is_active,
            is_baseline=version.is_baseline,
            total_calls=call_count,
            completed_calls=completed_count,
            failed_calls=failed_calls or 0,
            appointments_booked=appointments,
            leads_qualified=qualified,
            booking_rate=booking_rate,
            qualification_rate=qualification_rate,
            completion_rate=completion_rate,
            avg_duration_seconds=avg_duration_seconds,
            avg_quality_score=avg_quality_score,
            stats_from=datetime.combine(min_date, datetime.min.time()) if min_date else None,
            stats_to=datetime.combine(max_date, datetime.min.time()) if max_date else None,
        )

    def _comparison_response(
        self,
        versions: list[PromptVersion],
        winner_threshold: float,
    ) -> VersionComparisonResponse:
        """Run statistical comparison and map it to the API response schema."""
        if not versions:
            return VersionComparisonResponse(
                versions=[],
                winner_id=None,
                winner_probability=None,
                recommended_action="no_versions",
                min_samples_needed=0,
            )

        comparison = self._statistics_factory().compare_versions(
            versions,
            winner_threshold=winner_threshold,
        )

        version_items = [
            VersionComparisonItem(
                version_id=version_stats.version_id,
                version_number=version_stats.version_number,
                is_active=version_stats.is_active,
                is_baseline=version_stats.is_baseline,
                arm_status=version_stats.arm_status,
                probability_best=version_stats.probability_best,
                credible_interval_lower=version_stats.credible_interval[0],
                credible_interval_upper=version_stats.credible_interval[1],
                sample_size=version_stats.sample_size,
                booking_rate=version_stats.booking_rate,
                mean_estimate=version_stats.mean_estimate,
            )
            for version_stats in comparison.versions
        ]

        return VersionComparisonResponse(
            versions=version_items,
            winner_id=comparison.winner_id,
            winner_probability=comparison.winner_probability,
            recommended_action=comparison.recommended_action,
            min_samples_needed=comparison.min_samples_needed,
        )

    def _winner_response(
        self,
        versions: list[PromptVersion],
        threshold: float,
    ) -> WinnerDetectionResponse:
        """Run winner detection and map it to the API response schema."""
        if not versions:
            return WinnerDetectionResponse(
                winner_id=None,
                winner_probability=None,
                confidence_threshold=threshold,
                is_conclusive=False,
                message="No active versions to compare",
            )

        result = self._statistics_factory().detect_winner(versions, threshold=threshold)
        return WinnerDetectionResponse(
            winner_id=result.winner_id,
            winner_probability=result.winner_probability,
            confidence_threshold=result.confidence_threshold,
            is_conclusive=result.is_conclusive,
            message=result.message,
        )

    async def list_versions(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> PromptVersionListResponse:
        """List prompt versions for an agent in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)

        query = (
            select(PromptVersion)
            .where(PromptVersion.agent_id == agent_id)
            .order_by(PromptVersion.version_number.desc())
        )
        result = await paginate(db, query, page=page, page_size=page_size)
        return PromptVersionListResponse(**result.to_response(PromptVersionResponse))

    async def list_active_versions(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> list[PromptVersionResponse]:
        """List active prompt versions for an agent in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        active_versions = await self._prompt_versions.get_active_versions(db, agent_id)
        return [PromptVersionResponse.model_validate(version) for version in active_versions]

    async def create_version_for_agent(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        body: PromptVersionCreate,
        *,
        created_by_id: int | None,
    ) -> PromptVersionResponse:
        """Create a new prompt version for an agent in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        try:
            version = await self._prompt_versions.create_version(
                db=db,
                agent_id=agent_id,
                system_prompt=body.system_prompt,
                initial_greeting=body.initial_greeting,
                temperature=body.temperature,
                change_summary=body.change_summary,
                created_by_id=created_by_id,
                is_baseline=body.is_baseline,
                activate=False,
                traffic_percentage=body.traffic_percentage,
                experiment_id=body.experiment_id,
            )
        except ValueError as exc:
            raise NotFoundError(str(exc)) from exc
        return PromptVersionResponse.model_validate(version)

    async def get_version(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> PromptVersionResponse:
        """Get one prompt version for an agent in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        version = await self._get_version_for_agent(db, agent_id, version_id)
        return PromptVersionResponse.model_validate(version)

    async def update_version(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
        body: PromptVersionUpdate,
    ) -> PromptVersionResponse:
        """Update mutable prompt version metadata."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        version = await self._get_version_for_agent(db, agent_id, version_id)

        if body.change_summary is not None:
            version.change_summary = body.change_summary
        if body.is_baseline is not None:
            version.is_baseline = body.is_baseline
        if body.traffic_percentage is not None:
            version.traffic_percentage = body.traffic_percentage
        if body.experiment_id is not None:
            version.experiment_id = body.experiment_id

        await db.commit()
        await db.refresh(version)
        return PromptVersionResponse.model_validate(version)

    async def activate_version_for_agent(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> PromptVersionActivateResponse:
        """Activate a prompt version for an agent in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        await self._get_version_for_agent(db, agent_id, version_id)
        try:
            activated, deactivated_id = await self._prompt_versions.activate_version(db, version_id)
        except ValueError as exc:
            raise NotFoundError(str(exc)) from exc
        return PromptVersionActivateResponse(
            activated_version=PromptVersionResponse.model_validate(activated),
            deactivated_version_id=deactivated_id,
        )

    async def rollback_agent_to_version(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
        *,
        created_by_id: int | None,
    ) -> PromptVersionRollbackResponse:
        """Rollback an agent by creating a new active version from an old version."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        await self._get_version_for_agent(db, agent_id, version_id)
        try:
            new_version = await self._prompt_versions.rollback_to_version(
                db=db,
                version_id=version_id,
                created_by_id=created_by_id,
            )
        except ValueError as exc:
            raise NotFoundError(str(exc)) from exc
        return PromptVersionRollbackResponse(
            new_version=PromptVersionResponse.model_validate(new_version),
            rolled_back_from=version_id,
        )

    async def get_version_stats(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
        *,
        days: int,
    ) -> PromptVersionStatsResponse:
        """Get aggregate performance stats for one prompt version."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        version = await self._get_version_for_agent(db, agent_id, version_id)

        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        stats_result = await db.execute(
            select(
                func.sum(PromptVersionStats.total_calls).label("total_calls"),
                func.sum(PromptVersionStats.completed_calls).label("completed_calls"),
                func.sum(PromptVersionStats.failed_calls).label("failed_calls"),
                func.sum(PromptVersionStats.appointments_booked).label("appointments_booked"),
                func.sum(PromptVersionStats.leads_qualified).label("leads_qualified"),
                func.avg(PromptVersionStats.avg_duration_seconds).label("avg_duration"),
                func.avg(PromptVersionStats.avg_quality_score).label("avg_quality"),
                func.min(PromptVersionStats.stat_date).label("min_date"),
                func.max(PromptVersionStats.stat_date).label("max_date"),
            ).where(
                PromptVersionStats.prompt_version_id == version_id,
                PromptVersionStats.stat_date >= start_date,
                PromptVersionStats.stat_date <= end_date,
            )
        )
        stats_row = stats_result.one()
        return self._stats_response(
            version,
            total_calls=stats_row.total_calls,
            completed_calls=stats_row.completed_calls,
            failed_calls=stats_row.failed_calls,
            appointments_booked=stats_row.appointments_booked,
            leads_qualified=stats_row.leads_qualified,
            avg_duration_seconds=stats_row.avg_duration,
            avg_quality_score=stats_row.avg_quality,
            min_date=stats_row.min_date,
            max_date=stats_row.max_date,
        )

    async def activate_for_testing_in_workspace(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> PromptVersionResponse:
        """Activate a version for multi-variant testing in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        await self._get_version_for_agent(db, agent_id, version_id)
        try:
            activated = await self._prompt_versions.activate_for_testing(db, version_id)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return PromptVersionResponse.model_validate(activated)

    async def deactivate_version_in_workspace(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> PromptVersionResponse:
        """Deactivate a prompt version in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        await self._get_version_for_agent(db, agent_id, version_id)
        try:
            deactivated = await self._prompt_versions.deactivate_version(db, version_id)
        except ValueError as exc:
            raise NotFoundError(str(exc)) from exc
        return PromptVersionResponse.model_validate(deactivated)

    async def pause_version_in_workspace(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> PromptVersionResponse:
        """Pause a prompt version in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        await self._get_version_for_agent(db, agent_id, version_id)
        try:
            paused = await self._prompt_versions.pause_version(db, version_id)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return PromptVersionResponse.model_validate(paused)

    async def resume_version_in_workspace(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> PromptVersionResponse:
        """Resume a prompt version in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        await self._get_version_for_agent(db, agent_id, version_id)
        try:
            resumed = await self._prompt_versions.resume_version(db, version_id)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return PromptVersionResponse.model_validate(resumed)

    async def eliminate_version_in_workspace(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> PromptVersionResponse:
        """Eliminate a prompt version from testing in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        await self._get_version_for_agent(db, agent_id, version_id)
        try:
            eliminated = await self._prompt_versions.eliminate_version(db, version_id)
        except ValueError as exc:
            raise NotFoundError(str(exc)) from exc
        return PromptVersionResponse.model_validate(eliminated)

    async def update_arm_status_in_workspace(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        version_id: uuid.UUID,
        body: ArmStatusUpdate,
    ) -> PromptVersionResponse:
        """Update a prompt version arm status in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        await self._get_version_for_agent(db, agent_id, version_id)
        try:
            updated = await self._prompt_versions.update_arm_status(db, version_id, body.arm_status)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return PromptVersionResponse.model_validate(updated)

    async def compare_versions_in_workspace(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        *,
        winner_threshold: float,
    ) -> VersionComparisonResponse:
        """Compare active prompt versions for an agent in a workspace."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        active_versions = await self._prompt_versions.get_active_versions(db, agent_id)
        return self._comparison_response(active_versions, winner_threshold)

    async def detect_winner_in_workspace(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        *,
        threshold: float,
    ) -> WinnerDetectionResponse:
        """Detect whether an agent has a conclusive prompt-version winner."""
        await self._ensure_agent_in_workspace(db, agent_id, workspace_id)
        active_versions = await self._prompt_versions.get_active_versions(db, agent_id)
        return self._winner_response(active_versions, threshold)
