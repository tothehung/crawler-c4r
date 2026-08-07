from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from src.models import Finding


BigQueryRow = dict[str, Any]


def finding_to_bigquery_row(
    finding: Finding,
    *,
    crawled_at: datetime | None = None,
    loaded_at: datetime | None = None,
) -> BigQueryRow:
    payload = finding.model_dump(mode="json")
    crawled_at = _utc_now_if_none(crawled_at)
    loaded_at = _utc_now_if_none(loaded_at)

    return {
        "id": finding.id,
        "kind": finding.kind,
        "auditfirm_id": finding.auditfirm_id,
        "impact": finding.impact,
        "finders_count": finding.finders_count,
        "protocol_id": finding.protocol_id,
        "title": finding.title,
        "content": finding.content,
        "summary": finding.summary,
        "report_date": finding.report_date.isoformat() if finding.report_date else None,
        "contest_prize_txt": finding.contest_prize_txt,
        "contest_link": finding.contest_link,
        "sponsor_name": finding.sponsor_name,
        "sponsor_link": finding.sponsor_link,
        "quality_score": finding.quality_score,
        "general_score": finding.general_score,
        "source_link": finding.source_link,
        "github_link": finding.github_link,
        "pdf_link": finding.pdf_link,
        "pdf_page_from": finding.pdf_page_from,
        "contest_id": finding.contest_id,
        "slug": finding.slug,
        "firm_name": finding.firm_name,
        "firm_logo_square": finding.firm_logo_square,
        "protocol_name": finding.protocol_name,
        "bookmarked": finding.bookmarked,
        "read": finding.read,
        "finder_handles": _finder_handles(finding),
        "auditfirm": payload.get("auditfirms_auditfirm"),
        "protocol": payload.get("protocols_protocol"),
        "issue_finders": payload.get("issues_issue_finders", []),
        "issue_tag_scores": payload.get("issues_issuetagscore", []),
        "source_payload": payload,
        "source_payload_hash": stable_payload_hash(payload),
        "crawled_at": _format_bigquery_timestamp(crawled_at),
        "loaded_at": _format_bigquery_timestamp(loaded_at),
    }


def findings_to_bigquery_rows(
    findings: list[Finding],
    *,
    crawled_at: datetime | None = None,
    loaded_at: datetime | None = None,
) -> list[BigQueryRow]:
    crawled_at = _utc_now_if_none(crawled_at)
    loaded_at = _utc_now_if_none(loaded_at)
    return [
        finding_to_bigquery_row(
            finding,
            crawled_at=crawled_at,
            loaded_at=loaded_at,
        )
        for finding in findings
    ]


def stable_payload_hash(payload: dict[str, Any]) -> str:
    normalized_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized_payload.encode("utf-8")).hexdigest()


def _finder_handles(finding: Finding) -> list[str]:
    handles: list[str] = []
    seen: set[str] = set()

    for issue_finder in finding.issues_issue_finders:
        if issue_finder.wardens_warden is None:
            continue

        handle = issue_finder.wardens_warden.handle
        if not handle or handle in seen:
            continue

        handles.append(handle)
        seen.add(handle)

    return handles


def _utc_now_if_none(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _format_bigquery_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")
