"""Tests for pure email-pattern inference."""

from __future__ import annotations

from app.services.lead_discovery.email_patterns import (
    candidate_emails,
    split_full_name,
)


class TestSplitFullName:
    def test_two_tokens(self) -> None:
        assert split_full_name("Jane Smith") == ("Jane", "Smith")

    def test_three_tokens_uses_last(self) -> None:
        assert split_full_name("John A. Doe") == ("John", "Doe")

    def test_single_token(self) -> None:
        assert split_full_name("Cher") == ("Cher", "")

    def test_empty(self) -> None:
        assert split_full_name(None) == ("", "")


class TestCandidateEmails:
    def test_ranked_patterns_for_full_name(self) -> None:
        candidates = candidate_emails("Jane", "Smith", "acme.com")
        emails = [c.email for c in candidates]
        # Highest-confidence B2B pattern leads.
        assert emails[0] == "jane.smith@acme.com"
        assert "jane@acme.com" in emails
        assert "jsmith@acme.com" in emails
        # Confidence is monotonically non-increasing.
        confs = [c.confidence for c in candidates]
        assert confs == sorted(confs, reverse=True)

    def test_domain_url_is_normalized_to_host(self) -> None:
        candidates = candidate_emails("Jane", "Smith", "https://www.acme.com/team")
        assert all(c.email.endswith("@acme.com") for c in candidates)

    def test_full_name_fallback(self) -> None:
        candidates = candidate_emails(None, None, "acme.com", full_name="Bob Jones")
        assert "bob.jones@acme.com" in {c.email for c in candidates}

    def test_no_name_returns_empty(self) -> None:
        assert candidate_emails(None, None, "acme.com") == []

    def test_no_domain_returns_empty(self) -> None:
        assert candidate_emails("Jane", "Smith", None) == []

    def test_first_only(self) -> None:
        candidates = candidate_emails("Madonna", None, "acme.com")
        emails = {c.email for c in candidates}
        assert "madonna@acme.com" in emails

    def test_dedupes_addresses_keeping_highest_confidence(self) -> None:
        candidates = candidate_emails("Jane", "Smith", "acme.com")
        emails = [c.email for c in candidates]
        assert len(emails) == len(set(emails))

    def test_punctuation_in_name_is_sanitized(self) -> None:
        candidates = candidate_emails("Mary-Jane", "O'Brien", "acme.com")
        # No stray punctuation leaks into the local part.
        assert all("'" not in c.email and "-" not in c.email.split("@")[0] for c in candidates)
