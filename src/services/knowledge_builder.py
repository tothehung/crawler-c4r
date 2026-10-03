"""Extractive candidates, exact source citations, immutable revisions and review."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from markdown_it import MarkdownIt

from src.models.knowledge_base import (
    GroundedCitation,
    GroundedClaim,
    KnowledgeBuild,
    KnowledgeHead,
    KnowledgeReviewEvent,
    KnowledgeRevision,
)
from src.models.knowledge_contract import stable_hash

EXTRACTION_VERSION = "report-extractive-v1"
REQUIRED = {
    "root_cause",
    "preconditions",
    "exploit_conditions",
    "observed_behavior",
    "impact",
    "detection_signals",
    "remediation",
    "limitations",
}
HEADINGS = [
    (r"root cause|underlying cause", "root_cause"),
    (r"preconditions?|prerequisites?", "preconditions"),
    (r"exploit conditions?|attack conditions?", "exploit_conditions"),
    (r"impact|consequences?", "impact"),
    (r"recommend|mitigation|remediat|fix(?:es)?\b", "remediation"),
    (r"detection|code signals?", "detection_signals"),
    (r"limitations?|false positives?|scope constraints?", "limitations"),
]


def claim(category, text, citations):
    citations = [GroundedCitation.model_validate(c) for c in citations]
    return GroundedClaim(
        claim_id="clm_"
        + stable_hash([category, text, [c.model_dump(mode="json") for c in citations]]),
        category=category,
        text=text,
        citations=citations,
    )


def extract_claims(snapshot, *, max_claims=80):
    lines = snapshot["content"].splitlines()
    tokens = MarkdownIt("commonmark", {"html": False}).parse(snapshot["content"])
    category = "observed_behavior"
    claims = []
    seen = set()
    truncated = False
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            heading = tokens[index + 1].content.casefold()
            category = next(
                (name for pattern, name in HEADINGS if re.search(pattern, heading)),
                "observed_behavior",
            )
        if token.type != "paragraph_open" or not token.map:
            continue
        start, end = token.map
        quote = "\n".join(lines[start:end])
        if not quote.strip() or (start, end) in seen:
            continue
        plain = tokens[index + 1].content if index + 1 < len(tokens) else quote
        if (
            plain.startswith("Submitted by ")
            or re.fullmatch(r"\s*\[?https?://.*", plain)
            or re.fullmatch(r"\s*\[[^\]]+\]\([^\)]+\):?\s*", plain)
        ):
            continue
        seen.add((start, end))
        if len(claims) >= max_claims:
            truncated = True
            break
        claims.append(
            claim(
                category,
                quote,
                [
                    {
                        "snapshot_id": snapshot["snapshot_id"],
                        "start_line": start + 1,
                        "end_line": end,
                        "quote": quote,
                    }
                ],
            )
        )
    missing = [
        "missing_category:" + name
        for name in sorted(REQUIRED - {c.category for c in claims})
    ]
    # Headings locate excerpts; they do not establish semantic correctness.
    missing.append(
        "semantic_review_required: extracted report statements are not independently verified"
    )
    if truncated:
        missing.append("extraction_limit_reached")
    return claims, missing


def validate_grounding(
    tx, snapshot_id, processing_key, claims, evidence_link_ids, evidence_bindings=None
):
    snapshot = tx.get("source_finding_snapshots", snapshot_id)
    state = tx.get("evidence_processing_state", processing_key)
    if not snapshot or not state or state["snapshot_id"] != snapshot_id:
        raise ValueError("knowledge input snapshot/processing state mismatch")
    links = {r["link_id"]: r for r in tx.links(processing_key)}
    if set(evidence_link_ids) - links.keys():
        raise ValueError("knowledge references unrelated evidence links")
    for lid in evidence_link_ids:
        if links[lid]["snapshot_id"] != snapshot_id:
            raise ValueError("evidence link belongs to another source snapshot")
        eid = links[lid]["evidence_id"]
        if not eid or not tx.get("code_evidence", eid):
            raise ValueError("related link has no persisted evidence")
        if evidence_bindings is not None and evidence_bindings.get(lid) != eid:
            raise ValueError(
                "evidence binding changed; rebuild knowledge before review/export"
            )
    for item in claims:
        for cite in item.citations:
            if cite.snapshot_id != snapshot_id:
                raise ValueError("citation belongs to another snapshot")
            lines = snapshot["content"].splitlines()
            if (
                cite.end_line > len(lines)
                or "\n".join(lines[cite.start_line - 1 : cite.end_line]) != cite.quote
            ):
                raise ValueError("citation quote/range does not match immutable report")
            if cite.link_id:
                link = links.get(cite.link_id)
                if (
                    cite.link_id not in evidence_link_ids
                    or not link
                    or not link["evidence_id"]
                    or not tx.get("code_evidence", link["evidence_id"])
                ):
                    raise ValueError("citation link has no persisted evidence")
    return snapshot


def save_revision(
    store,
    *,
    snapshot_id,
    processing_key,
    title,
    claims,
    missing_information,
    extraction_version,
    evidence_link_ids,
    expected_revision=None,
):
    claims = [
        GroundedClaim.model_validate(
            c.model_dump() if isinstance(c, GroundedClaim) else c
        )
        for c in claims
    ]
    if len({c.claim_id for c in claims}) != len(claims):
        raise ValueError("duplicate claim identity")
    missing_information = sorted(
        set(missing_information)
        | {"missing_category:" + key for key in REQUIRED - {c.category for c in claims}}
    )
    with store.transaction() as tx:
        snapshot = validate_grounding(
            tx, snapshot_id, processing_key, claims, evidence_link_ids
        )
        bindings = {
            r["link_id"]: r["evidence_id"]
            for r in tx.links(processing_key)
            if r["link_id"] in evidence_link_ids
        }
        input_fingerprint = stable_hash(
            [
                snapshot_id,
                processing_key,
                title,
                [c.model_dump(mode="json") for c in claims],
                bindings,
                sorted(set(missing_information)),
                extraction_version,
            ]
        )
        build_id = "kbl_" + input_fingerprint
        knowledge_id = "knw_" + stable_hash(
            ["knowledge-source-v1", snapshot["source_key"]]
        )
        existing = tx.get("knowledge_builds", build_id)
        if existing:
            return (
                KnowledgeRevision.model_validate(
                    tx.get("knowledge_revisions", existing["revision_id"])
                ),
                False,
            )
        head = tx.get("knowledge_heads", knowledge_id)
        if expected_revision is not None and (
            not head or head["latest_revision_id"] != expected_revision
        ):
            raise ValueError("knowledge head changed; reload before revising")
        # A later snapshot must not be silently replaced by an older observation.
        if head:
            previous = tx.get("knowledge_revisions", head["latest_revision_id"])
            old_snapshot = tx.get("source_finding_snapshots", previous["snapshot_id"])
            if old_snapshot["snapshot_id"] != snapshot_id and datetime.fromisoformat(
                old_snapshot["captured_at"].replace("Z", "+00:00")
            ) >= datetime.fromisoformat(snapshot["captured_at"].replace("Z", "+00:00")):
                raise ValueError(
                    "older or ambiguous snapshot cannot replace latest knowledge"
                )
        data = {
            "knowledge_id": knowledge_id,
            "version": head["latest_version"] + 1 if head else 1,
            "snapshot_id": snapshot_id,
            "processing_key": processing_key,
            "title": title,
            "claims": [c.model_dump(mode="json") for c in claims],
            "evidence_link_ids": sorted(set(evidence_link_ids)),
            "evidence_bindings": bindings,
            "missing_information": sorted(set(missing_information)),
            "extraction_version": extraction_version,
            "input_fingerprint": input_fingerprint,
        }
        digest = stable_hash(data)
        rev = KnowledgeRevision(
            **data,
            content_hash=digest,
            revision_id="krv_" + stable_hash([knowledge_id, data["version"], digest]),
            created_at=datetime.now(UTC),
        )
        tx.put("knowledge_revisions", rev.model_dump(mode="json"))
        tx.put(
            "knowledge_heads",
            KnowledgeHead(
                knowledge_id=knowledge_id,
                latest_revision_id=rev.revision_id,
                latest_version=rev.version,
            ).model_dump(mode="json"),
        )
        tx.put(
            "knowledge_builds",
            KnowledgeBuild(
                build_id=build_id,
                revision_id=rev.revision_id,
                input_fingerprint=input_fingerprint,
            ).model_dump(mode="json"),
        )
    return rev, True


def build_page(store, *, pipeline_version, config_hash, after="", limit=100):
    rows = store.states(after=after, limit=limit)
    results = []
    for state in rows:
        if (
            state["pipeline_version"] != pipeline_version
            or state["config_hash"] != config_hash
        ):
            continue
        if not state["outputs_persisted_at"]:
            results.append(
                {
                    "processing_key": state["processing_key"],
                    "action": "waiting_for_evidence_inventory",
                }
            )
            continue
        snap = store.read("source_finding_snapshots", state["snapshot_id"])
        claims, missing = extract_claims(snap)
        links = [
            r["link_id"]
            for r in store.links(state["processing_key"])
            if r["evidence_id"]
        ]
        try:
            rev, created = save_revision(
                store,
                snapshot_id=snap["snapshot_id"],
                processing_key=state["processing_key"],
                title=snap["title"],
                claims=claims,
                missing_information=missing,
                extraction_version=EXTRACTION_VERSION,
                evidence_link_ids=links,
            )
            results.append(
                {
                    "processing_key": state["processing_key"],
                    "revision_id": rev.revision_id,
                    "action": "created" if created else "skipped",
                }
            )
        except ValueError as exc:
            results.append(
                {
                    "processing_key": state["processing_key"],
                    "action": "error",
                    "error": str(exc),
                }
            )
    return {
        "next_after": rows[-1]["processing_key"] if rows else None,
        "page_rows": len(rows),
        "results": results,
    }


def review_revision(store, revision_id, *, status, reviewer, note, expected_sequence):
    if not reviewer.strip() or not note.strip():
        raise ValueError("reviewer and rationale required")
    with store.transaction() as tx:
        row = tx.get("knowledge_revisions", revision_id)
        if not row:
            raise KeyError(revision_id)
        head = tx.get("knowledge_heads", row["knowledge_id"])
        if (
            head["latest_revision_id"] != revision_id
            or row["review_sequence"] != expected_sequence
        ):
            raise ValueError("stale review; reload latest revision/sequence")
        rev = KnowledgeRevision.model_validate(row)
        validate_grounding(
            tx,
            rev.snapshot_id,
            rev.processing_key,
            rev.claims,
            rev.evidence_link_ids,
            rev.evidence_bindings,
        )
        if status == "approved" and REQUIRED - {c.category for c in rev.claims}:
            raise ValueError(
                "approval requires all knowledge categories; unsupported categories need a cited limitation"
            )
        now = datetime.now(UTC)
        updated = KnowledgeRevision.model_validate(
            row
            | {
                "review_status": status,
                "review_sequence": expected_sequence + 1,
                "reviewed_by": reviewer,
                "review_note": note,
                "reviewed_at": now,
            }
        )
        event = KnowledgeReviewEvent(
            event_id="kre_" + stable_hash([revision_id, updated.review_sequence]),
            revision_id=revision_id,
            sequence=updated.review_sequence,
            previous_status=rev.review_status,
            status=status,
            reviewer=reviewer,
            note=note,
            reviewed_at=now,
        )
        tx.put("knowledge_review_events", event.model_dump(mode="json"))
        tx.put("knowledge_revisions", updated.model_dump(mode="json"))
    return updated
