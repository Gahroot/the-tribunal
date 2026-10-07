"""RF-006: one ``sending_days`` encoding (Monday=0 … Sunday=6) end to end."""

import uuid
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.core.sending_days import (
    DAY_NAMES,
    SENDING_DAYS_DESCRIPTION,
    WEEKDAYS,
    is_sending_day,
    normalize_sending_days,
)
from app.schemas.campaign import (
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
    VoiceCampaignCreate,
    VoiceCampaignUpdate,
)
from app.schemas.message_test import MessageTestCreate
from app.services.agents.realtor_template import get_realtor_campaign_defaults
from scripts.ops.audit_campaign_sending_days import is_ambiguous, legacy_ui_to_contract

MONDAY = date(2026, 10, 5)
WEEK = [MONDAY + timedelta(days=offset) for offset in range(7)]


@pytest.mark.parametrize(("value", "day"), list(enumerate(WEEK)))
def test_every_weekday_maps_to_python_weekday(value: int, day: date) -> None:
    assert day.weekday() == value
    assert DAY_NAMES[value] == day.strftime("%A")
    assert is_sending_day([value], day)
    assert not any(is_sending_day([value], other) for other in WEEK if other != day)


@pytest.mark.parametrize("day", WEEK)
def test_monday_to_friday_never_sends_on_weekend(day: date) -> None:
    assert is_sending_day(list(WEEKDAYS), day) is (day.strftime("%A") not in {"Saturday", "Sunday"})


@pytest.mark.parametrize(
    ("days", "allowed"), [([5, 6], {"Saturday", "Sunday"}), ([2], {"Wednesday"})]
)
def test_weekend_and_single_day_schedules(days: list[int], allowed: set[str]) -> None:
    assert {d.strftime("%A") for d in WEEK if is_sending_day(days, d)} == allowed


@pytest.mark.parametrize("legacy", [None, []])
def test_legacy_null_or_empty_means_every_day(legacy: list[int] | None) -> None:
    assert all(is_sending_day(legacy, d) for d in WEEK)


def test_normalize_sorts_and_dedupes() -> None:
    assert normalize_sending_days([4, 0, 2, 0]) == [0, 2, 4]
    assert normalize_sending_days(None) is None


@pytest.mark.parametrize(
    "schema",
    [CampaignCreate, CampaignUpdate, VoiceCampaignCreate, VoiceCampaignUpdate, MessageTestCreate],
)
@pytest.mark.parametrize("bad", [[7], [-1], []])
def test_request_schemas_reject_out_of_contract_days(schema: type, bad: list[int]) -> None:
    payload = {
        "name": "x",
        "from_phone_number": "+15550000000",
        "initial_message": "hi",
        "voice_agent_id": str(uuid.uuid4()),
        "sending_days": bad,
    }
    with pytest.raises(ValidationError) as excinfo:
        schema.model_validate(payload)
    assert [err["loc"] for err in excinfo.value.errors()] == [("sending_days",)]


def test_request_schema_accepts_monday_to_friday_and_documents_encoding() -> None:
    campaign = VoiceCampaignCreate(
        name="x",
        from_phone_number="+15550000000",
        voice_agent_id=uuid.uuid4(),
        sending_days=[4, 3, 2, 1, 0],
    )
    assert campaign.sending_days == [0, 1, 2, 3, 4]
    for schema in (CampaignCreate, VoiceCampaignCreate, CampaignResponse):
        prop = schema.model_json_schema()["properties"]["sending_days"]
        assert prop["description"] == SENDING_DAYS_DESCRIPTION


def test_onboarding_realtor_default_is_monday_to_friday() -> None:
    days = get_realtor_campaign_defaults()["sending_days"]
    assert [DAY_NAMES[d] for d in days] == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def test_audit_flags_pre_fix_ui_rows_without_rewriting_them() -> None:
    # Old UI "Mon-Fri" was stored as [1..5]: the worker runs Tue-Sat.
    assert is_ambiguous([1, 2, 3, 4, 5])
    assert legacy_ui_to_contract([1, 2, 3, 4, 5]) == [0, 1, 2, 3, 4]
    assert not is_ambiguous(list(range(7)))
    assert not is_ambiguous(None)
