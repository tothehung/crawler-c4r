from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceKind(StrEnum):
    URL_WITH_LINE = "url_with_line"
    LOCATED_BY_SYMBOL = "located_by_symbol"
    GITHUB_DIFF = "github_diff"
    INLINE_SNIPPET = "inline_snippet"
    COARSE_FILE = "coarse_file"
    GIST = "gist"
    INLINE_DIFF = "inline_diff"


CONFIDENCE_RANK: dict[EvidenceKind, int] = {
    EvidenceKind.GITHUB_DIFF: 1,
    EvidenceKind.URL_WITH_LINE: 2,
    EvidenceKind.LOCATED_BY_SYMBOL: 3,
    EvidenceKind.INLINE_SNIPPET: 4,
    EvidenceKind.COARSE_FILE: 5,
    EvidenceKind.GIST: 4,
    EvidenceKind.INLINE_DIFF: 4,
}


class ParseStatus(StrEnum):
    OK = "ok"
    REPAIRED = "repaired"
    INVALID = "invalid"
    UNRESOLVED = "unresolved"


class EvidenceCandidate(BaseModel):
    model_config = {"extra": "ignore"}

    kind: EvidenceKind
    url: str = ""
    repo: str = ""
    path: str | None = None
    ref: str | None = None
    commit_sha: str | None = None
    pull_number: int | None = None
    start_line: int | None = None
    end_line: int | None = None
    snippet: str = ""
    language: str | None = None
    symbol_hints: list[str] = Field(default_factory=list)


class FindingEvidence(BaseModel):
    id: str
    finding_id: str
    source: str
    kind: EvidenceKind
    url: str = ""
    repo: str = ""
    path: str | None = None
    ref_sha: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    snippet: str = ""
    fixed_snippet: str | None = None
    language: str = "Solidity"
    contract_name: str | None = None
    function_name: str | None = None
    parse_status: ParseStatus = ParseStatus.UNRESOLVED
    confidence_rank: int = CONFIDENCE_RANK[EvidenceKind.COARSE_FILE]
    extra: dict[str, Any] = Field(default_factory=dict)
