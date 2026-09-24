"""Transcript analysis worker.

Polls voice call messages with a transcript but no sentiment analysis,
runs them through the transcript analysis service, and merges results
into the linked CallOutcome.signals dict.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.call_outcome import CallOutcome
from app.models.conversation import Message
from app.services.ai.bandit_reward_service import record_bandit_reward
from app.services.ai.call_judge import judge_call
from app.services.ai.transcript_analysis import analyze_transcript
from app.workers.base import BaseWorker, WorkerRegistry
from app.workers.retryable import RetryableWorker

BATCH_SIZE = 10


class TranscriptAnalysisWorker(RetryableWorker, BaseWorker):
    """Background worker that analyzes voice call transcripts."""

    POLL_INTERVAL_SECONDS = 30
    COMPONENT_NAME = "transcript_analysis_worker"
    # Each cycle pulls up to BATCH_SIZE messages and runs them through the
    # transcript analysis service concurrently; cap matches BATCH_SIZE so a
    # full batch can fan out without bursting beyond the OpenAI rate budget.
    MAX_CONCURRENCY = BATCH_SIZE
    max_retries = 3
    backoff_base_seconds = 2.0

    async def _process_items(self) -> None:
        await self.execute_with_retry(self._process_batch, item_key="transcript_batch")

    async def _process_batch(self) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Message)
                .join(CallOutcome, CallOutcome.message_id == Message.id)
                .options(selectinload(Message.call_outcome))
                .where(
                    Message.channel == "voice",
                    CallOutcome.signals["live_only"].astext.is_(None),
                    or_(
                        CallOutcome.signals["analyzed"].astext.is_(None),
                        CallOutcome.signals["judge"].astext.is_(None),
                        (
                            (CallOutcome.signals["judge"]["error"].astext == "evaluation_failed")
                            & (CallOutcome.signals["judge_attempts"].astext.in_(["1", "2"]))
                        ),
                        (
                            (CallOutcome.signals["judge"]["error"].astext == "no_transcript")
                            & Message.transcript.is_not(None)
                        ),
                    ),
                    or_(
                        Message.transcript.is_not(None),
                        CallOutcome.created_at < datetime.now(UTC) - timedelta(minutes=5),
                    ),
                )
                .limit(BATCH_SIZE)
            )
            items: list[tuple[Message, CallOutcome, str | None]] = [
                (m, m.call_outcome, m.transcript)
                for m in result.scalars().all()
                if m.call_outcome is not None
            ]

            if not items:
                return

            self.logger.info("transcript_analysis_batch", count=len(items))

            async def evaluate(
                transcript: str | None, analyzed: object, judged: object
            ) -> tuple[object, object]:
                if not transcript:
                    return None, None
                if isinstance(judged, dict) and judged.get("error") in (
                    "no_transcript",
                    "evaluation_failed",
                ):
                    judged = None
                analysis = await asyncio.gather(
                    analyze_transcript(transcript) if analyzed is None else asyncio.sleep(0),
                    judge_call(transcript) if judged is None else asyncio.sleep(0),
                    return_exceptions=True,
                )
                return analysis

            results = await asyncio.gather(
                *(
                    evaluate(
                        text,
                        None
                        if outcome.signals.get("analyzed") == "unavailable"
                        else outcome.signals.get("analyzed"),
                        outcome.signals.get("judge"),
                    )
                    for _, outcome, text in items
                ),
                return_exceptions=True,
            )
            for (msg, outcome, _text), evaluation_result in zip(items, results, strict=True):
                current: dict[str, object] = dict(outcome.signals or {})
                analysis: object
                judgment: object
                if isinstance(evaluation_result, BaseException):
                    self.logger.error("call_evaluation_failed", message_id=str(msg.id))
                    analysis, judgment = evaluation_result, evaluation_result
                else:
                    analysis, judgment = evaluation_result
                if "analyzed" not in current or (current["analyzed"] == "unavailable" and _text):
                    if isinstance(analysis, BaseException):
                        self.logger.error("transcript_analysis_failed", message_id=str(msg.id))
                        current["analyzed"] = "error"
                    elif isinstance(analysis, dict):
                        current.update(analysis)
                        current["analyzed"] = True
                    else:
                        current["analyzed"] = "unavailable"
                if "judge" not in current or (
                    isinstance(current["judge"], dict)
                    and current["judge"].get("error") in ("no_transcript", "evaluation_failed")
                    and _text
                ):
                    if isinstance(judgment, BaseException):
                        self.logger.error("call_judge_failed", message_id=str(msg.id))
                        attempts = current.get("judge_attempts")
                        current["judge_attempts"] = (attempts if type(attempts) is int else 0) + 1
                        current["judge"] = {"human_review": True, "error": "evaluation_failed"}
                    else:
                        current["judge"] = judgment or {
                            "human_review": True,
                            "error": "no_transcript",
                        }
                outcome.signals = current
            await db.commit()
            for _, outcome, _ in items:
                await record_bandit_reward(db, outcome)


_registry = WorkerRegistry(TranscriptAnalysisWorker)
start_transcript_analysis_worker = _registry.start
stop_transcript_analysis_worker = _registry.stop
get_transcript_analysis_worker = _registry.get
