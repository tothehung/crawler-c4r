from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.models import Finding
from src.models.evidence import (
    CONFIDENCE_RANK,
    EvidenceCandidate,
    EvidenceKind,
    FindingEvidence,
    ParseStatus,
)
from src.services.evidence.dedup import Deduplicator, evidence_fingerprint
from src.services.evidence.github_fetcher import GitHubFetchError, GitHubFetcher
from src.services.evidence.scan_body import scan
from src.services.evidence.snippet_cleaner import clean
from src.services.evidence.validator import (
    ValidationResult,
    expand_window,
    locate_symbol,
    validate,
)


logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_LINES = 10
MAX_DIFF_HUNKS_PER_FINDING = 5


@dataclass(frozen=True)
class EvidencePipelineResult:
    finding_id: str
    source: str
    evidences: list[FindingEvidence]
    unresolved_urls: list[str] = field(default_factory=list)

    @property
    def has_code_evidence(self) -> bool:
        return any(e.parse_status != ParseStatus.UNRESOLVED for e in self.evidences)


class EvidencePipeline:
    def __init__(
        self,
        fetcher: GitHubFetcher,
        *,
        deduplicator: Deduplicator | None = None,
        context_lines: int = DEFAULT_CONTEXT_LINES,
        max_diff_hunks: int = MAX_DIFF_HUNKS_PER_FINDING,
    ) -> None:
        self.fetcher = fetcher
        self.dedup = deduplicator or Deduplicator()
        self.context_lines = context_lines
        self.max_diff_hunks = max_diff_hunks

    def process(self, finding: Finding) -> EvidencePipelineResult:
        candidates = scan(finding).candidates
        candidates.sort(key=lambda c: CONFIDENCE_RANK[c.kind])

        evidences: list[FindingEvidence] = []
        unresolved_urls: list[str] = []

        for candidate in candidates:
            try:
                built = self._build(finding, candidate)
            except GitHubFetchError as exc:
                logger.warning(
                    "Unresolved evidence for finding %s (%s): %s",
                    finding.id,
                    candidate.url or candidate.kind.value,
                    exc,
                )
                if candidate.url:
                    unresolved_urls.append(candidate.url)
                continue

            evidences.extend(built)

        return EvidencePipelineResult(
            finding_id=finding.id,
            source="solodit",
            evidences=evidences,
            unresolved_urls=unresolved_urls,
        )

    def _build(
        self,
        finding: Finding,
        candidate: EvidenceCandidate,
    ) -> list[FindingEvidence]:
        match candidate.kind:
            case EvidenceKind.URL_WITH_LINE:
                evidence = self._build_url_with_line(finding, candidate)
                return [evidence] if evidence else []
            case EvidenceKind.LOCATED_BY_SYMBOL:
                evidence = self._build_located_by_symbol(finding, candidate)
                return [evidence] if evidence else []
            case EvidenceKind.GITHUB_DIFF:
                return self._build_from_diff(finding, candidate)
            case EvidenceKind.INLINE_SNIPPET:
                evidence = self._build_inline(finding, candidate)
                return [evidence] if evidence else []
            case _:
                return []

    def _fetch_file_at_ref(
        self,
        candidate: EvidenceCandidate,
    ) -> tuple[str, str]:
        if not (candidate.ref and candidate.path):
            raise GitHubFetchError("candidate is missing ref or path")
        ref_sha = self.fetcher.resolve_ref_sha(candidate.repo, candidate.ref)
        content = self.fetcher.fetch_file(candidate.repo, ref_sha, candidate.path)
        return ref_sha, content

    def _build_url_with_line(
        self,
        finding: Finding,
        candidate: EvidenceCandidate,
    ) -> FindingEvidence | None:
        if not (candidate.ref and candidate.path and candidate.start_line):
            return None

        ref_sha, content = self._fetch_file_at_ref(candidate)
        lines = content.split("\n")

        start, end = expand_window(
            total_lines=len(lines),
            start_line=candidate.start_line,
            end_line=candidate.end_line or candidate.start_line,
            context=self.context_lines,
        )
        snippet = clean("\n".join(lines[start - 1 : end]))

        return self._finalize(
            finding_id=finding.id,
            kind=EvidenceKind.URL_WITH_LINE,
            url=candidate.url,
            repo=candidate.repo,
            path=candidate.path,
            ref_sha=ref_sha,
            start_line=start,
            end_line=end,
            snippet=snippet,
            validation=validate(snippet),
        )

    def _build_located_by_symbol(
        self,
        finding: Finding,
        candidate: EvidenceCandidate,
    ) -> FindingEvidence | None:
        if not (candidate.ref and candidate.path):
            return None

        ref_sha, content = self._fetch_file_at_ref(candidate)
        lines = content.split("\n")

        located_start, located_end = locate_symbol(content, candidate.symbol_hints)

        if located_start is not None and located_end is not None:
            start, end = expand_window(
                total_lines=len(lines),
                start_line=located_start,
                end_line=located_end,
                context=self.context_lines,
            )
            kind = EvidenceKind.LOCATED_BY_SYMBOL
        else:
            start, end = 1, len(lines)
            kind = EvidenceKind.COARSE_FILE

        snippet = clean("\n".join(lines[start - 1 : end]))

        return self._finalize(
            finding_id=finding.id,
            kind=kind,
            url=candidate.url,
            repo=candidate.repo,
            path=candidate.path,
            ref_sha=ref_sha,
            start_line=start,
            end_line=end,
            snippet=snippet,
            validation=validate(snippet),
        )

    def _build_from_diff(
        self,
        finding: Finding,
        candidate: EvidenceCandidate,
    ) -> list[FindingEvidence]:
        if candidate.commit_sha:
            diff = self.fetcher.fetch_commit_diff(candidate.repo, candidate.commit_sha)
        elif candidate.pull_number:
            diff = self.fetcher.fetch_pull_request_diff(candidate.repo, candidate.pull_number)
        else:
            return []

        results: list[FindingEvidence] = []

        for index, hunk in enumerate(diff.hunks[: self.max_diff_hunks]):
            snippet = clean("\n".join(hunk.removed_lines))
            fixed_snippet = clean("\n".join(hunk.added_lines)) or None

            evidence = self._finalize(
                finding_id=finding.id,
                kind=EvidenceKind.GITHUB_DIFF,
                url=candidate.url,
                repo=candidate.repo,
                path=hunk.path,
                ref_sha=diff.commit_sha,
                start_line=hunk.removed_start,
                end_line=(
                    hunk.removed_start + max(len(hunk.removed_lines), 1) - 1
                    if hunk.removed_start is not None
                    else None
                ),
                snippet=snippet,
                validation=validate(snippet),
                suffix=f"-{index}",
                extra={"fixed_snippet": fixed_snippet, "added_start": hunk.added_start},
            )
            if evidence is not None:
                results.append(evidence)

        return results

    def _build_inline(
        self,
        finding: Finding,
        candidate: EvidenceCandidate,
    ) -> FindingEvidence | None:
        snippet = clean(candidate.snippet)
        if not snippet:
            return None

        return self._finalize(
            finding_id=finding.id,
            kind=EvidenceKind.INLINE_SNIPPET,
            url=candidate.url,
            repo=candidate.repo,
            snippet=snippet,
            validation=validate(snippet),
        )

    def _finalize(
        self,
        *,
        finding_id: str,
        kind: EvidenceKind,
        url: str = "",
        repo: str = "",
        path: str | None = None,
        ref_sha: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        snippet: str,
        validation: ValidationResult,
        suffix: str = "",
        extra: dict[str, object] | None = None,
    ) -> FindingEvidence | None:
        fingerprint = evidence_fingerprint(
            repo=repo,
            path=path,
            ref_sha=ref_sha,
            start_line=start_line,
            end_line=end_line,
            snippet=snippet,
        )

        evidence_id = f"{fingerprint}{suffix}"
        duplicate_of = self.dedup.register(fingerprint, evidence_id)

        merged_extra: dict[str, object] = {**(extra or {})}
        if duplicate_of:
            merged_extra["duplicate_of"] = duplicate_of

        return FindingEvidence(
            id=evidence_id,
            finding_id=finding_id,
            source="solodit",
            kind=kind,
            url=url,
            repo=repo,
            path=path,
            ref_sha=ref_sha,
            start_line=start_line,
            end_line=end_line,
            snippet=snippet,
            language="Solidity",
            contract_name=validation.contract_name,
            function_name=validation.function_name,
            parse_status=validation.status,
            confidence_rank=CONFIDENCE_RANK[kind],
            extra=merged_extra,
        )
