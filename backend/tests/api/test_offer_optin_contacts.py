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
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tribunal_lead_capture import service as lead_magnet_delivery
from tribunal_offers.router import get_public_router as get_block_public_router
from tribunal_offers.router import get_router as get_block_router

from app.api.deps import get_current_user, get_workspace
from app.api.v1 import offers as live_offers
from app.core.encryption import hash_phone, hash_value
from app.db.session import get_db
from app.models.contact import Contact
from app.models.lead_magnet import DeliveryMethod, LeadMagnet, LeadMagnetType
from app.models.lead_magnet_lead import LeadMagnetLead
from app.models.offer import Offer
from app.models.offer_lead_magnet import OfferLeadMagnet
from app.models.workspace import Workspace
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
        self.rollbacks = 0
        self.fail_commit = False
        self.magnets: list[LeadMagnet] = []
        self._snapshot: tuple[list[OfferLeadMagnet], list[str]] | None = None
        self._next_contact_id = 1

    async def get(self, model: Any, key: uuid.UUID) -> Workspace:
        assert model is Workspace
        return Workspace(id=key, name=f"Brand {key}", settings={}, is_active=True)

    async def execute(self, statement: Any) -> MagicMock:
        sql = str(statement.compile()).lower()
        params = dict(statement.compile().params)
        values = {
            v for value in params.values() for v in (value if isinstance(value, list) else [value])
        }
        if "from lead_magnets" in sql:
            assert "lead_magnets.workspace_id =" in sql
            return _scalars(
                [m for m in self.magnets if m.workspace_id in values and m.id in values]
            )
        if "from offers" in sql:
            if "offers.workspace_id =" in sql:
                assert "offers.id =" in sql
                return _scalars(
                    [o for o in self.offers if o.workspace_id in values and o.id in values]
                )
            assert "offers.public_slug =" in sql
            assert "offers.is_public is true" in sql
            assert "offers.is_active is true" in sql
            return _scalars(
                [o for o in self.offers if o.public_slug in values and o.is_public and o.is_active]
            )
        if "from offer_lead_magnets" in sql:
            self._snapshot = (list(self.offer_lead_magnets), [o.name for o in self.offers])
            if "max(" in sql or "select offer_lead_magnets.lead_magnet_id" in sql:
                result = MagicMock()
                if "max(" in sql:
                    result.scalar.return_value = max(
                        (a.sort_order for a in self.offer_lead_magnets), default=0
                    )
                else:
                    result.all.return_value = [(a.lead_magnet_id,) for a in self.offer_lead_magnets]
                return result
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
        if isinstance(obj, Offer):
            obj.id = uuid.uuid4()
            obj.created_at = obj.updated_at = datetime.now(UTC)
            obj.page_views = obj.opt_ins = 0
            self.offers.append(obj)
        elif isinstance(obj, OfferLeadMagnet):
            obj.lead_magnet = next(m for m in self.magnets if m.id == obj.lead_magnet_id)
            self.offer_lead_magnets.append(obj)
            next(o for o in self.offers if o.id == obj.offer_id).offer_lead_magnets.append(obj)
        elif isinstance(obj, Contact):
            obj.id = self._next_contact_id
            self._next_contact_id += 1
            self.contacts.append(obj)
        elif isinstance(obj, LeadMagnetLead):
            obj.id = uuid.uuid4()
            self.leads.append(obj)

    async def refresh(self, obj: Any) -> None:
        assert obj in self.offers

    async def flush(self) -> None:
        return None

    async def delete(self, obj: Any) -> None:
        assert isinstance(obj, OfferLeadMagnet), "only associations may be removed"
        self.offer_lead_magnets.remove(obj)
        next(o for o in self.offers if o.id == obj.offer_id).offer_lead_magnets.remove(obj)

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self._snapshot:
            self.offer_lead_magnets, names = self._snapshot
            for offer, name in zip(self.offers, names, strict=True):
                offer.name = name
                offer.offer_lead_magnets = [
                    a for a in self.offer_lead_magnets if a.offer_id == offer.id
                ]

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("fixture commit failure")
        self.commits += 1
        self._snapshot = None


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
        discount_type="percentage",
        discount_value=0,
        public_slug=slug,
        is_public=True,
        is_active=True,
        require_email=True,
        require_phone=require_phone,
        require_name=require_name,
        page_views=0,
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
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    olm = OfferLeadMagnet(
        id=uuid.uuid4(), offer_id=offer.id, lead_magnet_id=magnet.id, sort_order=0
    )
    olm.lead_magnet = magnet
    session.offer_lead_magnets.append(olm)
    offer.offer_lead_magnets.append(olm)
    session.magnets.append(magnet)
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
    router.include_router(live_offers.router, prefix="/workspaces/{workspace_id}/offers")
    return router


