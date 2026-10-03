from __future__ import annotations

import hashlib
import re


WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_snippet(snippet: str) -> str:
    return "\n".join(line.rstrip() for line in snippet.strip().split("\n"))


def evidence_fingerprint(
    *,
    repo: str = "",
    path: str | None = None,
    ref_sha: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    snippet: str = "",
) -> str:
    normalized_snippet = WHITESPACE_PATTERN.sub(" ", normalize_snippet(snippet)).strip()
    payload = "|".join(
        [
            repo,
            path or "",
            ref_sha or "",
            str(start_line) if start_line is not None else "",
            str(end_line) if end_line is not None else "",
            hashlib.sha256(normalized_snippet.encode("utf-8")).hexdigest(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Deduplicator:
    """Tracks seen evidence fingerprints within a run.

    When the same evidence (same code at the same location) shows up in
    multiple findings, the first occurrence wins and later ones are
    reported as duplicates so the caller can link instead of insert.
    """

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}

    def register(self, fingerprint: str, evidence_id: str) -> str | None:
        existing_id = self._seen.get(fingerprint)
        if existing_id is not None:
            return existing_id

        self._seen[fingerprint] = evidence_id
        return None

    def __contains__(self, fingerprint: object) -> bool:
        return isinstance(fingerprint, str) and fingerprint in self._seen
