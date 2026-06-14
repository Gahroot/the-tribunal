"""Lead magnet API validation tests."""

import pytest
from fastapi import HTTPException, status

from app.api.v1.lead_magnets import validate_lead_magnet_content


def test_rich_lead_magnet_requires_content_data() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_lead_magnet_content(
            magnet_type="quiz",
            content_url="",
            content_data=None,
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "content_data is required" in exc_info.value.detail


def test_rich_lead_magnet_allows_empty_content_url_with_content_data() -> None:
    validate_lead_magnet_content(
        magnet_type="calculator",
        content_url="",
        content_data={"title": "ROI Calculator", "inputs": [{}], "outputs": [{}]},
    )


def test_url_backed_lead_magnet_requires_content_url() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_lead_magnet_content(
            magnet_type="pdf",
            content_url="",
            content_data=None,
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "content_url is required" in exc_info.value.detail
