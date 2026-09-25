"""Exercise real inbox HTTP boundaries with the project's redacting eyes probe."""

import json
import statistics
import subprocess
import time
from pathlib import Path

import httpx

from app.core.security import create_access_token
from tests.integration.test_inbox_postgres import OTHER_WORKSPACE, WORKSPACE

ROOT = Path(__file__).resolve().parents[3]
BASE = "http://127.0.0.1:8001"


def main() -> None:
    # Refuse to point this diagnostic at a regular/live API, even accidentally.
    ready = httpx.get(BASE + "/readyz").json()
    assert ready.get("fixture") is True and ready.get("delivery_disabled") is True
    token = create_access_token({"sub": "1"})
    auth = {"Authorization": f"Bearer {token}"}
    root = f"/api/v1/workspaces/{WORKSPACE}/conversations"
    cases = [
        (root + "/inbox?view=waiting", "GET", None, True, 200),
        (root + "/inbox/search", "POST", {"q": "Fixture Lead"}, True, 200),
        (root + "/00000000-0000-0000-0000-000000000079/inbox-detail", "GET", None, True, 200),
        (root + "/00000000-0000-0000-0000-000000000079/messages", "GET", None, True, 200),
        (
            root + "/00000000-0000-0000-0000-000000000079/read",
            "POST",
            {"last_message_at": "2026-09-24T12:00:00Z", "unread_count": 1},
            True,
            200,
        ),
        (root + "/inbox?page_size=101", "GET", None, True, 422),
        (root + "/00000000-0000-0000-0000-0000000000c8/inbox-detail", "GET", None, True, 404),
        (f"/api/v1/workspaces/{OTHER_WORKSPACE}/conversations/inbox", "GET", None, True, 404),
        (root + "/inbox", "GET", None, False, 401),
    ]
    observations = []
    for path, method, body, authenticated, status in cases:
        argv = [
            str(ROOT / ".ezcoder/eyes/http.sh"),
            BASE + path,
            method,
            json.dumps(body) if body is not None else "",
        ]
        if authenticated:
            argv.extend(["-H", f"Authorization: Bearer {token}"])
        process = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        if process.returncode:
            raise RuntimeError(f"HTTP probe failed for {path} with exit {process.returncode}")
        result = json.loads(process.stdout)
        # Read the probe's saved redacted artifact, not just its exit code.
        payload = json.loads(Path(result["body"]).read_text())
        assert result["status"] == status, (path, result["status"])
        if status == 200 and ("/inbox?" in path or path.endswith("/inbox/search")):
            assert set(payload) == {"items", "counts", "total", "page", "page_size", "pages"}
            assert len(payload["items"]) <= 50
            assert all(item["workspace_id"] == str(WORKSPACE) for item in payload["items"])
        if status in (401, 404, 422):
            assert "items" not in payload
        observations.append(
            {"path": path, "method": method, "status": status, "body_inspected": True}
        )

    # Same local synthetic dataset. Legacy page-100 reflects the former UI;
    # page-50 comparisons isolate query changes from the row-count reduction.
    timings = {}
    with httpx.Client(base_url=BASE, headers=auth, timeout=10) as client:
        for label, path in {
            "legacy_page100": root + "?page=1&page_size=100",
            "legacy_page50": root + "?page=1&page_size=50",
            "inbox_page50": root + "/inbox?page=1&page_size=50",
        }.items():
            samples = []
            for _ in range(11):
                start = time.perf_counter()
                response = client.get(path)
                response.raise_for_status()
                samples.append((time.perf_counter() - start) * 1000)
            timings[label] = {
                "first_ms": round(samples[0], 2),
                "warm_median_ms": round(statistics.median(samples[1:]), 2),
                "warm_max_ms": round(max(samples[1:]), 2),
                "response_bytes": len(response.content),
                "rows": len(response.json()["items"]),
            }
    report = {"fixture_only": True, "http_checks": observations, "local_timings": timings}
    out = ROOT / ".ezcoder/eyes/out/inbox-http-verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
