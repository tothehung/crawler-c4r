"""Capture immutable Git blobs and persist engine context beside contract-v1 rows.

No checkout, dependency installation, build hooks, source execution or network.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from src.models.knowledge_contract import CodeEvidence, stable_hash
from src.services.evidence.engine_validator import (
    EngineValidationError,
    EngineValidator,
)


class ContextUnavailable(ValueError):
    """Source cannot be safely bound to this evidence; not a syntax failure."""


def _git(root: Path, *arguments: str) -> bytes:
    command = [
        "git",
        "--no-replace-objects",
        "-c",
        f"safe.directory={root.as_posix()}",
        "-C",
        str(root),
        *arguments,
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EngineValidationError(
            f"Git process failed: {type(exc).__name__}"
        ) from exc
    if result.returncode:
        raise ContextUnavailable(
            f"Git {arguments[0]} failed: {result.stderr.decode('utf-8', errors='replace')[:500]}"
        )
    return result.stdout


def capture_bundle(evidence: CodeEvidence, root: Path) -> dict:
    if evidence.origin_kind not in {"github_file", "github_diff"}:
        raise ContextUnavailable("no_immutable_repository_provenance")
    if (
        not evidence.source_range
        or evidence.transformations
        or evidence.raw_snippet != evidence.normalized_snippet
    ):
        raise ContextUnavailable("no_unchanged_contiguous_source_range")
    root = root.resolve(strict=True)
    # Bind the explicitly mapped checkout to its declared upstream repository.
    remote = _git(root, "config", "--get", "remote.origin.url").decode().strip()
    expected = evidence.repo.lower().removesuffix(".git")
    allowed = {
        f"https://github.com/{expected}",
        f"git@github.com:{expected}",
        f"ssh://git@github.com/{expected}",
    }
    if remote.lower().removesuffix(".git").rstrip("/") not in allowed:
        raise ContextUnavailable("repository_origin_mismatch")
    commit = (
        _git(root, "rev-parse", "--verify", f"{evidence.commit_sha}^{{commit}}")
        .decode()
        .strip()
    )
    if commit != evidence.commit_sha:
        raise ContextUnavailable("commit_mismatch")
    entries = _git(root, "ls-tree", "-rz", "--full-tree", commit).split(b"\0")
    sources = []
    total = 0
    for entry in entries:
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
        if not path.endswith(".sol"):
            continue
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ContextUnavailable("non_regular_solidity_source: " + path)
        size = int(_git(root, "cat-file", "-s", oid))
        total += size
        if size > 2_000_000 or total > 4_000_000 or len(sources) >= 100:
            raise ContextUnavailable("source_bundle_limit_exceeded")
        data = _git(root, "cat-file", "blob", oid)
        sources.append({"path": path, "content": data.decode("utf-8")})
    sources.sort(key=lambda item: item["path"])
    target = next((s["content"] for s in sources if s["path"] == evidence.path), None)
    if target is None:
        raise ContextUnavailable("evidence_file_missing_at_commit")
    lines = target.splitlines()
    start, end = evidence.source_range.start_line, evidence.source_range.end_line
    # Compare actual content, not just a filename or a mutable branch reference.
    if end > len(lines) or lines[start - 1 : end] != evidence.raw_snippet.splitlines():
        raise ContextUnavailable("evidence_does_not_match_commit_range")
    return {"repo": evidence.repo, "commit_sha": commit, "sources": sources}


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".context-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def enrich_context(
    evidence: CodeEvidence, validator: EngineValidator, root: Path, output: Path
) -> dict:
    bundle = capture_bundle(evidence, root)
    bundle_id = stable_hash(bundle)
    request = {
        "evidence_id": evidence.evidence_id,
        "sources": bundle["sources"],
        "path": evidence.path,
        "start_line": evidence.source_range.start_line,
        "end_line": evidence.source_range.end_line,
    }
    result = validator._call(["evidence-context"], request)
    hashes = {
        s["path"]: hashlib.sha256(s["content"].encode("utf-8")).hexdigest()
        for s in bundle["sources"]
    }
    if (
        result.get("protocol_version") != "1.0"
        or result.get("context_version") != "solast-go@v0.1.4/repo-context-v1"
        or result.get("evidence_id") != evidence.evidence_id
        or result.get("source_hashes") != hashes
        or result.get("status") not in {"available", "partial", "unavailable"}
        or not isinstance(result.get("contracts"), list)
        or not isinstance(result.get("functions"), list)
        or not isinstance(result.get("diagnostics"), list)
    ):
        raise EngineValidationError(
            "Context response does not match source bundle/protocol"
        )
    for fn in result["functions"]:
        if (
            not isinstance(fn, dict)
            or fn.get("path") != evidence.path
            or not isinstance(fn.get("start_line"), int)
            or not isinstance(fn.get("end_line"), int)
            or not 1
            <= fn["start_line"]
            <= fn["end_line"]
            <= len(
                next(
                    s["content"]
                    for s in bundle["sources"]
                    if s["path"] == evidence.path
                ).splitlines()
            )
            or fn["end_line"] < request["start_line"]
            or fn["start_line"] > request["end_line"]
        ):
            raise EngineValidationError(
                "Context function range does not match evidence"
            )
    annotation = {
        "schema_version": "1.0",
        "evidence_id": evidence.evidence_id,
        "bundle_id": bundle_id,
        "repo": evidence.repo,
        "commit_sha": evidence.commit_sha,
        "source_range": evidence.source_range.model_dump(mode="json"),
        "engine_binary_sha256": validator.binary_hash,
        "result": result,
    }
    context_id = "ctx_" + stable_hash(annotation)
    # The bundle is committed before its referencing annotation. Neither changes
    # contract-v1 syntax status, evidence identity nor source text.
    _atomic_json(output / "bundles" / f"{bundle_id}.json", bundle)
    _atomic_json(
        output / "annotations" / f"{context_id}.json",
        annotation | {"context_id": context_id},
    )
    return {
        "evidence_id": evidence.evidence_id,
        "status": result["status"],
        "context_id": context_id,
        "annotation": str((output / "annotations" / f"{context_id}.json").resolve()),
        "diagnostics": result["diagnostics"],
    }


def enrich_batch(
    store,
    validator: EngineValidator,
    repositories: dict[str, str],
    output: Path,
    *,
    after: str = "",
    limit: int = 100,
) -> dict:
    rows = store.evidence(after=after, limit=limit)
    results = []
    for row in rows:
        evidence = CodeEvidence.model_validate(row)
        try:
            local = repositories.get(evidence.repo or "")
            if not local:
                raise ContextUnavailable(
                    "repository_not_configured"
                    if evidence.repo
                    else "no_immutable_repository_provenance"
                )
            results.append(enrich_context(evidence, validator, Path(local), output))
        except ContextUnavailable as exc:
            results.append(
                {
                    "evidence_id": evidence.evidence_id,
                    "status": "unavailable",
                    "reason": str(exc),
                }
            )
        except (EngineValidationError, OSError, UnicodeError) as exc:
            results.append(
                {
                    "evidence_id": evidence.evidence_id,
                    "status": "error",
                    "reason": str(exc),
                }
            )
    report = {
        "schema_version": "1.0",
        "engine_binary_sha256": validator.binary_hash,
        "next_after": rows[-1]["evidence_id"] if rows else None,
        "counts": {
            status: sum(r["status"] == status for r in results)
            for status in ("available", "partial", "unavailable", "error")
        },
        "results": results,
    }
    _atomic_json(output / "reports" / f"{stable_hash(report)}.json", report)
    return report
