"""Service for managing prompt versions."""

import uuid
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import func, select, update
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
from app.services.exceptions import NotFoundError, ValidationError

logger = structlog.get_logger()

# Valid arm status transitions
ARM_STATUS_TRANSITIONS = {
    "active": ["paused", "eliminated"],
    "paused": ["active", "eliminated"],
    "eliminated": [],  # Terminal state
}


class PromptVersionService:
    """Service for prompt version management.

    Handles creating, activating, and rolling back prompt versions
    while maintaining version history and proper deactivation.
    """

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

    @staticmethod
    def _comparison_response(
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

        stats_service = BanditStatisticsService()
        comparison = stats_service.compare_versions(versions, winner_threshold=winner_threshold)

        version_items = [
            VersionComparisonItem(
                version_id=version.version_id,
                version_number=version.version_number,
                is_active=version.is_active,
                is_baseline=version.is_baseline,
                arm_status=version.arm_status,
                probability_best=version.probability_best,
                credible_interval_lower=version.credible_interval[0],
                credible_interval_upper=version.credible_interval[1],
                sample_size=version.sample_size,
                booking_rate=version.booking_rate,
                mean_estimate=version.mean_estimate,
            )
            for version in comparison.versions
        ]

        return VersionComparisonResponse(
            versions=version_items,
            winner_id=comparison.winner_id,
            winner_probability=comparison.winner_probability,
            recommended_action=comparison.recommended_action,
            min_samples_needed=comparison.min_samples_needed,
        )

    @staticmethod
    def _winner_response(
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

        stats_service = BanditStatisticsService()
        result = stats_service.detect_winner(versions, threshold=threshold)
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
        active_versions = await self.get_active_versions(db, agent_id)
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
            version = await self.create_version(
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
            activated, deactivated_id = await self.activate_version(db, version_id)
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
            new_version = await self.rollback_to_version(
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
            activated = await self.activate_for_testing(db, version_id)
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
            deactivated = await self.deactivate_version(db, version_id)
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
            paused = await self.pause_version(db, version_id)
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
            resumed = await self.resume_version(db, version_id)
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
            eliminated = await self.eliminate_version(db, version_id)
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
            updated = await self.update_arm_status(db, version_id, body.arm_status)
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
        active_versions = await self.get_active_versions(db, agent_id)
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
        active_versions = await self.get_active_versions(db, agent_id)
        return self._winner_response(active_versions, threshold)

    async def create_version(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
        *,
        system_prompt: str | None = None,
        initial_greeting: str | None = None,
        temperature: float | None = None,
        change_summary: str | None = None,
        created_by_id: int | None = None,
        is_baseline: bool = False,
        activate: bool = False,
        parent_version_id: uuid.UUID | None = None,
        traffic_percentage: int | None = None,
        experiment_id: uuid.UUID | None = None,
    ) -> PromptVersion:
        """Create a new prompt version, optionally snapshotting from current agent.

        Args:
            db: Database session
            agent_id: Agent to create version for
            system_prompt: Override prompt (if None, uses current agent prompt)
            initial_greeting: Override greeting
            temperature: Override temperature
            change_summary: Description of changes
            created_by_id: User who created this version
            is_baseline: Whether this is a control variant
            activate: Whether to activate immediately
            parent_version_id: Parent version (for rollbacks)

        Returns:
            Created PromptVersion
        """
        log = logger.bind(service="prompt_version", agent_id=str(agent_id))

        # Get agent to snapshot from if no overrides
        agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = agent_result.scalar_one_or_none()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Get next version number
        max_version_result = await db.execute(
            select(func.max(PromptVersion.version_number)).where(PromptVersion.agent_id == agent_id)
        )
        max_version = max_version_result.scalar() or 0
        next_version = max_version + 1

        # Use provided values or snapshot from agent
        final_prompt = system_prompt if system_prompt is not None else agent.system_prompt
        final_greeting = (
            initial_greeting if initial_greeting is not None else agent.initial_greeting
        )
        final_temp = temperature if temperature is not None else agent.temperature

        version = PromptVersion(
            agent_id=agent_id,
            system_prompt=final_prompt,
            initial_greeting=final_greeting,
            temperature=final_temp,
            version_number=next_version,
            change_summary=change_summary,
            created_by_id=created_by_id,
            is_baseline=is_baseline,
            parent_version_id=parent_version_id,
            is_active=False,
            traffic_percentage=traffic_percentage,
            experiment_id=experiment_id,
            arm_status="active",
        )

        db.add(version)
        await db.flush()

        log.info(
            "prompt_version_created",
            version_id=str(version.id),
            version_number=next_version,
        )

        if activate:
            await self._activate_version_internal(db, version, log)

        await db.commit()
        await db.refresh(version)

        return version

    async def activate_version(
        self,
        db: AsyncSession,
        version_id: uuid.UUID,
    ) -> tuple[PromptVersion, uuid.UUID | None]:
        """Activate a prompt version, deactivating any current active version.

        Args:
            db: Database session
            version_id: Version to activate

        Returns:
            Tuple of (activated version, deactivated version ID or None)
        """
        log = logger.bind(service="prompt_version", version_id=str(version_id))

        version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == version_id)
        )
        version = version_result.scalar_one_or_none()
        if not version:
            raise ValueError(f"PromptVersion {version_id} not found")

        deactivated_id = await self._activate_version_internal(db, version, log)

        await db.commit()
        await db.refresh(version)

        return version, deactivated_id

    async def _activate_version_internal(
        self,
        db: AsyncSession,
        version: PromptVersion,
        log: structlog.stdlib.BoundLogger,
    ) -> uuid.UUID | None:
        """Internal method to activate a version and deactivate current."""
        # Find and deactivate current active version
        deactivated_id: uuid.UUID | None = None

        current_active_result = await db.execute(
            select(PromptVersion).where(
                PromptVersion.agent_id == version.agent_id,
                PromptVersion.is_active.is_(True),
                PromptVersion.id != version.id,
            )
        )
        current_active = current_active_result.scalar_one_or_none()

        if current_active:
            current_active.is_active = False
            deactivated_id = current_active.id
            log.info(
                "deactivated_previous_version",
                previous_version_id=str(current_active.id),
            )

        # Activate the new version
        version.is_active = True
        version.activated_at = datetime.now(UTC)

        log.info(
            "version_activated",
            version_number=version.version_number,
        )

        return deactivated_id

    async def get_active_version(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
    ) -> PromptVersion | None:
        """Get the currently active prompt version for an agent.

        Args:
            db: Database session
            agent_id: Agent ID

        Returns:
            Active PromptVersion or None
        """
        result = await db.execute(
            select(PromptVersion).where(
                PromptVersion.agent_id == agent_id,
                PromptVersion.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def rollback_to_version(
        self,
        db: AsyncSession,
        version_id: uuid.UUID,
        *,
        created_by_id: int | None = None,
        change_summary: str | None = None,
    ) -> PromptVersion:
        """Create a new version based on an old version and activate it.

        This doesn't reactivate the old version directly, but creates a new
        version with the same content for proper audit trail.

        Args:
            db: Database session
            version_id: Version to rollback to
            created_by_id: User performing rollback
            change_summary: Override rollback summary

        Returns:
            New active PromptVersion
        """
        log = logger.bind(service="prompt_version", rollback_to=str(version_id))

        # Get the version to rollback to
        source_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == version_id)
        )
        source = source_result.scalar_one_or_none()
        if not source:
            raise ValueError(f"PromptVersion {version_id} not found")

        # Create new version copying the source
        summary = change_summary or f"Rollback to version {source.version_number}"

        new_version = await self.create_version(
            db=db,
            agent_id=source.agent_id,
            system_prompt=source.system_prompt,
            initial_greeting=source.initial_greeting,
            temperature=source.temperature,
            change_summary=summary,
            created_by_id=created_by_id,
            is_baseline=False,
            activate=True,
            parent_version_id=version_id,
        )

        log.info(
            "rollback_completed",
            new_version_id=str(new_version.id),
            new_version_number=new_version.version_number,
        )

        return new_version

    async def ensure_version_exists(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
        created_by_id: int | None = None,
    ) -> PromptVersion:
        """Ensure an agent has at least one prompt version.

        Creates an initial version if none exists.

        Args:
            db: Database session
            agent_id: Agent ID
            created_by_id: User to attribute creation to

        Returns:
            Active PromptVersion (existing or newly created)
        """
        active = await self.get_active_version(db, agent_id)
        if active:
            return active

        # Check if any version exists
        any_version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.agent_id == agent_id).limit(1)
        )
        existing = any_version_result.scalar_one_or_none()
        if existing:
            # Activate the first one found
            version, _ = await self.activate_version(db, existing.id)
            return version

        # Create initial version
        return await self.create_version(
            db=db,
            agent_id=agent_id,
            change_summary="Initial version",
            created_by_id=created_by_id,
            is_baseline=True,
            activate=True,
        )

    async def get_active_versions(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
    ) -> list[PromptVersion]:
        """Get all active prompt versions for an agent.

        For multi-variant A/B testing, returns all versions that are:
        - is_active=True
        - arm_status='active' (not paused or eliminated)

        Args:
            db: Database session
            agent_id: Agent ID

        Returns:
            List of active PromptVersions for bandit selection
        """
        result = await db.execute(
            select(PromptVersion)
            .where(
                PromptVersion.agent_id == agent_id,
                PromptVersion.is_active.is_(True),
                PromptVersion.arm_status == "active",
            )
            .order_by(PromptVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def activate_for_testing(
        self,
        db: AsyncSession,
        version_id: uuid.UUID,
    ) -> PromptVersion:
        """Activate a version for A/B testing without deactivating others.

        Unlike activate_version(), this method enables multi-variant testing
        by allowing multiple active versions simultaneously.

        Args:
            db: Database session
            version_id: Version to activate for testing

        Returns:
            Activated PromptVersion
        """
        log = logger.bind(service="prompt_version", version_id=str(version_id))

        version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == version_id)
        )
        version = version_result.scalar_one_or_none()
        if not version:
            raise ValueError(f"PromptVersion {version_id} not found")

        if version.arm_status == "eliminated":
            raise ValueError("Cannot activate eliminated version")

        version.is_active = True
        version.arm_status = "active"
        version.activated_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(version)

        log.info(
            "version_activated_for_testing",
            version_number=version.version_number,
        )

        return version

    async def deactivate_version(
        self,
        db: AsyncSession,
        version_id: uuid.UUID,
    ) -> PromptVersion:
        """Deactivate a version without eliminating it.

        Version can be reactivated later.

        Args:
            db: Database session
            version_id: Version to deactivate

        Returns:
            Deactivated PromptVersion
        """
        log = logger.bind(service="prompt_version", version_id=str(version_id))

        version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == version_id)
        )
        version = version_result.scalar_one_or_none()
        if not version:
            raise ValueError(f"PromptVersion {version_id} not found")

        version.is_active = False

        await db.commit()
        await db.refresh(version)

        log.info(
            "version_deactivated",
            version_number=version.version_number,
        )

        return version

    async def pause_version(
        self,
        db: AsyncSession,
        version_id: uuid.UUID,
    ) -> PromptVersion:
        """Pause a version (temporarily exclude from bandit selection).

        Paused versions stay is_active=True but arm_status='paused'
        so they're excluded from bandit selection but can be resumed.

        Args:
            db: Database session
            version_id: Version to pause

        Returns:
            Paused PromptVersion
        """
        log = logger.bind(service="prompt_version", version_id=str(version_id))

        version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == version_id)
        )
        version = version_result.scalar_one_or_none()
        if not version:
            raise ValueError(f"PromptVersion {version_id} not found")

        if version.arm_status == "eliminated":
            raise ValueError("Cannot pause eliminated version")

        version.arm_status = "paused"

        await db.commit()
        await db.refresh(version)

        log.info(
            "version_paused",
            version_number=version.version_number,
        )

        return version

    async def resume_version(
        self,
        db: AsyncSession,
        version_id: uuid.UUID,
    ) -> PromptVersion:
        """Resume a paused version.

        Args:
            db: Database session
            version_id: Version to resume

        Returns:
            Resumed PromptVersion
        """
        log = logger.bind(service="prompt_version", version_id=str(version_id))

        version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == version_id)
        )
        version = version_result.scalar_one_or_none()
        if not version:
            raise ValueError(f"PromptVersion {version_id} not found")

        if version.arm_status == "eliminated":
            raise ValueError("Cannot resume eliminated version")

        version.arm_status = "active"

        await db.commit()
        await db.refresh(version)

        log.info(
            "version_resumed",
            version_number=version.version_number,
        )

        return version

    async def eliminate_version(
        self,
        db: AsyncSession,
        version_id: uuid.UUID,
    ) -> PromptVersion:
        """Eliminate a version from A/B testing permanently.

        This is a terminal state - eliminated versions cannot be reactivated.
        Use this when statistical analysis shows a version is clearly inferior.

        Args:
            db: Database session
            version_id: Version to eliminate

        Returns:
            Eliminated PromptVersion
        """
        log = logger.bind(service="prompt_version", version_id=str(version_id))

        version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == version_id)
        )
        version = version_result.scalar_one_or_none()
        if not version:
            raise ValueError(f"PromptVersion {version_id} not found")

        version.is_active = False
        version.arm_status = "eliminated"

        await db.commit()
        await db.refresh(version)

        log.info(
            "version_eliminated",
            version_number=version.version_number,
        )

        return version

    async def update_arm_status(
        self,
        db: AsyncSession,
        version_id: uuid.UUID,
        new_status: str,
    ) -> PromptVersion:
        """Update the arm status with validation.

        Args:
            db: Database session
            version_id: Version to update
            new_status: New status (active, paused, eliminated)

        Returns:
            Updated PromptVersion

        Raises:
            ValueError: If transition is invalid
        """
        if new_status not in ARM_STATUS_TRANSITIONS:
            raise ValueError(f"Invalid arm status: {new_status}")

        version_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == version_id)
        )
        version = version_result.scalar_one_or_none()
        if not version:
            raise ValueError(f"PromptVersion {version_id} not found")

        current_status = version.arm_status
        valid_transitions = ARM_STATUS_TRANSITIONS.get(current_status, [])

        if new_status != current_status and new_status not in valid_transitions:
            raise ValueError(f"Cannot transition from {current_status} to {new_status}")

        if new_status == "active":
            return await self.resume_version(db, version_id)
        elif new_status == "paused":
            return await self.pause_version(db, version_id)
        elif new_status == "eliminated":
            return await self.eliminate_version(db, version_id)
        else:
            return version

    async def get_versions_for_experiment(
        self,
        db: AsyncSession,
        experiment_id: uuid.UUID,
    ) -> list[PromptVersion]:
        """Get all versions in an experiment.

        Args:
            db: Database session
            experiment_id: Experiment UUID

        Returns:
            List of PromptVersions in the experiment
        """
        result = await db.execute(
            select(PromptVersion)
            .where(PromptVersion.experiment_id == experiment_id)
            .order_by(PromptVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def create_experiment(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
        version_ids: list[uuid.UUID],
        experiment_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Group versions into an experiment.

        Args:
            db: Database session
            agent_id: Agent ID
            version_ids: List of version IDs to group
            experiment_id: Optional experiment UUID (generated if not provided)

        Returns:
            Experiment UUID
        """
        if not experiment_id:
            experiment_id = uuid.uuid4()

        await db.execute(
            update(PromptVersion)
            .where(
                PromptVersion.id.in_(version_ids),
                PromptVersion.agent_id == agent_id,
            )
            .values(experiment_id=experiment_id)
        )

        await db.commit()

        return experiment_id


# Convenience functions for use without instantiating service


async def get_active_prompt_version(
    db: AsyncSession,
    agent_id: uuid.UUID,
) -> PromptVersion | None:
    """Get the active prompt version for an agent."""
    service = PromptVersionService()
    return await service.get_active_version(db, agent_id)


async def create_prompt_version_on_change(
    db: AsyncSession,
    agent_id: uuid.UUID,
    *,
    system_prompt: str | None = None,
    initial_greeting: str | None = None,
    temperature: float | None = None,
    change_summary: str | None = None,
    created_by_id: int | None = None,
) -> PromptVersion:
    """Create and activate a new prompt version when agent is updated."""
    service = PromptVersionService()
    return await service.create_version(
        db=db,
        agent_id=agent_id,
        system_prompt=system_prompt,
        initial_greeting=initial_greeting,
        temperature=temperature,
        change_summary=change_summary,
        created_by_id=created_by_id,
        activate=True,
    )
