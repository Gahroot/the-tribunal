"""Public offer opt-in → CRM contact regressions (finding RF-014).

The default published offer is email-required, phone-optional. Before the fix
an email-only opt-in bumped ``offer.opt_ins`` but never saved a contact, and
the encrypted-column equality lookups meant repeat submissions never deduped.

The real public routes (live ``app.api.v1.offers`` and the extracted
``tribunal_offers`` block), shared lead-contact resolution, lookup hashing and
lead-magnet delivery run against a small in-memory session; only the email
provider and the speed-to-lead queue are stubbed, so no email/SMS is sent.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from tribunal_lead_capture import service as lead_magnet_delivery
from tribunal_offers.router import get_public_router as get_block_public_router

from app.api.deps import get_db
from app.api.v1 import offers as live_offers
from app.core.encryption import hash_phone, hash_value
from app.models.contact import Contact
from app.models.lead_magnet import DeliveryMethod, LeadMagnet, LeadMagnetType
from app.models.lead_magnet_lead import LeadMagnetLead
from app.models.offer import Offer
from app.models.offer_lead_magnet import OfferLeadMagnet
from app.services.contacts.lead_contacts import (
    LeadIdentity,
    LeadIdentityError,
    find_or_create_lead_contact,
    normalize_lead_identity,
)

WS_A = uuid.uuid4()
WS_B = uuid.uuid4()


@asynccontextmanager
async def _noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _scalars(values: list[Any]) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = values[0] if values else None
    result.scalars.return_value.first.return_value = values[0] if values else None
    result.scalars.return_value.all.return_value = values
    return result


class FakeSession:
    """Just enough AsyncSession for the public opt-in route.

    Contact lookups only match on the bound workspace id plus lookup hash, so a
    query that forgot workspace scoping (or compared ciphertext) finds nothing.
    """

    def __init__(self) -> None:
        self.offers: list[Offer] = []
        self.offer_lead_magnets: list[OfferLeadMagnet] = []
        self.contacts: list[Contact] = []
        self.leads: list[LeadMagnetLead] = []
        self.commits = 0
        self._next_contact_id = 1

    async def execute(self, statement: Any) -> MagicMock:
        sql = str(statement.compile()).lower()
        params = dict(statement.compile().params)
        values = set(params.values())
        if "from offers" in sql:
            return _scalars(
                [o for o in self.offers if o.public_slug in values and o.is_public and o.is_active]
            )
        if "from offer_lead_magnets" in sql:
            return _scalars(
                sorted(
                    (olm for olm in self.offer_lead_magnets if olm.offer_id in values),
                    key=lambda olm: olm.sort_order,
                )
            )
        if "from contacts" in sql:
            assert "contacts.workspace_id =" in sql, "contact lookup must be workspace scoped"
            matches = [
                c
                for c in self.contacts
                if c.workspace_id in values and ({c.email_hash, c.phone_hash} - {None}) & values
            ]
            return _scalars(sorted(matches, key=lambda c: c.id))
        raise AssertionError(f"unexpected query: {sql}")

    def add(self, obj: Any) -> None:
        if isinstance(obj, Contact):
            obj.id = self._next_contact_id
            self._next_contact_id += 1
            self.contacts.append(obj)
        elif isinstance(obj, LeadMagnetLead):
            obj.id = uuid.uuid4()
            self.leads.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


def _offer(
    *,
    workspace_id: uuid.UUID = WS_A,
    slug: str = "seller-launch",
    require_phone: bool = False,
    require_name: bool = False,
) -> Offer:
    # Mirrors the wizard defaults: email required, phone/name optional.
    return Offer(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name="Seller Launch",
        public_slug=slug,
        is_public=True,
        is_active=True,
        require_email=True,
        require_phone=require_phone,
        require_name=require_name,
        opt_ins=0,
    )


def _attach_bonus(session: FakeSession, offer: Offer) -> LeadMagnet:
    magnet = LeadMagnet(
        id=uuid.uuid4(),
        workspace_id=offer.workspace_id,
        name="Seller Guide",
        description="Guide",
        magnet_type=LeadMagnetType.PDF,
        delivery_method=DeliveryMethod.EMAIL,
        content_url="https://cdn.example.test/guide.pdf",
        is_active=True,
        download_count=0,
    )
    olm = OfferLeadMagnet(
        id=uuid.uuid4(), offer_id=offer.id, lead_magnet_id=magnet.id, sort_order=0
    )
    olm.lead_magnet = magnet
    session.offer_lead_magnets.append(olm)
    return magnet


@pytest.fixture
def sent_emails(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def fake_send(**kwargs: Any) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr(lead_magnet_delivery, "send_automation_email", fake_send)
    return sent


@pytest.fixture
def speed_to_lead_jobs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []

    async def fake_enqueue(workspace_id: uuid.UUID, contact_id: int, **kwargs: Any) -> bool:
        jobs.append({"workspace_id": workspace_id, "contact_id": contact_id, **kwargs})
        return True

    monkeypatch.setattr(live_offers, "enqueue_speed_to_lead_job", fake_enqueue)
    return jobs


def _live_router() -> APIRouter:
    router = APIRouter()
    router.include_router(live_offers.public_router, prefix="/p/offers")
    return router


@pytest.fixture(params=["live", "block"])
def make_client(request: pytest.FixtureRequest) -> Any:
    """Exercise both the mounted route and the extracted block's copy."""
    router = _live_router() if request.param == "live" else get_block_public_router()

    def _make(session: FakeSession) -> AsyncClient:
        app = FastAPI(lifespan=_noop_lifespan)
        app.include_router(router, prefix="/api/v1")

        async def _db() -> AsyncIterator[FakeSession]:
            yield session

        app.dependency_overrides[get_db] = _db
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return _make


