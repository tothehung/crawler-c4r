"""Versioned, deterministic duplicate groups without mutating source snapshots.

Group membership is O(n), not pairwise O(n²). Similar content only queues review.
URLs in arbitrary report bodies/code links never serve as identity evidence.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from urllib.parse import parse_qsl, unquote, urlsplit

from src.models.knowledge_contract import SourceFindingSnapshot, stable_hash
from src.models.knowledge_operations import FindingDedupState, FindingMembership

DEDUP_VERSION = "finding-dedup-v1"


def finding_url(value: str) -> str | None:
    """Only URLs identifying individual findings; never whole reports or code."""
    try:
        u = urlsplit(value.strip())
        if (
            u.scheme.lower() not in {"http", "https"}
            or u.username
            or u.password
            or u.port not in {None, 80, 443}
        ):
            return None
        if any(
            not (k.lower().startswith("utm_") or k.lower() in {"ref", "source"})
            for k, _ in parse_qsl(u.query)
        ):
            return None
        host = (u.hostname or "").lower().removeprefix("www.")
        path = unquote(u.path).rstrip("/")
        if host == "github.com" and re.fullmatch(
            r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/[1-9][0-9]*", path
        ):
            # Comments are not separate findings; normalize repository casing.
            return "https://github.com" + path.lower()
        if (
            host == "code4rena.com"
            and re.fullmatch(r"/reports/[A-Za-z0-9_-]+", path)
            and re.fullmatch(
                r"[hmlg]-[0-9]+(?:-[A-Za-z0-9_-]+)?", u.fragment, flags=re.IGNORECASE
            )
        ):
            return "https://code4rena.com" + path + "#" + u.fragment
        if host in {"solodit.xyz", "solodit.cyfrin.io"} and re.fullmatch(
            r"/issues/[A-Za-z0-9_-]+", path
        ):
            return "https://solodit.cyfrin.io" + path
    except ValueError:
        return None
    return None


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def memberships(
    snapshot: SourceFindingSnapshot, *, version: str = DEDUP_VERSION
) -> list[FindingMembership]:
    tokens = {("source_identity", snapshot.source_key)}
    urls = [snapshot.source_url]
    if isinstance(snapshot.raw_payload, dict):
        # source_link is the original finding link in existing crawler exports.
        original = snapshot.raw_payload.get("source_link")
        if isinstance(original, str):
            urls.append(original)
    for url in urls:
        canonical = finding_url(url)
        if canonical:
            tokens.add(("finding_url", canonical))
    content = _normalized(snapshot.content)
    title = _normalized(snapshot.title).casefold()
    if len(content) >= 80:
        tokens.add(("content_exact", stable_hash(content)))
    if len(title) >= 25:
        tokens.add(("title_exact", stable_hash(title)))
    rows = []
    for method, key in sorted(tokens):
        group = "grp_" + stable_hash([version, method, key])
        rows.append(
            FindingMembership(
                membership_id="mem_" + stable_hash([group, snapshot.snapshot_id]),
                group_id=group,
                snapshot_id=snapshot.snapshot_id,
                source_key=snapshot.source_key,
                source=snapshot.source,
                method=method,
                normalized_key=key,
                decision=(
                    "confirmed"
                    if method in {"source_identity", "finding_url"}
                    else "candidate"
                ),
                dedup_version=version,
                created_at=datetime.now(UTC),
            )
        )
    return rows


def deduplicate_page(
    store, *, after: str = "", limit: int = 100, version: str = DEDUP_VERSION
) -> dict:
    snapshots = store.scan("source_finding_snapshots", after=after, limit=limit)
    indexed = skipped = 0
    for row in snapshots:
        snapshot = SourceFindingSnapshot.model_validate(row)
        key = "ddp_" + stable_hash([snapshot.snapshot_id, version])
        with store.transaction() as tx:
            if tx.get("finding_dedup_state", key):
                skipped += 1
                continue
            groups = memberships(snapshot, version=version)
            for member in groups:
                tx.put("finding_dedup_memberships", member.model_dump(mode="json"))
            completed = FindingDedupState(
                dedup_key=key,
                snapshot_id=snapshot.snapshot_id,
                dedup_version=version,
                membership_ids=[m.membership_id for m in groups],
                completed_at=datetime.now(UTC),
            )
            tx.put("finding_dedup_state", completed.model_dump(mode="json"))
            indexed += 1
    return {
        "dedup_version": version,
        "indexed": indexed,
        "skipped": skipped,
        "next_after": snapshots[-1]["snapshot_id"] if snapshots else None,
        "page_rows": len(snapshots),
    }
