"""Verified, strict recorded transport for reproducible offline resolver runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx

from src.services.evidence.resolver_http import ResolutionError


def replay_transport(directory: Path) -> httpx.MockTransport:
    directory = directory.resolve()
    records = {}
    for row in json.loads((directory / "index.json").read_text(encoding="utf-8")):
        path = (directory / row["body_file"]).resolve()
        if not path.is_relative_to(directory):
            raise ValueError("Recorded body path escapes fixture directory")
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != row["sha256"]:
            raise ValueError("Recorded response hash mismatch")
        records[row["url"]] = (row, body)

    def handler(request):
        record = records.get(str(request.url))
        if record is None:
            # This is missing test coverage, never evidence of a real HTTP 404.
            raise ResolutionError("fixture_missing", retryable=True)
        row, body = record
        return httpx.Response(
            row["status_code"], content=body, headers=row.get("headers", {})
        )

    return httpx.MockTransport(handler)
