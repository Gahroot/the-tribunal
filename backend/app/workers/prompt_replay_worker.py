"""Weekly privacy-preserving rubric replay of recent voice transcripts."""

from app.db.session import AsyncSessionLocal
from app.services.ai.prompt_scenario_suite import replay_weekly_sample
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
            verdicts = await replay_weekly_sample(db)
            # Free-text reasons can quote PII; only numeric results and IDs reach logs.
            for verdict in verdicts:
                self.logger.info(
                    "prompt_replay_verdict",
                    sample=verdict.name,
                    passed=verdict.success,
                    score=verdict.score,
                )
            self.logger.info(
                "prompt_replay_summary",
                sampled=len(verdicts),
                passed=sum(v.success for v in verdicts),
                mean_score=(sum(v.score for v in verdicts) / len(verdicts)) if verdicts else None,
            )


_registry = WorkerRegistry(PromptReplayWorker)
start_prompt_replay_worker = _registry.start
stop_prompt_replay_worker = _registry.stop
get_prompt_replay_worker = _registry.get