@pytest.fixture(params=["live", "block"])
def make_client(request: pytest.FixtureRequest) -> Any:
    """Exercise both the mounted route and the extracted block's copy."""
    router = _live_router() if request.param == "live" else get_block_public_router()
    if request.param == "block":
        router.include_router(get_block_router())

    def _make(session: FakeSession) -> AsyncClient:
        app = FastAPI(lifespan=_noop_lifespan)
        app.include_router(router, prefix="/api/v1")

        async def _db() -> AsyncIterator[FakeSession]:
            yield session

        async def _user() -> MagicMock:
            return MagicMock()

        async def _workspace(workspace_id: uuid.UUID) -> Workspace:
            assert workspace_id in (WS_A, WS_B)
            return Workspace(id=workspace_id, name="Fixture workspace")

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_workspace] = _workspace
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return _make


async def _opt_in(client: AsyncClient, slug: str | None, body: dict[str, Any]) -> Any:
    assert slug, "fixture offers always have a public slug"
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


# ── publication contract (RF-020) ────────────────────────────────────────────


async def test_publication_settings_survive_create_read_update_and_optin(
    make_client: Any, sent_emails: list[dict[str, Any]], speed_to_lead_jobs: list[Any]
) -> None:
    session = FakeSession()
    path = f"/api/v1/workspaces/{WS_A}/offers"
    publishing = {
        "is_public": True,
        "public_slug": "phone-and-name-fixture",
        "require_email": False,
        "require_phone": True,
        "require_name": True,
    }
    async with make_client(session) as client:
        created = await client.post(path, json={"name": "Fixture offer", **publishing})
        assert created.status_code == 201
        offer_id = created.json()["id"]
        for key, value in publishing.items():
            assert created.json()[key] == value
            assert getattr(session.offers[0], key) == value

        for suffix in ("", "/with-lead-magnets"):
            reopened = await client.get(f"{path}/{offer_id}{suffix}")
            assert reopened.status_code == 200
            assert {key: reopened.json()[key] for key in publishing} == publishing

        foreign_path = f"/api/v1/workspaces/{WS_B}/offers/{offer_id}"
        assert (await client.get(foreign_path)).status_code == 404
        assert (await client.put(foreign_path, json={"is_public": False})).status_code == 404

        public_path = f"/api/v1/p/offers/{publishing['public_slug']}"
        public = await client.get(public_path)
        assert public.status_code == 200
        assert {k: public.json()[k] for k in publishing if k.startswith("require_")} == {
            "require_email": False,
            "require_phone": True,
            "require_name": True,
        }
        private_keys = {"workspace_id", "is_public", "public_slug", "terms", "id"}
        assert not private_keys & public.json().keys()

        for body, detail in (
            ({"name": "Fixture Visitor"}, "Phone number is required"),
            ({"phone_number": "+14155550101", "name": "  "}, "Name is required"),
        ):
            rejected = await client.post(f"{public_path}/opt-in", json=body)
            assert rejected.status_code == 400
            assert rejected.json()["detail"] == detail
        assert session.contacts == []
        accepted = await client.post(
            f"{public_path}/opt-in",
            json={"phone_number": "+14155550101", "name": "Fixture Visitor"},
        )
        assert accepted.status_code == 200
        assert session.contacts[0].workspace_id == WS_A
        assert session.contacts[0].email is None

        publishing.update(
            public_slug="email-fixture", require_email=True, require_phone=False, require_name=False
        )
        updated = await client.put(f"{path}/{offer_id}", json=publishing)
        assert updated.status_code == 200
        reopened = await client.get(f"{path}/{offer_id}")
        assert {key: reopened.json()[key] for key in publishing} == publishing
        assert (await client.get(public_path)).status_code == 404
        public_path = "/api/v1/p/offers/email-fixture"
        public = await client.get(public_path)
        assert public.status_code == 200
        assert {k: public.json()[k] for k in publishing if k.startswith("require_")} == {
            "require_email": True,
            "require_phone": False,
            "require_name": False,
        }
        rejected = await client.post(f"{public_path}/opt-in", json={"phone_number": "+14155550102"})
        assert rejected.status_code == 400
        assert rejected.json()["detail"] == "Email is required"
        accepted = await client.post(
            f"{public_path}/opt-in", json={"email": "fixture@example.test"}
        )
        assert accepted.status_code == 200

        # An unrelated partial update must not reset publication choices.
        renamed = await client.put(f"{path}/{offer_id}", json={"name": "Renamed fixture"})
        assert {key: renamed.json()[key] for key in publishing} == publishing
        for disabled in ({"is_public": False}, {"is_public": True, "is_active": False}):
            assert (await client.put(f"{path}/{offer_id}", json=disabled)).status_code == 200
            assert (await client.get(public_path)).status_code == 404
            assert (
                await client.post(f"{public_path}/opt-in", json={"email": "fixture@example.test"})
            ).status_code == 404
    assert sent_emails == []


