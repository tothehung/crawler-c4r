from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from src.clients.solodit_client import PaginationOptions, SoloditClient


def _response(
    findings: list[dict[str, Any]],
    current_page: int,
    total_pages: int,
    page_size: int = 2,
) -> dict[str, Any]:
    return {
        "findings": findings,
        "metadata": {
            "currentPage": current_page,
            "totalPages": total_pages,
            "pageSize": page_size,
        },
        "rateLimit": {
            "limit": 20,
            "remaining": 19,
            "reset": 1785564900,
        },
    }


def _client_for_pages(
    pages: dict[int, dict[str, Any]],
    requested_pages: list[int],
) -> SoloditClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        page = body["page"]
        requested_pages.append(page)
        return httpx.Response(200, json=pages[page])

    return SoloditClient(
        api_key="test-api-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_fetch_findings_single_page_response() -> None:
    # Arrange
    requested_pages: list[int] = []
    client = _client_for_pages(
        pages={
            1: _response(
                findings=[{"id": "finding-1"}, {"id": "finding-2"}],
                current_page=1,
                total_pages=1,
            )
        },
        requested_pages=requested_pages,
    )

    # Act
    findings = client.fetch_findings(
        page_size=2,
        pagination=PaginationOptions(request_delay_seconds=0),
    )

    # Assert
    assert findings == [{"id": "finding-1"}, {"id": "finding-2"}]
    assert requested_pages == [1]


def test_fetch_findings_multiple_pages() -> None:
    # Arrange
    requested_pages: list[int] = []
    client = _client_for_pages(
        pages={
            1: _response(
                findings=[{"id": "finding-1"}],
                current_page=1,
                total_pages=3,
            ),
            2: _response(
                findings=[{"id": "finding-2"}],
                current_page=2,
                total_pages=3,
            ),
            3: _response(
                findings=[{"id": "finding-3"}],
                current_page=3,
                total_pages=3,
            ),
        },
        requested_pages=requested_pages,
    )

    # Act
    findings = client.fetch_findings(
        page_size=2,
        pagination=PaginationOptions(request_delay_seconds=0),
    )

    # Assert
    assert findings == [
        {"id": "finding-1"},
        {"id": "finding-2"},
        {"id": "finding-3"},
    ]
    assert requested_pages == [1, 2, 3]


def test_fetch_findings_stops_on_empty_last_page() -> None:
    # Arrange
    requested_pages: list[int] = []
    client = _client_for_pages(
        pages={
            1: _response(
                findings=[{"id": "finding-1"}],
                current_page=1,
                total_pages=3,
            ),
            2: _response(
                findings=[{"id": "finding-2"}],
                current_page=2,
                total_pages=3,
            ),
            3: _response(findings=[], current_page=3, total_pages=3),
        },
        requested_pages=requested_pages,
    )

    # Act
    findings = client.fetch_findings(
        page_size=2,
        pagination=PaginationOptions(request_delay_seconds=0),
    )

    # Assert
    assert findings == [{"id": "finding-1"}, {"id": "finding-2"}]
    assert requested_pages == [1, 2, 3]


def test_fetch_findings_raises_on_api_error_during_pagination() -> None:
    # Arrange
    requested_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        page = body["page"]
        requested_pages.append(page)
        if page == 2:
            return httpx.Response(500, json={"error": "internal error"})
        return httpx.Response(
            200,
            json=_response(
                findings=[{"id": "finding-1"}],
                current_page=1,
                total_pages=3,
            ),
        )

    client = SoloditClient(
        api_key="test-api-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    # Act / Assert
    with pytest.raises(httpx.HTTPStatusError):
        client.fetch_findings(
            page_size=2,
            pagination=PaginationOptions(request_delay_seconds=0),
        )
    assert requested_pages == [1, 2]