async def _opt_in(client: AsyncClient, slug: str, body: dict[str, Any]) -> Any:
    async with client:
        return await client.post(f"/api/v1/p/offers/{slug}/opt-in", json=body)


async def test_email_only_opt_in_creates_visible_contact(
    make_client: Any, sent_emails: list[dict[str, Any]], speed_to_lead_jobs: list[Any]
) -> None:
    session = FakeSession()
    offer = _offer()
    session.offers.append(offer)

    response = await _opt_in(
        make_client(session), offer.public_slug, {"email": " Pat@Example.test "}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(session.contacts) == 1
    contact = session.contacts[0]
    assert body["contact_id"] == contact.id
    assert contact.workspace_id == WS_A
    assert contact.email == "Pat@Example.test"
    assert contact.email_hash == hash_value("pat@example.test")
    # Nothing fabricated: no phone, no messaging consent.
    assert contact.phone_number is None
    assert contact.phone_hash is None
    assert contact.sms_consent_status in (None, "unknown")
    assert contact.source == "offer_optin"
    assert contact.status == "new"
    assert contact.notes == "Opted in via offer: Seller Launch"
    assert offer.opt_ins == 1
    assert session.commits == 1
    # No phone → nothing to dial or text.
    assert speed_to_lead_jobs == []
    assert sent_emails == []


async def test_phone_present_opt_in_normalizes_phone_and_delivers_bonus(
    make_client: Any, sent_emails: list[dict[str, Any]], speed_to_lead_jobs: list[Any]
) -> None:
    session = FakeSession()
    offer = _offer()
    session.offers.append(offer)
    _attach_bonus(session, offer)

    response = await _opt_in(
        make_client(session),
        offer.public_slug,
        {"email": "ava@example.test", "phone_number": "(415) 555-0101", "name": "Ava Stone"},
    )

    assert response.status_code == 200
    body = response.json()
    contact = session.contacts[0]
    assert contact.phone_number == "+14155550101"
    assert contact.phone_hash == hash_phone("+14155550101")
    assert (contact.first_name, contact.last_name) == ("Ava", "Stone")
    assert contact.sms_consent_status in (None, "unknown")
    # Opt-in attribution on the bonus record points at the contact and offer.
    [lead] = session.leads
    assert body["lead_magnet_lead_id"] == str(lead.id)
    assert lead.contact_id == contact.id
    assert lead.source_offer_id == offer.id
    assert lead.workspace_id == WS_A
    assert lead.phone_number == "+14155550101"
    assert lead.delivered is True
    assert [e["to_email"] for e in sent_emails] == ["ava@example.test"]
    if speed_to_lead_jobs:  # live route only; the block has no speed-to-lead hook
        assert speed_to_lead_jobs == [
            {"workspace_id": WS_A, "contact_id": contact.id, "source": "offer_optin"}
        ]


async def test_repeat_submissions_reuse_contact_and_keep_counting(
    make_client: Any, sent_emails: list[dict[str, Any]], speed_to_lead_jobs: list[Any]
) -> None:
    session = FakeSession()
    offer = _offer()
    session.offers.append(offer)
    _attach_bonus(session, offer)

    first = await _opt_in(make_client(session), offer.public_slug, {"email": "pat@example.test"})
    second = await _opt_in(
        make_client(session),
        offer.public_slug,
        {"email": "PAT@example.test", "phone_number": "+1 415 555 0199", "name": "Pat Buyer"},
    )

    assert first.status_code == second.status_code == 200
    assert len(session.contacts) == 1
    contact = session.contacts[0]
    assert first.json()["contact_id"] == second.json()["contact_id"] == contact.id
    # Gaps filled from the newer submission; original email kept as entered.
    assert contact.email == "pat@example.test"
    assert contact.phone_number == "+14155550199"
    assert (contact.first_name, contact.last_name) == ("Pat", "Buyer")
    assert contact.notes == "Opted in via offer: Seller Launch"
    # Every accepted submission still counts and gets its bonus record.
    assert offer.opt_ins == 2
    assert [lead.contact_id for lead in session.leads] == [contact.id, contact.id]
    assert len(sent_emails) == 2
    # Speed-to-lead only fires for brand-new contacts.
    assert speed_to_lead_jobs == []


async def test_existing_contact_fields_are_not_overwritten(make_client: Any) -> None:
    session = FakeSession()
    offer = _offer()
    session.offers.append(offer)
    existing = Contact(
        id=42,
        workspace_id=WS_A,
        first_name="Patricia",
        last_name="Known",
        email="pat@example.test",
        email_hash=hash_value("pat@example.test"),
        phone_number="+14155550100",
        phone_hash=hash_phone("+14155550100"),
        status="qualified",
        notes="VIP seller",
    )
    session.contacts.append(existing)

    response = await _opt_in(
        make_client(session),
        offer.public_slug,
        {"email": "pat@example.test", "phone_number": "+14155550111", "name": "Someone Else"},
    )

    assert response.status_code == 200
    assert response.json()["contact_id"] == 42
    assert len(session.contacts) == 1
    assert existing.phone_number == "+14155550100"
    assert (existing.first_name, existing.last_name) == ("Patricia", "Known")
    assert existing.status == "qualified"
    assert existing.notes == "VIP seller\nOpted in via offer: Seller Launch"


@pytest.mark.parametrize(
    ("offer_kwargs", "body", "detail"),
    [
        ({}, {}, "Email is required"),
        ({}, {"email": "   ", "name": "Pat"}, "Email is required"),
        ({}, {"email": "not-an-email"}, "Please enter a valid email address"),
        (
            {},
            {"email": "pat@example.test", "phone_number": "12"},
            "Please enter a valid phone number",
        ),
        ({"require_phone": True}, {"email": "pat@example.test"}, "Phone number is required"),
        ({"require_name": True}, {"email": "pat@example.test"}, "Name is required"),
    ],
)
async def test_invalid_submissions_are_rejected_without_side_effects(
    make_client: Any, offer_kwargs: dict[str, Any], body: dict[str, Any], detail: str
) -> None:
    session = FakeSession()
    offer = _offer(**offer_kwargs)
    session.offers.append(offer)

    response = await _opt_in(make_client(session), offer.public_slug, body)

    assert response.status_code == 400
    assert response.json()["detail"] == detail
    assert session.contacts == []
    assert session.leads == []
    assert offer.opt_ins == 0
    assert session.commits == 0


async def test_same_email_in_other_workspace_is_never_reused(make_client: Any) -> None:
    session = FakeSession()
    offer_b = _offer(workspace_id=WS_B, slug="other-workspace-offer")
    session.offers.append(offer_b)
    foreign = Contact(
        id=7,
        workspace_id=WS_A,
        first_name="Pat",
        email="pat@example.test",
        email_hash=hash_value("pat@example.test"),
        phone_number="+14155550100",
        phone_hash=hash_phone("+14155550100"),
        status="new",
    )
    session.contacts.append(foreign)

    response = await _opt_in(
        make_client(session),
        offer_b.public_slug,
        {"email": "pat@example.test", "phone_number": "+14155550100"},
    )

    assert response.status_code == 200
    created = session.contacts[-1]
    assert len(session.contacts) == 2
    assert response.json()["contact_id"] == created.id != foreign.id
    assert created.workspace_id == WS_B
    assert foreign.workspace_id == WS_A
    assert foreign.notes is None


async def test_unknown_or_unpublished_offer_is_404(make_client: Any) -> None:
    session = FakeSession()
    offer = _offer()
    offer.is_public = False
    session.offers.append(offer)

    response = await _opt_in(make_client(session), offer.public_slug, {"email": "a@b.test"})

    assert response.status_code == 404
    assert session.contacts == []


# ── service-level ────────────────────────────────────────────────────────────


def test_normalize_lead_identity_rejects_malformed_values() -> None:
    assert normalize_lead_identity(email=" a@b.test ", phone_number="", name="  Jo   Ann  ") == (
        LeadIdentity(email="a@b.test", phone_number=None, name="Jo Ann")
    )
    with pytest.raises(LeadIdentityError):
        normalize_lead_identity(email="nope", phone_number=None, name=None)
    with pytest.raises(LeadIdentityError):
        normalize_lead_identity(email=None, phone_number="555", name=None)


async def test_find_or_create_requires_an_identifier() -> None:
    with pytest.raises(LeadIdentityError, match="Email or phone number is required"):
        await find_or_create_lead_contact(
            FakeSession(),  # type: ignore[arg-type]
            workspace_id=WS_A,
            identity=LeadIdentity(email=None, phone_number=None, name="Name Only"),
            source="offer_optin",
        )


async def test_find_or_create_matches_phone_when_email_is_new() -> None:
    session = FakeSession()
    existing = Contact(
        id=3,
        workspace_id=WS_A,
        first_name="Unknown",
        phone_number="+14155550100",
        phone_hash=hash_phone("+14155550100"),
        status="new",
    )
    session.contacts.append(existing)

    result = await find_or_create_lead_contact(
        session,  # type: ignore[arg-type]
        workspace_id=WS_A,
        identity=LeadIdentity(email="new@example.test", phone_number="+14155550100", name="Jo"),
        source="offer_optin",
    )

    assert result.created is False
    assert result.contact is existing
    assert existing.email == "new@example.test"
    assert existing.email_hash == hash_value("new@example.test")
    assert existing.first_name == "Jo"