async def test_publication_defaults_and_validation(make_client: Any) -> None:
    session = FakeSession()
    path = f"/api/v1/workspaces/{WS_A}/offers"
    async with make_client(session) as client:
        created = await client.post(path, json={"name": "Private fixture"})
        assert created.status_code == 201
        body = created.json()
        assert body["is_public"] is False
        assert body["public_slug"] is None
        assert body["require_email"] is True
        assert body["require_phone"] is False
        assert body["require_name"] is False
        for invalid in ({"public_slug": "x" * 101}, {"require_phone": "invalid"}):
            rejected = await client.post(path, json={"name": "Invalid fixture", **invalid})
            assert rejected.status_code == 422
            rejected = await client.put(f"{path}/{body['id']}", json=invalid)
            assert rejected.status_code == 422
        assert len(session.offers) == 1
    # Globally unique slugs still guard the anonymous lookup across workspaces.
    assert Offer.__table__.c.public_slug.unique is True


# ── explicit clears and free pricing (RF-024) ─────────────────────────────────


async def test_offer_update_preserves_explicit_empty_and_zero_values(make_client: Any) -> None:
    session = FakeSession()
    path = f"/api/v1/workspaces/{WS_A}/offers"
    original = {
        "name": "Free pricing fixture",
        "description": "Old description",
        "headline": "Old headline",
        "guarantee_type": "money_back",
        "guarantee_days": 30,
        "guarantee_text": "Old guarantee",
        "value_stack_items": [{"name": "Training", "value": 100, "included": True}],
        "regular_price": 100,
        "offer_price": 50,
        "discount_type": "fixed",
        "discount_value": 10,
        "terms": "Keep terms",
        "is_public": True,
        "public_slug": "free-pricing-fixture",
        "require_email": False,
        "require_phone": True,
        "require_name": False,
    }
    changes = {
        "description": "",
        "headline": None,
        "guarantee_text": None,
        "guarantee_days": 0,
        "value_stack_items": [],
        "offer_price": 0,
    }
    async with make_client(session) as client:
        created = await client.post(path, json=original)
        assert created.status_code == 201
        offer_path = f"{path}/{created.json()['id']}"
        updated = await client.put(offer_path, json=changes)
        assert updated.status_code == 200
        for response in (updated, await client.get(offer_path)):
            assert response.status_code == 200
            assert {key: response.json()[key] for key in changes} == changes
            untouched = original.keys() - changes.keys()
            assert {key: response.json()[key] for key in untouched} == {
                key: original[key] for key in untouched
            }
        public = await client.get("/api/v1/p/offers/free-pricing-fixture")
        assert public.status_code == 200
        assert {key: public.json()[key] for key in changes} == changes
        assert public.json()["regular_price"] == 100
        assert public.json()["require_phone"] is True

        # Null removes pricing; omission does not restore it or reset flags.
        cleared = await client.put(offer_path, json={"offer_price": None, "is_active": False})
        assert cleared.status_code == 200
        renamed = await client.put(offer_path, json={"name": "Still inactive"})
        assert renamed.json()["offer_price"] is None
        assert renamed.json()["is_active"] is False
        assert renamed.json()["is_public"] is True
        assert (await client.get("/api/v1/p/offers/free-pricing-fixture")).status_code == 404
        for invalid in (
            {"offer_price": -1},
            {"regular_price": -1},
            {"guarantee_days": -1},
            {"value_stack_items": [{"name": "Invalid", "value": -1}]},
        ):
            assert (await client.put(offer_path, json=invalid)).status_code == 422
        assert (await client.get(offer_path)).json()["offer_price"] is None


# ── exact bonus selection (RF-023) ───────────────────────────────────────────


