"""Join latest structured knowledge to finding/evidence links without embeddings."""

from __future__ import annotations

from src.models.knowledge_base import KnowledgeRevision
from src.services.knowledge_builder import REQUIRED, validate_grounding
from src.services.knowledge_quality import iter_records


def export_knowledge(
    store, *, include_candidates=False, link_id=None, max_rows=100_000
):
    records = []
    for head in iter_records(store, "knowledge_heads", max_rows=max_rows):
        with store.transaction() as tx:
            head = tx.get("knowledge_heads", head["knowledge_id"])
            row = tx.get("knowledge_revisions", head["latest_revision_id"])
            rev = KnowledgeRevision.model_validate(row)
            if rev.review_status == "rejected" or (
                rev.review_status != "approved" and not include_candidates
            ):
                continue
            if link_id and link_id not in rev.evidence_link_ids:
                continue
            snap = validate_grounding(
                tx,
                rev.snapshot_id,
                rev.processing_key,
                rev.claims,
                rev.evidence_link_ids,
                rev.evidence_bindings,
            )
            fields = {name: [] for name in sorted(REQUIRED)}
            for c in rev.claims:
                fields[c.category].append(c.model_dump(mode="json"))
            evidence = []
            for lid in rev.evidence_link_ids:
                if link_id and lid != link_id:
                    continue
                link = tx.get("finding_evidence_links", lid)
                code = (
                    tx.get("code_evidence", link["evidence_id"])
                    if link["evidence_id"]
                    else None
                )
                evidence.append(
                    {
                        "link_id": lid,
                        "role": link["role"],
                        "role_basis": link["role_basis"],
                        "evidence_id": link["evidence_id"],
                        "resolution_status": link["resolution_status"],
                        "syntax_status": code["syntax_status"] if code else None,
                        "provenance": (
                            {
                                key: code[key]
                                for key in (
                                    "origin_kind",
                                    "origin_url",
                                    "repo",
                                    "commit_sha",
                                    "path",
                                    "source_range",
                                )
                            }
                            if code
                            else None
                        ),
                        "direct_claim_ids": [
                            c.claim_id
                            for c in rev.claims
                            if any(cite.link_id == lid for cite in c.citations)
                        ],
                    }
                )
            records.append(
                {
                    "knowledge_id": rev.knowledge_id,
                    "revision_id": rev.revision_id,
                    "version": rev.version,
                    "title": rev.title,
                    "review_status": rev.review_status,
                    "review_sequence": rev.review_sequence,
                    "snapshot_id": rev.snapshot_id,
                    "source": snap["source"],
                    "source_id": snap["source_id"],
                    "source_url": snap["source_url"],
                    "knowledge": fields,
                    "missing_information": rev.missing_information,
                    "finding_evidence": evidence,
                    "support_scope": "Claims cite the report; only direct_claim_ids explicitly cite an evidence link. Related code is not automatically proof of every claim.",
                }
            )
    return {
        "schema_version": "1.0",
        "include_candidates": include_candidates,
        "records": records,
    }
