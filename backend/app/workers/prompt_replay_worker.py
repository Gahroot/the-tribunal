"""Weekly privacy-preserving rubric replay of recent voice transcripts."""

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.prompt_version import PromptVersion
from app.services.ai.prompt_scenario_suite import replay_recent_calls
from app.workers.base import BaseWorker, WorkerRegistry
from app.workers.retryable import RetryableWorker


class PromptReplayWorker(RetryableWorker, BaseWorker):
    POLL_INTERVAL_SECONDS = 7 * 86400
    COMPONENT_NAME = "prompt_replay"
    MAX_CONCURRENCY = 1
    max_retries = 3
    backoff_base_seconds = 2.0

    async def _process_items(self) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PromptVersion)
                .where(PromptVersion.is_active.is_(True))
                .order_by(func.random())
                .limit(50)
            )
            versions = list(result.scalars())
            sample_size = max(1, 50 // len(versions)) if versions else 1
            for version in versions:
                try:
                    verdicts = await replay_recent_calls(db, version, sample_size=sample_size)
                    self.logger.info(
                        "prompt_replay_summary",
                        version_id=str(version.id),
                        sampled=len(verdicts),
                        passed=sum(v.success for v in verdicts),
                        mean_score=(sum(v.score for v in verdicts) / len(verdicts))
                        if verdicts
                        else None,
                    )
                except Exception:
                    self.logger.exception("prompt_replay_failed", version_id=str(version.id))


_registry = WorkerRegistry(PromptReplayWorker)
start_prompt_replay_worker = _registry.start
stop_prompt_replay_worker = _registry.stop
get_prompt_replay_worker = _registry.get
