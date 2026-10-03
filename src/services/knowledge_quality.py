"""Scoped quality reporting. Rates always include their numerator/denominator."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime

from src.repositories.knowledge_store import KEYS
from src.services.finding_dedup import DEDUP_VERSION


def iter_records(store, table: str, *, max_rows: int = 100_000):
    after = ""
    count = 0
    while True:
        rows = store.scan(table, after=after, limit=1000)
        for row in rows:
            count += 1
            if count > max_rows:
                raise ValueError(
                    f"Report limit exceeded for {table}; increase --max-rows (no truncated report emitted)"
                )
            yield row
        if len(rows) < 1000:
            break
        after = rows[-1][KEYS[table]]


def rate(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def quality_report(
    store,
    *,
    pipeline_version: str,
    config_hash: str,
    dedup_version: str = DEDUP_VERSION,
    max_rows: int = 100_000,
) -> dict:
    states = {
        r["processing_key"]: r
        for r in iter_records(store, "evidence_processing_state", max_rows=max_rows)
        if r["pipeline_version"] == pipeline_version and r["config_hash"] == config_hash
    }
    now = datetime.now(UTC)
    snapshots = {}
    buckets = defaultdict(
        lambda: {
            "states": [],
            "snapshots": set(),
            "source_keys": set(),
            "with_evidence": set(),
            "links": [],
            "evidence": {},
        }
    )
    evidence = {}
    uses = defaultdict(set)
    for state in states.values():
        snap = store.read("source_finding_snapshots", state["snapshot_id"])
        if snap is None:
            raise ValueError("State references missing snapshot")
        snapshots[snap["snapshot_id"]] = snap
        bucket = buckets[snap["source"]]
        bucket["states"].append(state)
        bucket["snapshots"].add(snap["snapshot_id"])
        bucket["source_keys"].add(snap["source_key"])
        for link in store.links(state["processing_key"]):
            bucket["links"].append(link)
            eid = link["evidence_id"]
            if eid:
                if eid not in evidence:
                    evidence[eid] = store.read("code_evidence", eid)
                if evidence[eid] is None:
                    raise ValueError("Link references missing evidence")
                bucket["evidence"][eid] = evidence[eid]
                bucket["with_evidence"].add(snap["source_key"])
                uses[eid].add(snap["source_key"])
    by_source = {}
    for source, bucket in sorted(buckets.items()):
        links, ev = bucket["links"], bucket["evidence"]
        checked = [r for r in ev.values() if r["syntax_status"] != "not_checked"]
        links_with_evidence = [r for r in links if r["evidence_id"]]
        by_source[source] = {
            "source_findings": len(bucket["source_keys"]),
            "snapshots": len(bucket["snapshots"]),
            "states": dict(Counter(r["status"] for r in bucket["states"])),
            "findings_with_evidence": rate(
                len(bucket["with_evidence"]), len(bucket["source_keys"])
            ),
            "resolution": dict(Counter(r["resolution_status"] for r in links)),
            "resolve_success": rate(
                sum(r["resolution_status"] == "resolved" for r in links), len(links)
            ),
            "syntax_status": dict(Counter(r["syntax_status"] for r in ev.values())),
            "parse_coverage": rate(len(checked), len(ev)),
            "parse_success_checked": rate(
                sum(r["syntax_status"] == "parsed" for r in checked), len(checked)
            ),
            "roles": dict(Counter(r["role"] for r in links_with_evidence)),
            "role_coverage": rate(
                sum(r["role"] != "unknown" for r in links_with_evidence),
                len(links_with_evidence),
            ),
            "link_errors": dict(
                Counter(r["error_code"] for r in links if r["error_code"])
            ),
        }
    # Group membership is a link, never a destructive rewrite of raw snapshots.
    groups = defaultdict(list)
    for row in iter_records(store, "finding_dedup_memberships", max_rows=max_rows):
        if row["dedup_version"] == dedup_version and row["snapshot_id"] in snapshots:
            groups[row["group_id"]].append(row)
    parents = {r["source_key"]: r["source_key"] for r in snapshots.values()}

    def find(key):
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    confirmed = []
    candidates = []
    for gid, members in sorted(groups.items()):
        ids = sorted({r["source_key"] for r in members})
        if len(ids) < 2:
            continue
        item = {
            "group_id": gid,
            "method": members[0]["method"],
            "source_keys": ids,
            "snapshot_ids": sorted(r["snapshot_id"] for r in members),
            "sources": sorted({r["source"] for r in members}),
        }
        if members[0]["decision"] == "confirmed":
            confirmed.append(item)
            for key in ids[1:]:
                a, b = sorted((find(ids[0]), find(key)))
                parents[b] = a
        else:
            candidates.append(item)
    candidates = [g for g in candidates if len({find(k) for k in g["source_keys"]}) > 1]
    components = defaultdict(list)
    for key in sorted(parents):
        components[find(key)].append(key)
    completed_dedup = {
        r["snapshot_id"]
        for r in iter_records(store, "finding_dedup_state", max_rows=max_rows)
        if r["dedup_version"] == dedup_version and r["snapshot_id"] in snapshots
    }
    attempts = [
        r
        for r in iter_records(store, "knowledge_processing_attempts", max_rows=max_rows)
        if r["processing_key"] in states
    ]
    times = sorted(r["resolver_seconds"] for r in attempts)
    retryable = [
        r
        for r in states.values()
        if r["retryable"] and r["attempts"] < r["max_attempts"]
    ]
    due = [
        r
        for r in retryable
        if r["next_retry_at"] is None
        or datetime.fromisoformat(r["next_retry_at"].replace("Z", "+00:00")) <= now
    ]
    links_count = sum(len(b["links"]) for b in buckets.values())
    evidence_link_count = sum(
        sum(bool(r["evidence_id"]) for r in b["links"]) for b in buckets.values()
    )
    return {
        "schema_version": "1.0",
        "pipeline_version": pipeline_version,
        "config_hash": config_hash,
        "dedup_version": dedup_version,
        "by_source": by_source,
        "totals": {
            "source_findings": len(parents),
            "snapshots": len(snapshots),
            "processing_states": len(states),
            "links": links_count,
            "unique_evidence": len(evidence),
            "evidence_links": evidence_link_count,
            "reused_evidence_links": evidence_link_count - len(evidence),
            "evidence_shared_between_findings": sum(len(s) > 1 for s in uses.values()),
            "states": dict(Counter(r["status"] for r in states.values())),
        },
        "finding_dedup": {
            "index_coverage": rate(len(completed_dedup), len(snapshots)),
            "confirmed_groups": confirmed,
            "review_candidates": candidates,
            "confirmed_components": [v for v in components.values() if len(v) > 1],
            "source_findings_linked": sum(len(v) - 1 for v in components.values()),
            "cross_source_groups": sum(len(g["sources"]) > 1 for g in confirmed),
        },
        "operations": {
            "attempts": sum(r["attempts"] for r in states.values()),
            "retry_attempts": sum(max(0, r["attempts"] - 1) for r in states.values()),
            "retry_due": len(due),
            "retry_waiting": len(retryable) - len(due),
            "attempts_exhausted": sum(
                r["status"] != "succeeded" and r["attempts"] >= r["max_attempts"]
                for r in states.values()
            ),
            "state_errors": dict(
                Counter(r["error_code"] for r in states.values() if r["error_code"])
            ),
            "timed_attempts": len(times),
            "untimed_attempts": sum(r["attempts"] for r in states.values())
            - len(times),
            "resolver_seconds_total": sum(times),
            "resolver_seconds_mean": sum(times) / len(times) if times else None,
            "resolver_seconds_max": max(times) if times else None,
        },
        "limitations": [
            "Scoped to one pipeline/config; snapshot revisions are counted separately from native source findings.",
            "Parse/role coverage is not vulnerability or role accuracy; parser annotations are the latest stored values.",
            "Resolver time excludes storage; old/interrupted attempts without a committed metric remain untimed.",
            "Read while workers are paused for a consistent report; multi-page reports are not database snapshots.",
            "Exact normalized content/title creates review candidates only; no embedding/fuzzy semantic matcher.",
        ],
    }
