"""BaseCampaignWorker — RetryableWorker contract.

``BaseCampaignWorker`` is abstract; we instantiate a minimal concrete
subclass to exercise the mixin behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import QueryableAttribute

import app.workers.base_campaign_worker as base_campaign_worker_module
from app.models.campaign import CampaignStatus, CampaignType
from app.workers.base import BaseWorker
from app.workers.base_campaign_worker import BaseCampaignWorker
from app.workers.retryable import RetryableWorker
from tests.workers._retryable_helpers import wire_worker_for_retry_test


class _StubCampaignWorker(BaseCampaignWorker):
    COMPONENT_NAME = "stub_campaign_worker"

    @property
    def campaign_type(self) -> CampaignType:
        return CampaignType.SMS

    @property
    def eager_loads(self) -> list[QueryableAttribute[Any]]:
        return []

    async def _process_campaign_contacts(self, campaign, db, log) -> None:  # type: ignore[no-untyped-def]
        return None

    def _get_remaining_filter(self, campaign):  # type: ignore[no-untyped-def]
        return None


def test_base_class_inherits_retryable_and_base() -> None:
    assert issubclass(BaseCampaignWorker, RetryableWorker)
    assert issubclass(BaseCampaignWorker, BaseWorker)


def test_retry_configuration_inherited_defaults() -> None:
    assert BaseCampaignWorker.max_retries == 3
    assert BaseCampaignWorker.backoff_base_seconds == 2.0


@pytest.mark.asyncio
async def test_failed_campaign_processing_routes_to_dlq() -> None:
    worker = _StubCampaignWorker()
    recorder = wire_worker_for_retry_test(worker)

    campaign = MagicMock(id=uuid4(), name="bad campaign")
    db = MagicMock()

    async def fail(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("campaign blew up")

    item_key = f"campaign:{campaign.id}"
    await worker.execute_with_retry(fail, campaign, db, item_key=item_key)

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["worker_name"] == "stub_campaign_worker"
    assert recorder.calls[0]["item_key"] == item_key


@pytest.mark.asyncio
async def test_scheduled_end_completion_generates_report(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = _StubCampaignWorker()
    worker._is_within_sending_hours = MagicMock(return_value=False)  # type: ignore[method-assign]
    campaign_id = uuid4()
    campaign = SimpleNamespace(
        id=campaign_id,
        name="Ended campaign",
        scheduled_end=datetime.now(UTC) - timedelta(minutes=1),
        sending_hours_start=None,
        sending_hours_end=None,
        sending_days=None,
        timezone="UTC",
        status=CampaignStatus.RUNNING,
        completed_at=None,
    )
    db = AsyncMock()
    service = MagicMock()
    service.generate_report = AsyncMock()
    service_class = MagicMock(return_value=service)
    monkeypatch.setattr(base_campaign_worker_module, "CampaignReportService", service_class)

    await worker._process_campaign(campaign, db)

    assert campaign.status == CampaignStatus.COMPLETED
    assert campaign.completed_at is not None
    service.generate_report.assert_awaited_once_with(db, campaign_id)
    worker._is_within_sending_hours.assert_not_called()
    db.commit.assert_awaited_once()
