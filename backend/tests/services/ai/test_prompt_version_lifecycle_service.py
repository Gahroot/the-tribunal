"""Tests for workspace-scoped prompt version lifecycle service logic."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.prompt_version import PromptVersion
from app.schemas.prompt_version import ArmStatusUpdate
from app.services.ai.bandit_statistics import ComparisonResult, VersionStats, WinnerResult
from app.services.ai.prompt_version_lifecycle_service import PromptVersionLifecycleService
from app.services.exceptions import NotFoundError, ValidationError


@dataclass(slots=True)
class _StatsRow:
    total_calls: int | None
    completed_calls: int | None
    failed_calls: int | None
    appointments_booked: int | None
    leads_qualified: int | None
    avg_duration: float | None
    avg_quality: float | None
    min_date: date | None
    max_date: date | None


class _Result:
    def __init__(self, *, scalar: Any = None, row: Any = None) -> None:
        self._scalar = scalar
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def one(self) -> Any:
        return self._row


def _prompt_version(**overrides: Any) -> PromptVersion:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "agent_id": uuid.uuid4(),
        "system_prompt": "You are helpful.",
        "initial_greeting": "Hello",
        "temperature": 0.7,
        "version_number": 1,
        "change_summary": None,
        "created_by_id": None,
        "is_active": True,
        "is_baseline": False,
        "parent_version_id": None,
        "total_calls": 0,
        "successful_calls": 0,
        "booked_appointments": 0,
        "traffic_percentage": None,
        "experiment_id": None,
        "arm_status": "active",
        "bandit_alpha": 1.0,
        "bandit_beta": 1.0,
        "total_reward": 0.0,
        "reward_count": 0,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "activated_at": None,
    }
    values.update(overrides)
    return PromptVersion(**values)


def _db_with_agent_and_version(
    version: PromptVersion,
    stats_row: _StatsRow | None = None,
) -> MagicMock:
    db = MagicMock()
    results = [_Result(scalar=version.agent_id), _Result(scalar=version)]
    if stats_row is not None:
        results.append(_Result(row=stats_row))
    db.execute = AsyncMock(side_effect=results)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


class _StatisticsService:
    def __init__(self, *, comparison: ComparisonResult, winner: WinnerResult) -> None:
        self._comparison = comparison
        self._winner = winner
        self.compare_versions = MagicMock(return_value=comparison)
        self.detect_winner = MagicMock(return_value=winner)


def test_stats_response_uses_daily_aggregates_and_computes_rates() -> None:
    version = _prompt_version(version_number=4, total_calls=99, successful_calls=88)
    response = PromptVersionLifecycleService._stats_response(
        version,
        total_calls=20,
        completed_calls=10,
        failed_calls=2,
        appointments_booked=3,
        leads_qualified=4,
        avg_duration_seconds=120.5,
        avg_quality_score=0.87,
        min_date=date(2026, 5, 1),
        max_date=date(2026, 5, 3),
    )

    assert response.prompt_version_id == version.id
    assert response.version_number == 4
    assert response.total_calls == 20
    assert response.completed_calls == 10
    assert response.failed_calls == 2
    assert response.appointments_booked == 3
    assert response.leads_qualified == 4
    assert response.booking_rate == 0.3
    assert response.qualification_rate == 0.4
    assert response.completion_rate == 0.5
    assert response.avg_duration_seconds == 120.5
    assert response.avg_quality_score == 0.87
    assert response.stats_from == datetime(2026, 5, 1)
    assert response.stats_to == datetime(2026, 5, 3)


def test_stats_response_falls_back_to_version_counters_when_no_daily_rows() -> None:
    version = _prompt_version(total_calls=12, successful_calls=6, booked_appointments=2)
    response = PromptVersionLifecycleService._stats_response(
        version,
        total_calls=None,
        completed_calls=None,
        failed_calls=None,
        appointments_booked=None,
        leads_qualified=None,
        avg_duration_seconds=None,
        avg_quality_score=None,
        min_date=None,
        max_date=None,
    )

    assert response.total_calls == 12
    assert response.completed_calls == 6
    assert response.appointments_booked == 2
    assert response.failed_calls == 0
    assert response.leads_qualified == 0
    assert response.booking_rate == pytest.approx(2 / 6)
    assert response.completion_rate == 0.5
    assert response.qualification_rate is None
    assert response.stats_from is None
    assert response.stats_to is None


async def test_get_version_stats_scopes_agent_and_maps_aggregate_row() -> None:
    version = _prompt_version()
    stats_row = _StatsRow(
        total_calls=9,
        completed_calls=6,
        failed_calls=3,
        appointments_booked=2,
        leads_qualified=1,
        avg_duration=75.0,
        avg_quality=0.9,
        min_date=date(2026, 5, 10),
        max_date=date(2026, 5, 11),
    )
    db = _db_with_agent_and_version(version, stats_row)

    response = await PromptVersionLifecycleService().get_version_stats(
        db,
        uuid.uuid4(),
        version.agent_id,
        version.id,
        days=14,
    )

    assert response.total_calls == 9
    assert response.completed_calls == 6
    assert response.failed_calls == 3
    assert response.booking_rate == pytest.approx(2 / 6)
    assert db.execute.await_count == 3


async def test_get_version_stats_raises_not_found_when_agent_not_in_workspace() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(scalar=None))

    with pytest.raises(NotFoundError, match="Agent not found"):
        await PromptVersionLifecycleService().get_version_stats(
            db,
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            days=30,
        )

    db.execute.assert_awaited_once()


async def test_update_arm_status_wraps_invalid_lifecycle_transition() -> None:
    version = _prompt_version()
    prompt_versions = MagicMock()
    prompt_versions.update_arm_status = AsyncMock(
        side_effect=ValueError("Cannot resume eliminated version")
    )
    db = _db_with_agent_and_version(version)

    service = PromptVersionLifecycleService(prompt_versions=prompt_versions)

    with pytest.raises(ValidationError, match="Cannot resume eliminated version"):
        await service.update_arm_status_in_workspace(
            db,
            uuid.uuid4(),
            version.agent_id,
            version.id,
            ArmStatusUpdate(arm_status="active"),
        )

    prompt_versions.update_arm_status.assert_awaited_once_with(db, version.id, "active")


async def test_activate_for_testing_wraps_invalid_lifecycle_state() -> None:
    version = _prompt_version()
    prompt_versions = MagicMock()
    prompt_versions.activate_for_testing = AsyncMock(
        side_effect=ValueError("Cannot activate eliminated version")
    )
    db = _db_with_agent_and_version(version)

    service = PromptVersionLifecycleService(prompt_versions=prompt_versions)

    with pytest.raises(ValidationError, match="Cannot activate eliminated version"):
        await service.activate_for_testing_in_workspace(
            db,
            uuid.uuid4(),
            version.agent_id,
            version.id,
        )

    prompt_versions.activate_for_testing.assert_awaited_once_with(db, version.id)


async def test_compare_versions_maps_statistics_service_result() -> None:
    first = _prompt_version(version_number=1, bandit_alpha=40, bandit_beta=10, reward_count=50)
    second = _prompt_version(
        agent_id=first.agent_id,
        version_number=2,
        bandit_alpha=10,
        bandit_beta=40,
        reward_count=50,
    )
    comparison = ComparisonResult(
        versions=[
            VersionStats(
                version_id=first.id,
                version_number=first.version_number,
                is_active=True,
                is_baseline=False,
                arm_status="active",
                alpha=40,
                beta=10,
                sample_size=50,
                mean_estimate=0.8,
                probability_best=0.97,
                credible_interval=(0.68, 0.89),
                booking_rate=0.4,
            )
        ],
        winner_id=first.id,
        winner_probability=0.97,
        recommended_action="declare_winner",
        min_samples_needed=0,
    )
    winner = WinnerResult(
        winner_id=first.id,
        winner_probability=0.97,
        confidence_threshold=0.95,
        is_conclusive=True,
        message="Version has 97.0% probability of being best",
    )
    stats_service = _StatisticsService(comparison=comparison, winner=winner)
    prompt_versions = MagicMock()
    prompt_versions.get_active_versions = AsyncMock(return_value=[first, second])
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(scalar=first.agent_id))

    service = PromptVersionLifecycleService(
        prompt_versions=prompt_versions,
        statistics_factory=lambda: stats_service,
    )
    response = await service.compare_versions_in_workspace(
        db,
        uuid.uuid4(),
        first.agent_id,
        winner_threshold=0.9,
    )

    assert response.winner_id == first.id
    assert response.winner_probability == 0.97
    assert response.recommended_action == "declare_winner"
    assert response.versions[0].version_id == first.id
    assert response.versions[0].credible_interval_lower == 0.68
    assert response.versions[0].credible_interval_upper == 0.89
    stats_service.compare_versions.assert_called_once_with([first, second], winner_threshold=0.9)


async def test_detect_winner_returns_empty_active_version_message_without_statistics_call() -> None:
    prompt_versions = MagicMock()
    prompt_versions.get_active_versions = AsyncMock(return_value=[])
    stats_factory = MagicMock()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(scalar=uuid.uuid4()))

    service = PromptVersionLifecycleService(
        prompt_versions=prompt_versions,
        statistics_factory=stats_factory,
    )
    response = await service.detect_winner_in_workspace(
        db,
        uuid.uuid4(),
        uuid.uuid4(),
        threshold=0.8,
    )

    assert response.winner_id is None
    assert response.winner_probability is None
    assert response.confidence_threshold == 0.8
    assert response.is_conclusive is False
    assert response.message == "No active versions to compare"
    stats_factory.assert_not_called()
