from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.models import Finding
from src.models.evidence import EvidenceCandidate, EvidenceKind
from src.services.evidence.discovery import discover

GITHUB_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?github\.com/"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)"
    r"(?:/(?:blob|tree)/(?P<ref>[^/\s#]+)(?:/(?P<path>[^#\s]+))?"
    r"|/commit/(?P<commit_sha>[0-9a-f]{7,40})"
    r"|/pull/(?P<pull_number>\d+))"
    r"(?:#L(?P<start_line>\d+)(?:-L(?P<end_line>\d+))?)?",
    re.IGNORECASE,
)

FENCED_BLOCK_PATTERN = re.compile(
    r"```(?P<language>[A-Za-z0-9_+-]*)[ \t]*\r?\n" r"(?P<body>.*?)" r"```",
    re.DOTALL,
)

SOLIDITY_HINT_PATTERN = re.compile(
    r"\b(?:pragma\s+solidity|contract\s+\w+|interface\s+\w+|library\s+\w+"
    r"|function\s+\w+\s*\(|modifier\s+\w+|mapping\s*\(|payable\b"
    r"|address\s+(?:payable\s+)?\w+|require\s*\(|emit\s+\w+)\b"
)

SYMBOL_HINT_PATTERN = re.compile(
    r"\b(?:(?P<contract>[A-Z][A-Za-z0-9_]*)\.(?P<function>[a-zA-Z_][A-Za-z0-9_]*))"
)


@dataclass(frozen=True)
class ScanResult:
    candidates: list[EvidenceCandidate]
    symbol_hints: list[str] = field(default_factory=list)

    @property
    def has_code_evidence(self) -> bool:
        return any(c.kind != EvidenceKind.COARSE_FILE for c in self.candidates)


def scan(finding: Finding, *, context_window: int = 10) -> ScanResult:
    body = "\n".join(part for part in (finding.summary, finding.content) if part)
    links = [finding.github_link, finding.source_link]
    symbol_hints = _collect_symbol_hints(finding.title + "\n" + body)

    candidates: list[EvidenceCandidate] = []
    for node in discover(body, metadata_urls=links):
        if node.kind in {"inline", "inline_diff", "gist"}:
            kind = {
                "inline": EvidenceKind.INLINE_SNIPPET,
                "inline_diff": EvidenceKind.INLINE_DIFF,
                "gist": EvidenceKind.GIST,
            }[node.kind]
            candidates.append(
                EvidenceCandidate(
                    kind=kind,
                    url=node.url or "",
                    snippet=node.snippet or "",
                    language="Solidity",
                    symbol_hints=symbol_hints,
                )
            )
        else:
            candidate = _candidate_from_url(node.url, symbol_hints, context_window)
            if candidate:
                candidate.url = node.url.split("#")[0]
                candidate.start_line = node.start_line
                candidate.end_line = node.end_line
                if node.kind == "github_file" and node.start_line:
                    candidate.kind = EvidenceKind.URL_WITH_LINE
                candidates.append(candidate)

    return ScanResult(candidates=candidates, symbol_hints=symbol_hints)


@dataclass(frozen=True)
class _FencedBlock:
    language: str | None
    snippet: str


def _extract_fenced_blocks(body: str) -> list[_FencedBlock]:
    blocks: list[_FencedBlock] = []

    for match in FENCED_BLOCK_PATTERN.finditer(body):
        raw_language = (match.group("language") or "").strip().lower()
        snippet = match.group("body")

        if not snippet.strip():
            continue

        if (
            raw_language == "solidity"
            or raw_language == ""
            and SOLIDITY_HINT_PATTERN.search(snippet)
        ):
            blocks.append(_FencedBlock(language="Solidity", snippet=snippet))

    return blocks


def _candidate_from_url(
    url: str,
    symbol_hints: list[str],
    context_window: int,
) -> EvidenceCandidate | None:
    match = GITHUB_URL_PATTERN.search(url)
    if not match:
        return None

    repo = f"{match.group('owner')}/{match.group('repo')}"
    ref = match.group("ref")
    path = match.group("path")
    commit_sha = match.group("commit_sha")
    pull_number = match.group("pull_number")
    start_line = match.group("start_line")
    end_line = match.group("end_line")

    if commit_sha or pull_number:
        return EvidenceCandidate(
            kind=EvidenceKind.GITHUB_DIFF,
            url=url,
            repo=repo,
            commit_sha=commit_sha,
            pull_number=int(pull_number) if pull_number else None,
            symbol_hints=symbol_hints,
        )

    if path is None:
        return None

    clean_path = path.removesuffix(".git").removesuffix("/")

    if start_line:
        return EvidenceCandidate(
            kind=EvidenceKind.URL_WITH_LINE,
            url=url.split("#")[0],
            repo=repo,
            ref=ref,
            path=clean_path,
            start_line=int(start_line),
            end_line=int(end_line) if end_line else int(start_line),
            symbol_hints=symbol_hints,
        )

    return EvidenceCandidate(
        kind=EvidenceKind.LOCATED_BY_SYMBOL,
        url=url.split("#")[0],
        repo=repo,
        ref=ref,
        path=clean_path,
        start_line=None,
        end_line=None,
        symbol_hints=symbol_hints,
    )


def _collect_symbol_hints(body: str) -> list[str]:
    hints: list[str] = []
    for match in SYMBOL_HINT_PATTERN.finditer(body):
        contract = match.group("contract")
        function = match.group("function")
        hint = f"{contract}.{function}"
        if hint not in hints:
            hints.append(hint)
    return hints
