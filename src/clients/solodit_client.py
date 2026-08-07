from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = PROJECT_ROOT / "data" / "sample_response.json"
DEFAULT_BASE_URL = "https://solodit.cyfrin.io"
DEFAULT_ENDPOINT = "/api/v1/solodit/findings"
DEFAULT_LANGUAGE = "Solidity"
DEFAULT_TIMEOUT = 30.0
DEFAULT_REQUEST_DELAY_SECONDS = 0.1

logger = logging.getLogger(__name__)

StopCondition = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class FindingsPage:
    findings: list[dict[str, Any]]
    current_page: int
    total_pages: int
    page_size: int
    metadata: dict[str, Any]
    response_data: dict[str, Any]


@dataclass(frozen=True)
class PaginationOptions:
    start_page: int = 1
    max_pages: int | None = None
    stop_condition: StopCondition | None = None
    request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS

    def __post_init__(self) -> None:
        if self.start_page < 1:
            raise ValueError("start_page must be greater than or equal to 1")
        if self.max_pages is not None and self.max_pages < 1:
            raise ValueError("max_pages must be greater than or equal to 1")
        if self.request_delay_seconds < 0:
            raise ValueError("request_delay_seconds must be greater than or equal to 0")


class SoloditClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise RuntimeError("Missing CYFRIN_API_KEY. Add it to .env or export it before running.")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self.timeout = timeout
        self._http_client = http_client

    @property
    def url(self) -> str:
        return f"{self.base_url}{self.endpoint}"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Cyfrin-API-Key": self.api_key,
        }

    def fetch_findings(
        self,
        page_size: int,
        filters: dict[str, Any] | None = None,
        pagination: PaginationOptions | None = None,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []

        for findings_page in self.iter_findings_pages(
            page_size=page_size,
            filters=filters,
            pagination=pagination,
        ):
            findings.extend(findings_page.findings)

        return findings

    def iter_findings_pages(
        self,
        page_size: int,
        filters: dict[str, Any] | None = None,
        pagination: PaginationOptions | None = None,
    ) -> Any:
        pagination = pagination or PaginationOptions()
        filters = filters or _default_filters()
        page = pagination.start_page
        fetched_pages = 0

        while True:
            response_data = self.fetch_findings_page(
                page=page,
                page_size=page_size,
                filters=filters,
            )
            page_findings = response_data.get("findings", [])
            if not isinstance(page_findings, list):
                raise ValueError("Solodit response field 'findings' must be a list")

            metadata = response_data.get("metadata", {})
            current_page = _metadata_int(metadata, "currentPage", page)
            total_pages = _metadata_int(metadata, "totalPages", current_page)
            response_page_size = _metadata_int(metadata, "pageSize", page_size)

            logger.info(
                "Fetched Solodit findings page",
                extra={
                    "current_page": current_page,
                    "total_pages": total_pages,
                    "page_size": response_page_size,
                    "findings_count": len(page_findings),
                },
            )

            yield FindingsPage(
                findings=page_findings,
                current_page=current_page,
                total_pages=total_pages,
                page_size=response_page_size,
                metadata=metadata if isinstance(metadata, dict) else {},
                response_data=response_data,
            )
            fetched_pages += 1

            if not page_findings:
                break
            if current_page >= total_pages:
                break
            if pagination.max_pages is not None and fetched_pages >= pagination.max_pages:
                break
            if pagination.stop_condition is not None and pagination.stop_condition(response_data):
                break

            if pagination.request_delay_seconds:
                time.sleep(pagination.request_delay_seconds)

            page = current_page + 1

    def fetch_findings_page(
        self,
        page: int,
        page_size: int,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "page": page,
            "pageSize": page_size,
            "filters": filters or _default_filters(),
        }

        client = self._http_client
        if client is not None:
            return self._post_findings(client, payload)

        with httpx.Client(timeout=self.timeout) as managed_client:
            return self._post_findings(managed_client, payload)

    def _post_findings(
        self,
        client: httpx.Client,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = client.post(self.url, headers=self.headers, json=payload)
        if response.is_error:
            logger.error(
                "Solodit request failed",
                extra={
                    "status_code": response.status_code,
                    "response_text": response.text,
                },
            )
        response.raise_for_status()
        return response.json()


def fetch_sample_findings() -> dict[str, Any]:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("CYFRIN_API_KEY")
    base_url = os.getenv("SOLODIT_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    page_size = int(os.getenv("SOLODIT_PAGE_SIZE", "1"))

    client = SoloditClient(api_key=api_key or "", base_url=base_url)
    return client.fetch_findings_page(
        page=1,
        page_size=min(page_size, 5),
        filters=_default_filters(),
    )


def fetch_findings(
    max_pages: int | None = None,
    start_page: int = 1,
    stop_condition: StopCondition | None = None,
    request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
) -> list[dict[str, Any]]:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("CYFRIN_API_KEY")
    base_url = os.getenv("SOLODIT_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    page_size = int(os.getenv("SOLODIT_PAGE_SIZE", "100"))
    client = SoloditClient(api_key=api_key or "", base_url=base_url)

    return client.fetch_findings(
        page_size=page_size,
        filters=_default_filters(),
        pagination=PaginationOptions(
            start_page=start_page,
            max_pages=max_pages,
            stop_condition=stop_condition,
            request_delay_seconds=request_delay_seconds,
        ),
    )


def save_json(data: dict[str, Any], output_path: Path = OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_response(data: dict[str, Any]) -> dict[str, Any]:
    for finding in data.get("findings", []):
        if not isinstance(finding, dict):
            continue

        report_date: dict[str, Any] | None = finding.get("report_date") or None
        finding["report_date"] = report_date

    return data


def _default_filters() -> dict[str, Any]:
    return {
        "languages": [{"value": DEFAULT_LANGUAGE}],
    }


def _metadata_int(metadata: Any, key: str, default: int) -> int:
    if not isinstance(metadata, dict):
        return default

    value = metadata.get(key, default)
    if value is None:
        return default
    return int(value)


def main() -> None:
    data = normalize_response(fetch_sample_findings())
    pretty_json = json.dumps(data, ensure_ascii=False, indent=2)
    print(pretty_json)
    save_json(data)
    print(f"\nSaved response to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
