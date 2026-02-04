"""Service for managing prompt versions."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.prompt_version import PromptVersion

logger = structlog.get_logger()


class PromptVersionService:
    """Service for prompt version management.

    Handles creating, activating, and rolling back prompt versions
    while maintaining version history and proper deactivation.
    """

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
            select(func.max(PromptVersion.version_number)).where(
                PromptVersion.agent_id == agent_id
            )
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
            select(PromptVersion)
            .where(PromptVersion.agent_id == agent_id)
            .limit(1)
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
