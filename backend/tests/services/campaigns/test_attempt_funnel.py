"""Attempt funnel query boundaries and rate math."""

from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.schemas.attempt_funnel import AttemptFunnelResponse
from app.services.campaigns.attempt_funnel import _attempts, _metrics


def test_attempts_query_scopes_campaign_conversation_and_contact() -> None:
    workspace_id = uuid4()
    campaign_id = uuid4()
    sql = str(
        _attempts(workspace_id, campaign_id)
        .select()
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert sql.count(str(workspace_id)) >= 4
    assert str(campaign_id) in sql
    assert "row_number() OVER (PARTITION BY" in sql
    assert "appointments.message_id = messages.id" in sql
    assert "appointments.workspace_id" in sql
    assert "messages.direction = 'outbound'" in sql


def test_response_contract_accepts_empty_cohort() -> None:
    from datetime import UTC, datetime

    empty = _metrics(
        SimpleNamespace(
            calls=0, connected=None, conversation=None, qualified=None, booked=None, shown=None
        )
    )
    response = AttemptFunnelResponse.model_validate(
        {
            "starts_at": datetime(2026, 1, 1, tzinfo=UTC),
            "ends_at": datetime(2026, 1, 2, tzinfo=UTC),
            "hour_timezone": "UTC",
            "cost_basis": "estimated_blended_ai_call_usd",
            "overall": empty,
            "attempt": [],
            "hour_utc": [],
            "lead_source": [],
            "campaign": [],
        }
    )
    assert response.overall.calls == 0
    assert response.overall.show_rate_of_booked is None


def test_metrics_are_call_denominated_and_costs_unknown_without_bookings() -> None:
    row = SimpleNamespace(calls=4, connected=3, conversation=2, qualified=1, booked=0, shown=0)
    metrics = _metrics(row)
    assert metrics["connect_rate"] == 0.75
    assert metrics["conversation_rate"] == 0.5
    assert metrics["qualified_rate"] == 0.25
    assert metrics["show_rate_of_booked"] is None
    assert metrics["estimated_cost_per_booked_usd"] is None
    assert metrics["estimated_cost_per_shown_usd"] is None

    booked = _metrics(
        SimpleNamespace(calls=4, connected=3, conversation=2, qualified=1, booked=2, shown=1)
    )
    assert booked["show_rate_of_booked"] == 0.5
    assert booked["estimated_cost_per_booked_usd"] == round(booked["estimated_cost_usd"] / 2, 2)
