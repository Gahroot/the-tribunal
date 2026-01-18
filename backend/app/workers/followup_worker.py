"""Follow-up worker service for processing automated conversation follow-ups.

This background worker:
1. Polls for conversations with scheduled follow-ups
2. Generates AI follow-up messages
3. Sends messages via Telnyx SMS
4. Updates conversation follow-up tracking
"""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.conversation import Conversation
from app.services.ai.text_agent import generate_followup_message
from app.services.telephony.telnyx import TelnyxSMSService

logger = structlog.get_logger()

# Worker configuration
POLL_INTERVAL_SECONDS = 60  # Check every minute
MAX_FOLLOWUPS_PER_TICK = 10  # Limit batch size


class FollowupWorker:
    """Background worker for processing conversation follow-ups."""

    def __init__(self) -> None:
        """Initialize the follow-up worker."""
        self.running = False
        self.logger = logger.bind(component="followup_worker")
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the follow-up worker background task."""
        if self.running:
            self.logger.warning("Follow-up worker already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        self.logger.info("Follow-up worker started")

    async def stop(self) -> None:
        """Stop the follow-up worker."""
        self.running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.logger.info("Follow-up worker stopped")

    async def _run_loop(self) -> None:
        """Main worker loop that polls for follow-ups to process."""
        while self.running:
            try:
                await self._process_followups()
            except Exception:
                self.logger.exception("Error in follow-up worker loop")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _process_followups(self) -> None:
        """Process all pending follow-ups."""
        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC)

            # Query conversations that need follow-ups
            result = await db.execute(
                select(Conversation).where(
                    and_(
                        Conversation.followup_enabled.is_(True),
                        Conversation.next_followup_at.is_not(None),
                        Conversation.next_followup_at <= now,
                        Conversation.followup_count_sent < Conversation.followup_max_count,
                        Conversation.ai_enabled.is_(True),
                        # Only follow up if last message was outbound (no reply)
                        Conversation.last_message_direction == "outbound",
                    )
                )
                .order_by(Conversation.next_followup_at)
                .limit(MAX_FOLLOWUPS_PER_TICK)
            )
            conversations = result.scalars().all()

            if not conversations:
                return

            self.logger.info("Processing follow-ups", count=len(conversations))

            for conversation in conversations:
                try:
                    await self._process_conversation_followup(conversation, db)
                except Exception:
                    self.logger.exception(
                        "Error processing conversation follow-up",
                        conversation_id=str(conversation.id),
                    )

    async def _process_conversation_followup(
        self,
        conversation: Conversation,
        db: AsyncSession,
    ) -> None:
        """Process follow-up for a single conversation."""
        log = self.logger.bind(conversation_id=str(conversation.id))

        # Check for required API keys
        openai_key = settings.openai_api_key
        telnyx_key = settings.telnyx_api_key

        if not openai_key:
            log.warning("No OpenAI API key configured")
            return

        if not telnyx_key:
            log.warning("No Telnyx API key configured")
            return

        # Generate follow-up message
        message_body = await generate_followup_message(
            conversation=conversation,
            db=db,
            openai_api_key=openai_key,
        )

        if not message_body:
            log.warning("Failed to generate follow-up message")
            # Still schedule next attempt
            conversation.next_followup_at = datetime.now(UTC) + timedelta(
                hours=conversation.followup_delay_hours
            )
            await db.commit()
            return

        # Send the follow-up via SMS
        sms_service = TelnyxSMSService(telnyx_key)
        try:
            message = await sms_service.send_message(
                to_number=conversation.contact_phone,
                from_number=conversation.workspace_phone,
                body=message_body,
                db=db,
                workspace_id=conversation.workspace_id,
            )

            log.info(
                "Follow-up sent",
                message_id=str(message.id),
                followup_count=conversation.followup_count_sent + 1,
            )

            # Update follow-up tracking
            conversation.followup_count_sent += 1
            conversation.last_followup_at = datetime.now(UTC)

            # Schedule next follow-up if still within limits
            if conversation.followup_count_sent < conversation.followup_max_count:
                conversation.next_followup_at = datetime.now(UTC) + timedelta(
                    hours=conversation.followup_delay_hours
                )
            else:
                conversation.next_followup_at = None
                log.info("Max follow-ups reached", max_count=conversation.followup_max_count)

            await db.commit()

        except Exception as e:
            log.exception("Failed to send follow-up", error=str(e))
            # Still schedule next attempt, but with a delay
            conversation.next_followup_at = datetime.now(UTC) + timedelta(
                hours=conversation.followup_delay_hours
            )
            await db.commit()
        finally:
            await sms_service.close()


# Global worker instance
_followup_worker: FollowupWorker | None = None


async def start_followup_worker() -> FollowupWorker:
    """Start the global follow-up worker."""
    global _followup_worker
    if _followup_worker is None:
        _followup_worker = FollowupWorker()
        await _followup_worker.start()
    return _followup_worker


async def stop_followup_worker() -> None:
    """Stop the global follow-up worker."""
    global _followup_worker
    if _followup_worker:
        await _followup_worker.stop()
        _followup_worker = None


def get_followup_worker() -> FollowupWorker | None:
    """Get the global follow-up worker instance."""
    return _followup_worker
