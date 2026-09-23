"""Background workers registry.

Provides centralized lifecycle management and metadata for all background
workers. ``WORKER_SPECS`` is the canonical startup registry; ``ALL_REGISTRIES``
is kept as a compatibility projection for code that only needs lifecycle hooks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import structlog

from app.core.config import Settings, settings

# Import all worker registries
from app.workers.ad_library_discovery_worker import (
    _registry as ad_library_discovery_registry,
)
from app.workers.ad_monitor_worker import _registry as ad_monitor_registry
from app.workers.approval_worker import _registry as approval_registry
from app.workers.auth_rate_limit_cleanup_worker import (
    _registry as auth_rate_limit_cleanup_registry,
)
from app.workers.automation_worker import _registry as automation_registry
from app.workers.base import BaseWorker
from app.workers.campaign_worker import _registry as campaign_registry
from app.workers.drip_campaign_worker import _registry as drip_campaign_registry
from app.workers.enrichment_worker import _registry as enrichment_registry
from app.workers.experiment_evaluation_worker import _registry as experiment_evaluation_registry
from app.workers.followup_worker import _registry as followup_registry
from app.workers.message_test_worker import _registry as message_test_registry
from app.workers.never_booked_worker import _registry as never_booked_registry
from app.workers.noshow_reengagement_worker import _registry as noshow_reengagement_registry
from app.workers.nudge_worker import _registry as nudge_registry
from app.workers.operator_report_worker import _registry as operator_report_registry
from app.workers.outbound_auto_draft_worker import (
    _registry as outbound_auto_draft_registry,
)
from app.workers.outbound_improvement_suggestion_worker import (
    _registry as outbound_improvement_suggestion_registry,
)
from app.workers.prompt_improvement_worker import _registry as prompt_improvement_registry
from app.workers.prompt_stats_worker import _registry as prompt_stats_registry
from app.workers.prospect_enrichment_worker import (
    _registry as prospect_enrichment_registry,
)
from app.workers.prospect_promotion_worker import (
    _registry as prospect_promotion_registry,
)
from app.workers.reminder_worker import _registry as reminder_registry
from app.workers.speed_to_lead_worker import _registry as speed_to_lead_registry
from app.workers.transcript_analysis_worker import _registry as transcript_analysis_registry
from app.workers.voice_campaign_worker import _registry as voice_campaign_registry
from app.workers.web_people_discovery_worker import (
    _registry as web_people_discovery_registry,
)

logger = structlog.get_logger()
WorkerEnabledPredicate = Callable[[Settings], bool]


class WorkerRegistryProtocol(Protocol):
    """Lifecycle surface implemented by worker registries."""

    async def start(self) -> BaseWorker:
        """Start and return the singleton worker instance."""
        ...

    async def stop(self) -> None:
        """Stop the singleton worker instance if running."""
        ...

    def get(self) -> BaseWorker | None:
        """Return the running worker instance, if any."""
        ...


def _always_enabled(_settings: Settings) -> bool:
    """Default per-worker enablement predicate."""
    return True


class _LazyBlockRegistry:
    """Lazy proxy to a worker registry that lives in an extracted block package.

    The Reviews & Reputation workers live in the mountable ``tribunal-reviews``
    block, whose package import pulls ``app.core_api`` (which in turn imports
    ``app.workers.base``). Importing the block's registries at *this* module's
    load time would re-enter a half-initialized ``app.core_api`` /
    ``tribunal_reviews`` cycle. Resolving them on first lifecycle call (during
    the app lifespan, long after imports settle) breaks that cycle while keeping
    the static :data:`WORKER_SPECS` list intact.
    """

    __slots__ = ("_module", "_attr", "_target")

    def __init__(self, module: str, attr: str) -> None:
        self._module = module
        self._attr = attr
        self._target: WorkerRegistryProtocol | None = None

    def _resolve(self) -> WorkerRegistryProtocol:
        if self._target is None:
            import importlib

            self._target = getattr(importlib.import_module(self._module), self._attr)
        return self._target

    async def start(self) -> BaseWorker:
        return await self._resolve().start()

    async def stop(self) -> None:
        await self._resolve().stop()

    def get(self) -> BaseWorker | None:
        return self._resolve().get()


# Reviews & Reputation workers live in the extracted ``tribunal-reviews`` block;
# proxied lazily to avoid an import cycle through ``app.core_api`` at load time.
review_request_registry: WorkerRegistryProtocol = _LazyBlockRegistry(
    "tribunal_reviews", "review_request_registry"
)
reputation_registry: WorkerRegistryProtocol = _LazyBlockRegistry(
    "tribunal_reviews", "reputation_registry"
)


@dataclass(frozen=True, slots=True)
class WorkerHealthMetadata:
    """Readiness metadata for a worker heartbeat.

    ``heartbeat_required`` means a running instance must keep its Redis heartbeat
    fresh for ``/readyz`` to stay green. ``heartbeat_dependency`` records the
    external dependency used to store/read the health signal.
    """

    component_name: str
    heartbeat_required: bool = True
    heartbeat_dependency: str = "redis"


@dataclass(frozen=True, slots=True)
class WorkerSpec:
    """Operational metadata and lifecycle hook for a background worker."""

    name: str
    registry: WorkerRegistryProtocol
    dependencies: tuple[str, ...]
    enabled: WorkerEnabledPredicate = _always_enabled
    enabled_setting: str = "always"
    health: WorkerHealthMetadata | None = None

    def is_enabled(self, runtime_settings: Settings | None = None) -> bool:
        """Return whether this worker should start for ``runtime_settings``."""
        return self.enabled(runtime_settings or settings)

    @property
    def health_metadata(self) -> WorkerHealthMetadata:
        """Return explicit health metadata, defaulting to the worker name."""
        return self.health or WorkerHealthMetadata(component_name=self.name)


# All worker specs in startup order. Dependencies document runtime resources the
# worker reaches during normal polling; they are not startup preconditions unless
# the worker's own code treats them that way.
WORKER_SPECS: tuple[WorkerSpec, ...] = (
    WorkerSpec(
        name="campaign_worker",
        registry=campaign_registry,
        dependencies=("postgres", "redis", "text_message_provider", "openai"),
    ),
    WorkerSpec(
        name="voice_campaign_worker",
        registry=voice_campaign_registry,
        dependencies=("postgres", "redis", "telnyx_voice", "openai"),
    ),
    WorkerSpec(
        name="followup_worker",
        registry=followup_registry,
        dependencies=("postgres", "openai", "text_message_provider"),
    ),
    WorkerSpec(
        name="reminder_worker",
        registry=reminder_registry,
        dependencies=("postgres", "text_message_provider"),
    ),
    WorkerSpec(
        name="message_test_worker",
        registry=message_test_registry,
        dependencies=("postgres", "redis", "text_message_provider"),
    ),
    WorkerSpec(
        name="reputation_worker",
        registry=reputation_registry,
        dependencies=("postgres", "redis"),
    ),
    WorkerSpec(
        name="enrichment_worker",
        registry=enrichment_registry,
        dependencies=("postgres", "website_http", "openai"),
    ),
    WorkerSpec(
        name="prompt_stats",
        registry=prompt_stats_registry,
        dependencies=("postgres",),
    ),
    WorkerSpec(
        name="prompt_improvement",
        registry=prompt_improvement_registry,
        dependencies=("postgres", "openai"),
    ),
    WorkerSpec(
        name="outbound_improvement_suggestions",
        registry=outbound_improvement_suggestion_registry,
        dependencies=("postgres", "openai"),
    ),
    WorkerSpec(
        name="experiment_evaluation",
        registry=experiment_evaluation_registry,
        dependencies=("postgres",),
    ),
    WorkerSpec(
        name="automation_worker",
        registry=automation_registry,
        dependencies=("postgres", "text_message_provider", "approval_gate"),
    ),
    WorkerSpec(
        name="noshow_reengagement_worker",
        registry=noshow_reengagement_registry,
        dependencies=("postgres", "text_message_provider"),
    ),
    WorkerSpec(
        name="review_request_worker",
        registry=review_request_registry,
        dependencies=("postgres", "text_message_provider"),
    ),
    WorkerSpec(
        name="never_booked_worker",
        registry=never_booked_registry,
        dependencies=("postgres", "text_message_provider"),
    ),
    WorkerSpec(
        name="nudge_worker",
        registry=nudge_registry,
        dependencies=("postgres", "telnyx_sms", "expo_push"),
    ),
    WorkerSpec(
        name="approval_worker",
        registry=approval_registry,
        dependencies=("postgres", "text_message_provider", "expo_push", "calcom"),
    ),
    WorkerSpec(
        name="drip_campaign_worker",
        registry=drip_campaign_registry,
        dependencies=("postgres", "text_message_provider"),
    ),
    WorkerSpec(
        name="transcript_analysis_worker",
        registry=transcript_analysis_registry,
        dependencies=("postgres", "openai"),
    ),
    WorkerSpec(
        name="auth_rate_limit_cleanup",
        registry=auth_rate_limit_cleanup_registry,
        dependencies=("postgres",),
    ),
    WorkerSpec(
        name="ad_library_discovery_worker",
        registry=ad_library_discovery_registry,
        dependencies=("postgres", "redis", "meta_ad_library"),
        enabled=lambda s: s.ad_library_discovery_worker_enabled,
        enabled_setting="ad_library_discovery_worker_enabled",
    ),
    WorkerSpec(
        name="prospect_enrichment_worker",
        registry=prospect_enrichment_registry,
        dependencies=("postgres", "website_http", "openai"),
        enabled=lambda s: s.prospect_enrichment_worker_enabled,
        enabled_setting="prospect_enrichment_worker_enabled",
    ),
    WorkerSpec(
        name="prospect_promotion_worker",
        registry=prospect_promotion_registry,
        dependencies=("postgres",),
        enabled=lambda s: s.prospect_promotion_worker_enabled,
        enabled_setting="prospect_promotion_worker_enabled",
    ),
    WorkerSpec(
        name="ad_monitor_worker",
        registry=ad_monitor_registry,
        dependencies=("postgres",),
        enabled=lambda s: s.ad_monitor_worker_enabled,
        enabled_setting="ad_monitor_worker_enabled",
    ),
    WorkerSpec(
        name="web_people_discovery_worker",
        registry=web_people_discovery_registry,
        dependencies=("postgres", "website_http"),
        enabled=lambda s: s.web_people_discovery_worker_enabled,
        enabled_setting="web_people_discovery_worker_enabled",
    ),
    # Per-workspace opt-in lives in workspace settings (outbound_autopilot.enabled,
    # default off); the worker itself is always started and cheap when idle.
    WorkerSpec(
        name="outbound_auto_draft_worker",
        registry=outbound_auto_draft_registry,
        dependencies=("postgres",),
    ),
    # Proactive operator reporting over iMessage. Always started and cheap when
    # idle; per-workspace opt-in lives in the autonomy mandate's operator_report.
    WorkerSpec(
        name="operator_report_worker",
        registry=operator_report_registry,
        dependencies=("postgres", "text_message_provider"),
        enabled=lambda s: s.operator_report_worker_enabled,
        enabled_setting="operator_report_worker_enabled",
    ),
    # Instant speed-to-lead first touch (parallel voice attempt + "calling you
    # now" SMS) queued by the lead-creation hooks; cheap when the queue is dry.
    WorkerSpec(
        name="speed_to_lead_worker",
        registry=speed_to_lead_registry,
        dependencies=("postgres", "redis", "telnyx_voice", "text_message_provider"),
        enabled=lambda s: s.speed_to_lead_worker_enabled,
        enabled_setting="speed_to_lead_worker_enabled",
    ),
)

# Compatibility projection for callers that only need the registries.
ALL_REGISTRIES: list[WorkerRegistryProtocol] = [spec.registry for spec in WORKER_SPECS]


def enabled_worker_specs(runtime_settings: Settings | None = None) -> list[WorkerSpec]:
    """Return enabled workers in startup order."""
    resolved_settings = runtime_settings or settings
    return [spec for spec in WORKER_SPECS if spec.is_enabled(resolved_settings)]


async def start_all_workers() -> None:
    """Start all enabled background workers in order."""
    log = logger.bind(context="worker_lifecycle")
    for spec in enabled_worker_specs(settings):
        worker = await spec.registry.start()
        name = worker.COMPONENT_NAME or worker.__class__.__name__.lower()
        health = spec.health_metadata
        log.info(
            "worker_started",
            worker=name,
            worker_spec=spec.name,
            dependencies=spec.dependencies,
            enabled_setting=spec.enabled_setting,
            heartbeat_component=health.component_name,
            heartbeat_required=health.heartbeat_required,
            heartbeat_dependency=health.heartbeat_dependency,
        )


async def stop_all_workers() -> None:
    """Stop all enabled background workers in reverse order."""
    log = logger.bind(context="worker_lifecycle")
    for spec in reversed(enabled_worker_specs(settings)):
        instance = spec.registry.get()
        name = (
            instance.COMPONENT_NAME or instance.__class__.__name__.lower()
            if instance
            else spec.name
        )
        health = spec.health_metadata
        await spec.registry.stop()
        log.info(
            "worker_stopped",
            worker=name,
            worker_spec=spec.name,
            enabled_setting=spec.enabled_setting,
            heartbeat_component=health.component_name,
            heartbeat_required=health.heartbeat_required,
            heartbeat_dependency=health.heartbeat_dependency,
        )


__all__ = [
    "start_all_workers",
    "stop_all_workers",
    "ALL_REGISTRIES",
    "WORKER_SPECS",
    "WorkerHealthMetadata",
    "WorkerRegistryProtocol",
    "WorkerSpec",
    "enabled_worker_specs",
]
