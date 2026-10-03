"""Bounded GitHub reads. No redirects to arbitrary hosts; never execute source."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx

HOSTS = {
    "api.github.com",
    "github.com",
    "raw.githubusercontent.com",
    "gist.githubusercontent.com",
    "patch-diff.githubusercontent.com",
}


class ResolutionError(Exception):
    def __init__(self, code: str, *, retryable: bool = False, retry_after: float = 0):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after


def retry_delay(headers) -> float:
    value = headers.get("retry-after", "")
    if value.isdigit():
        return float(value)
    if value:
        try:
            return max(
                0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
            )
        except (ValueError, TypeError):
            pass
    reset = headers.get("x-ratelimit-reset", "")
    return (
        max(0, float(reset) - datetime.now(UTC).timestamp()) if reset.isdigit() else 0
    )


class ResolverHTTP:
    def __init__(
        self,
        client: httpx.Client,
        *,
        token: str | None = None,
        max_requests: int = 100,
        max_bytes: int = 2_000_000,
        before_request=None,
    ):
        self.client = client
        self.token = token
        self.max_requests = max_requests
        self.max_bytes = max_bytes
        self.before_request = before_request
        self.requests = 0
        self.cache = {}

    def text(self, url: str) -> str:
        if url in self.cache:
            return self.cache[url]
        original = url
        for _ in range(4):
            try:
                parsed = urlsplit(url)
                port = parsed.port
            except ValueError as exc:
                raise ResolutionError("unsupported_host") from exc
            if (
                parsed.scheme != "https"
                or parsed.hostname not in HOSTS
                or parsed.username
                or parsed.password
                or port
            ):
                raise ResolutionError("unsupported_host")
            if self.requests >= self.max_requests:
                raise ResolutionError("request_budget_exceeded", retryable=True)
            if self.before_request:
                self.before_request()
            self.requests += 1
            headers = {"User-Agent": "w3goaudit-resolver-v1"}
            if self.token and parsed.hostname == "api.github.com":
                headers["Authorization"] = f"Bearer {self.token}"
            try:
                with self.client.stream(
                    "GET", url, headers=headers, follow_redirects=False
                ) as response:
                    status = response.status_code
                    if status in {301, 302, 303, 307, 308}:
                        url = str(
                            response.url.join(response.headers.get("location", ""))
                        )
                        continue
                    if status == 404:
                        raise ResolutionError("not_found_or_inaccessible")
                    if (
                        status == 429
                        or status >= 500
                        or (
                            status == 403
                            and (
                                response.headers.get("x-ratelimit-remaining") == "0"
                                or "retry-after" in response.headers
                            )
                        )
                    ):
                        raise ResolutionError(
                            f"http_{status}",
                            retryable=True,
                            retry_after=retry_delay(response.headers),
                        )
                    if status != 200:
                        raise ResolutionError(f"http_{status}")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > self.max_bytes:
                            raise ResolutionError("response_too_large")
                    try:
                        result = data.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise ResolutionError("non_utf8_response") from exc
                    self.cache[original] = result
                    return result
            except httpx.TransportError as exc:
                raise ResolutionError("transport_error", retryable=True) from exc
        raise ResolutionError("redirect_limit")

    def json(self, url: str) -> dict:
        try:
            data = json.loads(self.text(url))
        except json.JSONDecodeError as exc:
            raise ResolutionError("invalid_json", retryable=True) from exc
        if not isinstance(data, dict):
            raise ResolutionError("unexpected_json")
        return data