@pytest.mark.parametrize("initial, retained", [(2, 1), (1, 0), (2, 0), (2, 2)])
async def test_edit_reconciles_bonus_set(make_client: Any, initial: int, retained: int) -> None:
    session = FakeSession()
    offer = _offer()
    offer.created_at = offer.updated_at = datetime.now(UTC)
    session.offers.append(offer)
    magnets = [_attach_bonus(session, offer) for _ in range(initial)]
    associations = list(session.offer_lead_magnets)
    for index, association in enumerate(associations):
        association.sort_order = index + 4
        association.is_bonus = index == 1
    history = LeadMagnetLead(id=uuid.uuid4(), source_offer_id=offer.id)
    session.leads.append(history)
    path = f"/api/v1/workspaces/{WS_A}/offers/{offer.id}"
    async with make_client(session) as client:
        response = await client.put(
            path, json={"lead_magnet_ids": [str(m.id) for m in magnets[:retained]]}
        )
        assert response.status_code == 200
        reopened = await client.get(f"{path}/with-lead-magnets")
        assert reopened.status_code == 200
        assert [m["id"] for m in reopened.json()["lead_magnets"]] == [
            str(m.id) for m in magnets[:retained]
        ]
    assert session.offer_lead_magnets == associations[:retained]
    assert [(a.sort_order, a.is_bonus) for a in session.offer_lead_magnets] == [
        (i + 4, i == 1) for i in range(retained)
    ]
    assert session.magnets == magnets
    assert session.leads == [history]


async def test_bonus_reconciliation_validates_and_rolls_back(make_client: Any) -> None:
    session = FakeSession()
    offer = _offer()
    offer.created_at = offer.updated_at = datetime.now(UTC)
    session.offers.append(offer)
    magnet = _attach_bonus(session, offer)
    original = list(session.offer_lead_magnets)
    foreign = LeadMagnet(id=uuid.uuid4(), workspace_id=WS_B, name="Foreign fixture")
    session.magnets.append(foreign)
    path = f"/api/v1/workspaces/{WS_A}/offers/{offer.id}"
    async with make_client(session) as client:
        for invalid_id in (foreign.id, uuid.uuid4()):
            rejected = await client.put(
                path, json={"name": "Must not save", "lead_magnet_ids": [str(invalid_id)]}
            )
            assert rejected.status_code == 404
            assert offer.name == "Seller Launch"
            assert session.offer_lead_magnets == original
        assert (
            await client.put(path.replace(str(WS_A), str(WS_B)), json={"lead_magnet_ids": []})
        ).status_code == 404
        session.fail_commit = True
        with pytest.raises(RuntimeError, match="fixture commit failure"):
            await client.put(path, json={"name": "Must roll back", "lead_magnet_ids": []})
        assert offer.name == "Seller Launch"
        assert session.offer_lead_magnets == original
        assert session.rollbacks == 3
        session.fail_commit = False
        # Additive callers still retain the current set and metadata.
        extra = LeadMagnet(
            id=uuid.uuid4(),
            workspace_id=WS_A,
            name="New fixture",
            content_url="https://example.test/fixture.pdf",
            magnet_type=LeadMagnetType.PDF,
            delivery_method=DeliveryMethod.EMAIL,
            is_active=True,
            download_count=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.magnets.append(extra)
        attached = await client.post(f"{path}/lead-magnets", json=[str(extra.id)])
        assert attached.status_code == 200
        assert {a.lead_magnet_id for a in session.offer_lead_magnets} == {magnet.id, extra.id}
        assert session.offer_lead_magnets[0] is original[0]
        assert session.offer_lead_magnets[1].sort_order == 1
        # Reconcile removes one, retains metadata and adds each new ID only once.
        new_magnet = LeadMagnet(id=uuid.uuid4(), workspace_id=WS_A, name="Selected fixture")
        session.magnets.append(new_magnet)
        updated = await client.put(
            path, json={"lead_magnet_ids": [str(extra.id), str(new_magnet.id), str(new_magnet.id)]}
        )
        assert updated.status_code == 200
        assert [a.lead_magnet_id for a in session.offer_lead_magnets] == [extra.id, new_magnet.id]
        assert [(a.sort_order, a.is_bonus) for a in session.offer_lead_magnets] == [
            (1, True),
            (2, True),
        ]


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
            cast(AsyncSession, FakeSession()),
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
        cast(AsyncSession, session),
        workspace_id=WS_A,
        identity=LeadIdentity(email="new@example.test", phone_number="+14155550100", name="Jo"),
        source="offer_optin",
    )

    assert result.created is False
    assert result.contact is existing
    assert existing.email == "new@example.test"
    assert existing.email_hash == hash_value("new@example.test")
    assert existing.first_name == "Jo"
