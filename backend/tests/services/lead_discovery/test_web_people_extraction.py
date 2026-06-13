"""Tests for people extraction from company web pages (pure)."""

from __future__ import annotations

from app.services.lead_discovery.providers.web_people import (
    extract_people_from_html,
)

_TEAM_HTML = """
<html><body>
  <header><nav>
    <a href="/">Home</a><a href="/about">About Us</a><a href="/contact">Contact</a>
  </nav></header>
  <section class="our-team">
    <div class="team-member">
      <h3 class="member-name">Jane Smith</h3>
      <p class="role">Chief Executive Officer</p>
    </div>
    <div class="team-member">
      <h3>John A. Doe</h3>
      <span class="title">Head of Marketing</span>
    </div>
    <div class="team-member">
      <h3>Bob Jones</h3>
      <p>Just some bio text without a clear role.</p>
    </div>
  </section>
  <footer>Copyright Acme Inc. All rights reserved.</footer>
</body></html>
"""


class TestExtractPeople:
    def test_extracts_named_people_with_titles(self) -> None:
        people = extract_people_from_html(_TEAM_HTML, "https://acme.com/team")
        by_name = {p.full_name: p for p in people}
        assert "Jane Smith" in by_name
        assert by_name["Jane Smith"].title == "Chief Executive Officer"
        assert by_name["John A. Doe"].title == "Head of Marketing"

    def test_titled_people_rank_above_untitled(self) -> None:
        people = extract_people_from_html(_TEAM_HTML, "https://acme.com/team")
        assert people[0].title is not None
        assert people[0].confidence >= people[-1].confidence

    def test_splits_first_and_last_name(self) -> None:
        people = extract_people_from_html(_TEAM_HTML, None)
        jane = next(p for p in people if p.full_name == "Jane Smith")
        assert jane.first_name == "Jane"
        assert jane.last_name == "Smith"

    def test_ignores_nav_and_boilerplate(self) -> None:
        people = extract_people_from_html(_TEAM_HTML, None)
        names = {p.full_name for p in people}
        assert "About Us" not in names
        assert "Home" not in names

    def test_empty_html_returns_empty(self) -> None:
        assert extract_people_from_html("", None) == []

    def test_page_without_people_returns_empty(self) -> None:
        html = "<html><body><h1>Welcome</h1><p>We sell widgets.</p></body></html>"
        assert extract_people_from_html(html, None) == []

    def test_source_url_is_recorded(self) -> None:
        people = extract_people_from_html(_TEAM_HTML, "https://acme.com/team")
        assert all(p.source_url == "https://acme.com/team" for p in people)
