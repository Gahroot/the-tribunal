"""Transcript analysis worker.

Polls for voice call messages that have a transcript but no sentiment
analysis yet, runs them through the transcript analysis service, and
merges the results into the linked CallOutcome.signals dict.
"""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.call_outcome import CallOutcome
from app.models.conversation import Message
from app.services.ai.transcript_analysis import analyze_transcript
from app.workers.base import BaseWorker, WorkerRegistry

BATCH_SIZE = 10


class TranscriptAnalysisWorker(BaseWorker):
    """Background worker that analyzes voice call transcripts."""

    POLL_INTERVAL_SECONDS = 30
    COMPONENT_NAME = "transcript_analysis_worker"

    async def _process_items(self) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Message)
                .join(CallOutcome, CallOutcome.message_id == Message.id)
                .options(selectinload(Message.call_outcome))
                .where(
                    Message.channel == "voice",
                    Message.transcript.is_not(None),
                    CallOutcome.signals["analyzed"].astext.is_(None),
                )
                .limit(BATCH_SIZE)
            )
            messages = result.scalars().all()

            if not messages:
                return

            self.logger.info("transcript_analysis_batch", count=len(messages))

            for msg in messages:
                outcome = msg.call_outcome
                if outcome is None or not msg.transcript:
                    continue

                log = self.logger.bind(message_id=str(msg.id))
                current: dict[str, object] = dict(outcome.signals or {})
                try:
                    analysis = await analyze_transcript(msg.transcript)
                    current.update(analysis)
                    current["analyzed"] = True
                    log.info("transcript_analyzed", sentiment=analysis.get("sentiment"))
                except Exception:
                    log.exception("transcript_analysis_failed")
                    current["analyzed"] = "error"

                outcome.signals = current

            await db.commit()


_registry = WorkerRegistry(TranscriptAnalysisWorker)
start_transcript_analysis_worker = _registry.start
stop_transcript_analysis_worker = _registry.stop
get_transcript_analysis_worker = _registry.get
