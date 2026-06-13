"""Tests for the person-level dedupe facet.

People extraction emits named individuals at a company, so the key must bind a
person's name to their company host — two different people at one domain must
not collide, and the same person must dedupe across runs.
"""

from __future__ import annotations

from app.services.lead_discovery.dedupe import (
    dedupe_key_for_email,
    dedupe_key_for_person,
    dedupe_key_for_website,
)


class TestDedupeKeyForPerson:
    def test_email_wins_and_matches_email_facet(self) -> None:
        # An email-bearing person merges with any email-keyed row.
        key = dedupe_key_for_person(email="Jane@Acme.com", website_host="acme.com")
        assert key == dedupe_key_for_email("jane@acme.com")

    def test_same_company_different_people_are_distinct(self) -> None:
        jane = dedupe_key_for_person(full_name="Jane Smith", website_host="acme.com")
        john = dedupe_key_for_person(full_name="John Doe", website_host="acme.com")
        assert jane is not None and john is not None
        assert jane != john

    def test_same_person_different_company_distinct(self) -> None:
        a = dedupe_key_for_person(full_name="Jane Smith", website_host="acme.com")
        b = dedupe_key_for_person(full_name="Jane Smith", website_host="globex.com")
        assert a != b

    def test_same_person_same_company_is_stable(self) -> None:
        a = dedupe_key_for_person(first_name="Jane", last_name="Smith", website="https://acme.com")
        b = dedupe_key_for_person(full_name="Jane Smith", website_host="acme.com")
        assert a == b

    def test_does_not_collide_with_host_only_website_key(self) -> None:
        person = dedupe_key_for_person(full_name="Jane Smith", website_host="acme.com")
        company = dedupe_key_for_website("acme.com")
        assert person != company

    def test_missing_name_and_host_returns_none(self) -> None:
        assert dedupe_key_for_person(full_name="Jane Smith") is None
        assert dedupe_key_for_person(website_host="acme.com") is None
        assert dedupe_key_for_person() is None
