"""Contract-v1 resolver: exact provenance, conservative roles, no syntax claims."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote, unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field

from src.models.knowledge_contract import (
    CodeEvidence,
    FindingEvidenceLink,
    LineRange,
    stable_hash,
)
from src.services.evidence.discovery import Candidate, discover
from src.services.evidence.resolver_http import ResolutionError, ResolverHTTP
from src.services.knowledge_processing import ResolutionResult

PIPELINE_VERSION = "evidence-resolver-v1"
SHA = re.compile(r"[0-9a-f]{40}$")


class ResolverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extractor_version: Literal["evidence-resolver-v1"] = PIPELINE_VERSION
    normalization_version: Literal["identity-v1"] = "identity-v1"
    transport_mode: Literal["live", "recorded"] = "live"
    context_lines: int = Field(default=10, ge=0, le=100)
    max_candidates: int = Field(default=200, ge=1, le=1000)
    max_requests: int = Field(default=100, ge=1, le=1000)
    max_response_bytes: int = Field(default=2_000_000, ge=100, le=10_000_000)
    max_evidence_per_candidate: int = Field(default=100, ge=1, le=1000)


@dataclass(frozen=True)
class Hunk:
    old_path: str | None
    new_path: str | None
    old_start: int
    new_start: int
    before: str
    after: str


def safe_path(path: str) -> str:
    if (
        not path
        or path.startswith("/")
        or any(p in {"", ".", ".."} for p in path.split("/"))
        or "\\" in path
        or ":" in path
        or '"' in path
    ):
        raise ResolutionError("unsupported_path")
    return path


def parse_unified_diff(text: str) -> list[Hunk]:
    """Retain context and both paths, including additions/deletions/renames."""
    lines = text.splitlines(keepends=True)
    old_path = new_path = None
    hunks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git "):
            old_path = new_path = None
        elif line.startswith(("--- ", "+++ ")):
            path = line[4:].strip().split("\t")[0]
            path = (
                None
                if path == "/dev/null"
                else safe_path(path[2:] if path.startswith(("a/", "b/")) else path)
            )
            if line.startswith("--- "):
                old_path = path
            else:
                new_path = path
        elif line.startswith("@@ "):
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if not match:
                raise ResolutionError("invalid_diff_header")
            old_start, old_count, new_start, new_count = (
                int(match[1]),
                int(match[2] or 1),
                int(match[3]),
                int(match[4] or 1),
            )
            before, after = [], []
            i += 1
            while i < len(lines) and not lines[i].startswith(("@@ ", "diff --git ")):
                item = lines[i]
                if item.startswith("\\ No newline"):
                    previous = lines[i - 1][:1]
                    if previous in {"-", " "} and before:
                        before[-1] = before[-1].rstrip("\r\n")
                    if previous in {"+", " "} and after:
                        after[-1] = after[-1].rstrip("\r\n")
                elif item.startswith(" "):
                    before.append(item[1:])
                    after.append(item[1:])
                elif item.startswith("-"):
                    before.append(item[1:])
                elif item.startswith("+"):
                    after.append(item[1:])
                else:
                    raise ResolutionError("unsupported_diff_line")
                i += 1
            if len(before) != old_count or len(after) != new_count:
                raise ResolutionError("truncated_diff")
            hunks.append(
                Hunk(
                    old_path,
                    new_path,
                    old_start,
                    new_start,
                    "".join(before),
                    "".join(after),
                )
            )
            continue
        i += 1
    return hunks


class EvidenceResolver:
    def __init__(self, client, *, config: dict, store=None, token=None, heartbeat=None):
        self.config = ResolverConfig.model_validate(config)
        self.config_hash = stable_hash(config)
        self.store = store
        self.http = ResolverHTTP(
            client,
            token=token,
            max_requests=self.config.max_requests,
            max_bytes=self.config.max_response_bytes,
            before_request=heartbeat,
        )

    def __call__(self, snapshot, lease) -> ResolutionResult:
        if (
            lease.pipeline_version != PIPELINE_VERSION
            or lease.config_hash != self.config_hash
        ):
            raise ValueError(
                "Resolver version/config does not match the processing fingerprint"
            )
        self.http.requests = 0
        self.http.cache.clear()  # Cache is attempt-scoped; mutable refs cannot leak across runs.
        metadata = [snapshot.source_url]
        if isinstance(snapshot.raw_payload, dict):
            metadata += [snapshot.raw_payload.get("github_link", "")]
        candidates = discover(snapshot.content, metadata_urls=metadata)
        previous = self.store.links(lease.processing_key) if self.store else []
        links = {
            row["link_id"]: FindingEvidenceLink.model_validate(row) for row in previous
        }
        evidence = {}
        for link in links.values():
            if link.evidence_id:
                evidence[link.evidence_id] = CodeEvidence.model_validate(
                    self.store.read("code_evidence", link.evidence_id)
                )
        retry_after = 0
        for index, candidate in enumerate(candidates):
            locator = candidate.locator
            root_id = self.link_id(lease.processing_key, locator)
            old = links.get(root_id)
            if old and not old.retryable:
                continue
            try:
                if index >= self.config.max_candidates:
                    raise ResolutionError("candidate_budget_exceeded")
                pieces = self.resolve(candidate, snapshot)
                if not pieces:
                    raise ResolutionError("no_solidity_evidence")
                if len(pieces) > self.config.max_evidence_per_candidate:
                    raise ResolutionError("evidence_budget_exceeded")
                built = []
                for number, (piece, suffix, role, basis) in enumerate(pieces):
                    evidence[piece.evidence_id] = piece
                    child_locator = locator if number == 0 else locator + "/" + suffix
                    built.append(
                        self.link(
                            candidate,
                            lease,
                            child_locator,
                            evidence_id=piece.evidence_id,
                            resolution_status="resolved",
                            role=role,
                            role_basis=basis,
                        )
                    )
                # Each diff-side pair can be recovered through the root relationship.
                for number, link in enumerate(built):
                    if number:
                        link.related_link_id = built[0].link_id
                    links[link.link_id] = link
            except ResolutionError as exc:
                retry_after = max(retry_after, exc.retry_after)
                link = self.link(
                    candidate,
                    lease,
                    locator,
                    resolution_status=(
                        "retryable_error" if exc.retryable else "unavailable"
                    ),
                    error_code=exc.code,
                    retryable=exc.retryable,
                )
                links[link.link_id] = link
        used = {link.evidence_id for link in links.values() if link.evidence_id}
        return ResolutionResult(
            len(links),
            [evidence[key] for key in sorted(used)],
            list(links.values()),
            retry_after,
            allow_inventory_expansion=True,
        )

    @staticmethod
    def link_id(key, locator):
        return "lnk_" + stable_hash(["link-v1", key, locator])

    def link(self, candidate, lease, locator, **fields):
        reported = None
        if candidate.start_line and candidate.end_line >= candidate.start_line:
            reported = LineRange(
                start_line=candidate.start_line, end_line=candidate.end_line
            )
        return FindingEvidenceLink(
            link_id=self.link_id(lease.processing_key, locator),
            snapshot_id=lease.snapshot_id,
            processing_key=lease.processing_key,
            candidate_locator=locator,
            candidate_url=candidate.url,
            reported_range=reported,
            report_context=candidate.context,
            created_at=datetime.now(UTC),
            **fields,
        )

    def evidence(self, *, snippet, locator, **fields):
        if not snippet.strip():
            raise ResolutionError("empty_source")
        provisional = CodeEvidence.model_construct(
            evidence_id="pending",
            raw_snippet=snippet,
            normalized_snippet=snippet,
            locator=locator,
            normalization_version=self.config.normalization_version,
            extractor_version=self.config.extractor_version,
            created_at=datetime.now(UTC),
            **fields,
        )
        return CodeEvidence.model_validate(
            provisional.model_dump() | {"evidence_id": provisional.expected_id()}
        )

    def resolve(self, candidate: Candidate, snapshot):
        if candidate.kind == "inline":
            piece = self.evidence(
                snippet=candidate.snippet,
                locator=candidate.locator,
                origin_kind="inline",
                origin_snapshot_id=snapshot.snapshot_id,
            )
            return [(piece, "inline", candidate.role, candidate.role_basis)]
        if candidate.kind == "inline_diff":
            result = []
            for side in ["before", "after"]:
                # An inline patch may omit filenames/hunk headers. Keep original
                # patch as raw; projection is explicit and never concatenates sides.
                selected = []
                for line in candidate.snippet.splitlines(keepends=True):
                    if line.startswith(
                        (
                            "diff --git ",
                            "index ",
                            "--- ",
                            "+++ ",
                            "@@ ",
                            "\\ No newline",
                        )
                    ):
                        continue
                    if line.startswith("+" if side == "before" else "-"):
                        continue
                    selected.append(
                        line[1:] if line.startswith(("+", "-", " ")) else line
                    )
                normalized = "".join(selected)
                if not normalized.strip():
                    continue
                piece = self.evidence(
                    snippet=candidate.snippet,
                    locator=f"{candidate.locator}:{side}",
                    origin_kind="inline",
                    origin_snapshot_id=snapshot.snapshot_id,
                )
                data = piece.model_dump() | {
                    "normalized_snippet": normalized,
                    "transformations": [f"inline_diff:{side}"],
                }
                provisional = CodeEvidence.model_construct(**data)
                piece = CodeEvidence.model_validate(
                    data | {"evidence_id": provisional.expected_id()}
                )
                role = candidate.role if side == "after" else "unknown"
                result.append(
                    (
                        piece,
                        side,
                        role,
                        candidate.role_basis if role != "unknown" else None,
                    )
                )
            return result
        if candidate.kind == "github_file":
            return self.file(candidate)
        if candidate.kind == "gist":
            return self.gist(candidate)
        return self.diff(candidate)

    def sha(self, value):
        if not isinstance(value, str) or not SHA.fullmatch(value):
            raise ResolutionError("missing_immutable_revision")
        return value

    def file(self, candidate):
        parsed = urlsplit(candidate.url)
        parts = unquote(parsed.path).strip("/").split("/")
        repo = "/".join(parts[:2])
        tail = (
            parts[2:] if parsed.hostname == "raw.githubusercontent.com" else parts[3:]
        )
        if len(tail) < 2:
            raise ResolutionError("invalid_file_url")
        if parsed.fragment and candidate.start_line is None:
            raise ResolutionError("unsupported_source_anchor")
        # Try ref/path boundaries, including encoded/slash-containing branch names.
        failure = ResolutionError("not_found_or_inaccessible")
        for split in range(1, min(len(tail), 9)):
            ref, path = "/".join(tail[:split]), safe_path("/".join(tail[split:]))
            try:
                sha = (
                    ref
                    if SHA.fullmatch(ref)
                    else self.sha(
                        self.http.json(
                            f"https://api.github.com/repos/{repo}/commits/{quote(ref, safe='')}"
                        ).get("sha")
                    )
                )
                content = self.http.text(
                    f"https://raw.githubusercontent.com/{repo}/{sha}/{quote(path, safe='/')}"
                )
            except ResolutionError as exc:
                if exc.code != "not_found_or_inaccessible":
                    raise
                failure = exc
                continue
            lines = content.splitlines(keepends=True)
            start = candidate.start_line if candidate.start_line is not None else 1
            end = candidate.end_line if candidate.end_line is not None else len(lines)
            if not 1 <= start <= end <= len(lines):
                raise ResolutionError("source_range_out_of_bounds")
            start = max(1, start - self.config.context_lines)
            end = min(len(lines), end + self.config.context_lines)
            piece = self.evidence(
                snippet="".join(lines[start - 1 : end]),
                locator=f"lines:{start}-{end}",
                origin_kind="github_file",
                origin_url=f"https://github.com/{repo}/blob/{sha}/{quote(path, safe='/')}#L{start}-L{end}",
                repo=repo,
                commit_sha=sha,
                path=path,
                source_range=LineRange(start_line=start, end_line=end),
            )
            return [(piece, "file", candidate.role, candidate.role_basis)]
        raise failure

    def gist(self, candidate):
        parsed = urlsplit(candidate.url)
        parts = parsed.path.strip("/").split("/")
        gist_id = parts[0] if len(parts) == 1 else parts[1]
        revision = parts[2] if len(parts) == 3 else None
        url = f"https://api.github.com/gists/{gist_id}" + (
            f"/{revision}" if revision else ""
        )
        data = self.http.json(url)
        if data.get("truncated"):
            raise ResolutionError("gist_inventory_truncated")
        revision = self.sha(revision or (data.get("history") or [{}])[0].get("version"))
        files = data.get("files")
        if not isinstance(files, dict):
            raise ResolutionError("invalid_gist_files")
        result = []
        for name, info in sorted(files.items()):
            if not name.lower().endswith(".sol"):
                continue
            name = safe_path(name)
            anchor = "file-" + re.sub(r"[^a-z0-9-]", "-", name.lower())
            if parsed.fragment and parsed.fragment != anchor:
                continue
            snippet = info.get("content")
            if info.get("truncated") or not isinstance(snippet, str):
                owner = (data.get("owner") or {}).get("login")
                if not owner or not re.fullmatch(r"[\w-]+", owner):
                    raise ResolutionError("missing_gist_owner")
                snippet = self.http.text(
                    f"https://gist.githubusercontent.com/{owner}/{gist_id}/raw/{revision}/{quote(name, safe='')}"
                )
            piece = self.evidence(
                snippet=snippet,
                locator=f"file:{name}",
                origin_kind="gist",
                origin_url=f"https://api.github.com/gists/{gist_id}/{revision}#{anchor}",
                gist_id=gist_id,
                gist_revision=revision,
                path=name,
            )
            result.append((piece, "gist:" + name, candidate.role, candidate.role_basis))
        return result

    def diff(self, candidate):
        parts = urlsplit(candidate.url).path.strip("/").split("/")
        repo = "/".join(parts[:2])
        revision = parts[3].removesuffix(".diff").removesuffix(".patch")
        if parts[2] == "commit":
            data = self.http.json(
                f"https://api.github.com/repos/{repo}/commits/{revision}"
            )
            head = self.sha(data.get("sha"))
            parents = data.get("parents", [])
            if len(parents) != 1:
                raise ResolutionError("unsupported_root_or_merge_commit")
            base = self.sha(parents[0].get("sha"))
            url = f"https://github.com/{repo}/commit/{head}.diff"
        else:
            data = self.http.json(
                f"https://api.github.com/repos/{repo}/pulls/{revision}"
            )
            head = self.sha(data.get("head", {}).get("sha"))
            base = self.sha(data.get("base", {}).get("sha"))
            compare = self.http.json(
                f"https://api.github.com/repos/{repo}/compare/{base}...{head}"
            )
            base = self.sha(compare.get("merge_base_commit", {}).get("sha"))
            url = f"https://github.com/{repo}/compare/{base}...{head}.diff"
        hunks = parse_unified_diff(self.http.text(url))
        result = []
        for hunk in hunks:
            for side, path, start, snippet, sha in [
                ("before", hunk.old_path, hunk.old_start, hunk.before, base),
                ("after", hunk.new_path, hunk.new_start, hunk.after, head),
            ]:
                if not path or not path.lower().endswith(".sol") or not snippet.strip():
                    continue
                end = start + len(snippet.splitlines()) - 1
                if start < 1:
                    raise ResolutionError("invalid_diff_range")
                # Verify patch projection against the immutable file; a truncated
                # or misleading upstream diff must not fabricate source provenance.
                source = self.http.text(
                    f"https://raw.githubusercontent.com/{repo}/{sha}/{quote(path, safe='/')}"
                )
                if (
                    "".join(source.splitlines(keepends=True)[start - 1 : end])
                    != snippet
                ):
                    raise ResolutionError("diff_source_mismatch")
                piece = self.evidence(
                    snippet=snippet,
                    locator=f"lines:{start}-{end}:{side}",
                    origin_kind="github_diff",
                    repo=repo,
                    commit_sha=sha,
                    path=path,
                    origin_url=f"https://github.com/{repo}/blob/{sha}/{quote(path, safe='/')}#L{start}-L{end}",
                    source_range=LineRange(start_line=start, end_line=end),
                )
                role = candidate.role if side == "after" else "unknown"
                result.append(
                    (
                        piece,
                        f"diff:{path}:{start}:{side}",
                        role,
                        candidate.role_basis if role != "unknown" else None,
                    )
                )
        return result
