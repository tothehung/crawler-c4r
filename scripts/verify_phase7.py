"""Build grounded candidates on the frozen corpus; verify citations and evidence joins.

No embeddings, retrieval, model API, or automatic approval.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.knowledge_contract import stable_hash
from src.repositories.knowledge_store import SQLiteKnowledgeStore
from src.services.evidence.repo_context import _atomic_json
from src.services.knowledge_builder import build_page, claim, save_revision
from src.services.knowledge_evidence import export_knowledge
from src.services.knowledge_quality import iter_records


def overflow_draft(store):
    """Authored example grounded in the captured H-03 report; remains needs_review."""
    selected = next(
        (
            s
            for s in iter_records(store, "source_finding_snapshots")
            if "Risk of silent overflow in reserves update" in s["title"]
        ),
        None,
    )
    if selected is None:
        return None
    kid = "knw_" + stable_hash(["knowledge-source-v1", selected["source_key"]])
    head = store.read("knowledge_heads", kid)
    if not head:
        return None
    base = store.read("knowledge_revisions", head["latest_revision_id"])
    lines = selected["content"].splitlines()

    def citation(needle, *, exact=False):
        matches = [
            i
            for i, line in enumerate(lines)
            if (line.strip() == needle if exact else needle in line)
        ]
        if len(matches) != 1:
            raise ValueError(f"Example source anchor is not unique: {needle}")
        index = matches[0]
        return {
            "snapshot_id": selected["snapshot_id"],
            "start_line": index + 1,
            "end_line": index + 1,
            "quote": lines[index],
        }

    root = citation("while the values that update them are of type")
    impact = citation("If the reserves variables are updated with a silent overflow")
    fix = citation("Add checks that the casting value is not greater")
    poc = citation("Setting up pool and base token HDT with high decimals")
    code = citation(
        "virtualBaseTokenReserves += uint128(netInputAmount - feeAmount - protocolFeeAmount);",
        exact=True,
    )
    # Explicitly choose a matching code evidence, not an arbitrary link in the finding.
    for lid in base["evidence_link_ids"]:
        link = store.read("finding_evidence_links", lid)
        if link["role"] in {"fix", "poc"}:
            continue
        evidence = store.read("code_evidence", link["evidence_id"])
        if (
            "virtualBaseTokenReserves += uint128(netInputAmount - feeAmount - protocolFeeAmount);"
            in evidence["raw_snippet"]
        ):
            code = code | {"link_id": lid}
            break
    claims = [
        claim(
            "root_cause",
            "Theo báo cáo, buy/sell ép giá trị uint256 xuống uint128 để cập nhật virtual reserves mà chưa kiểm tra giá trị có nằm trong miền uint128.",
            [root],
        ),
        claim(
            "preconditions",
            "Kịch bản minh họa của báo cáo sử dụng base token có 30 decimals; đây là cấu hình PoC, không phải kết luận rằng chỉ token 30 decimals mới gặp lỗi.",
            [poc],
        ),
        claim(
            "exploit_conditions",
            "Điều kiện cần xem xét là giá trị tại phép ép kiểu vượt type(uint128).max mà không bị kiểm tra trước đó; cần xác minh khả năng đạt giá trị này trong luồng giao dịch đầy đủ.",
            [root, fix],
        ),
        claim(
            "observed_behavior",
            "Báo cáo mô tả giá trị có thể bị cắt khi ép xuống uint128 trước khi cập nhật virtualBaseTokenReserves hoặc virtualNftReserves.",
            [root],
        ),
        claim(
            "impact",
            "Virtual reserves sai có thể phá vỡ quan hệ định giá xy=k, làm giá tính toán không chính xác và gây tổn thất tiềm năng cho người dùng hoặc chủ pool.",
            [impact],
        ),
        claim(
            "detection_signals",
            "Dấu hiệu cần review là phép ép uint128(...) trong cập nhật virtual reserves, kết hợp thiếu kiểm tra miền giá trị trước phép ép. Sự xuất hiện của cast đơn thuần chưa đủ kết luận có lỗi.",
            [code, root],
        ),
        claim(
            "remediation",
            "Theo đề xuất trong báo cáo, kiểm tra giá trị không vượt type(uint128).max và revert trước khi ép kiểu; áp dụng cho cả đường buy và sell.",
            [fix],
        ),
    ]
    missing = [
        "missing_category:limitations",
        "PoC chưa được chạy lại trong phase 7.",
        "Cần reviewer xác minh điều kiện khai thác và giới hạn áp dụng từ repo đầy đủ.",
    ]
    manifest = {
        "expected_revision_id": base["revision_id"],
        "title": base["title"],
        "claims": [
            {
                "category": c.category,
                "text": c.text,
                "citations": [q.model_dump(mode="json") for q in c.citations],
            }
            for c in claims
        ],
        "missing_information": missing,
    }
    _atomic_json(ROOT / "data/processed/phase7-overflow-draft.json", manifest)
    rev, _ = save_revision(
        store,
        snapshot_id=base["snapshot_id"],
        processing_key=base["processing_key"],
        title=base["title"],
        claims=claims,
        missing_information=missing,
        extraction_version="authored-draft-v1",
        evidence_link_ids=base["evidence_link_ids"],
        expected_revision=base["revision_id"],
    )
    return rev


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path, default=ROOT / "data/checkpoints/phase4-replay.sqlite3"
    )
    args = parser.parse_args()
    store = SQLiteKnowledgeStore(args.db)
    protected = [
        "source_finding_snapshots",
        "code_evidence",
        "finding_evidence_links",
        "evidence_processing_state",
    ]
    before = {t: stable_hash(list(iter_records(store, t))) for t in protected}
    config = json.loads(
        (ROOT / "config/knowledge_phase4_recorded.json").read_text(encoding="utf-8")
    )
    scope = {
        "pipeline_version": "evidence-resolver-v1",
        "config_hash": stable_hash(config),
    }
    pages = []
    after = ""
    while True:
        page = build_page(store, **scope, after=after, limit=10)
        pages.append(page)
        if any(r["action"] == "error" for r in page["results"]):
            raise ValueError(page)
        if page["page_rows"] < 10:
            break
        after = page["next_after"]
    rerun = build_page(store, **scope, limit=1000)
    assert all(r["action"] == "skipped" for r in rerun["results"])
    example = overflow_draft(store)
    exported = export_knowledge(store, include_candidates=True)
    _atomic_json(ROOT / "data/processed/phase7-knowledge.json", exported)
    if example:
        labels = {
            "root_cause": "Nguyên nhân gốc",
            "preconditions": "Điều kiện ban đầu",
            "exploit_conditions": "Điều kiện khai thác cần kiểm chứng",
            "observed_behavior": "Hành vi lỗi",
            "impact": "Tác động",
            "detection_signals": "Dấu hiệu trên code",
            "remediation": "Cách sửa",
        }
        view = [
            "# Ví dụ knowledge cho finding/evidence",
            "",
            example.title,
            "",
            "**Trạng thái: needs_review — chưa duyệt, chưa chạy lại PoC.**",
            "",
            f"Revision: `{example.revision_id}`",
            "",
        ]
        for item in example.claims:
            view.extend(
                ["## " + labels.get(item.category, item.category), "", item.text, ""]
            )
            for cite in item.citations:
                view.append(
                    f"- Căn cứ: report snapshot `{cite.snapshot_id}`, dòng {cite.start_line}–{cite.end_line}."
                    + (f" Evidence link: `{cite.link_id}`." if cite.link_id else "")
                )
            view.append("")
        view.extend(
            [
                "## Còn thiếu / cần kiểm tra",
                "",
                *["- " + s for s in example.missing_information],
                "",
                "Quote nguyên văn và liên kết evidence đầy đủ nằm trong phase7-overflow-draft.json và phase7-knowledge.json.",
                "",
            ]
        )
        (ROOT / "data/processed/phase7-example.md").write_text(
            "\n".join(view), encoding="utf-8"
        )
    assert before == {t: stable_hash(list(iter_records(store, t))) for t in protected}
    approved = export_knowledge(store)
    categories = Counter(
        c["category"]
        for r in exported["records"]
        for items in r["knowledge"].values()
        for c in items
    )
    report = {
        "scope": "structured knowledge for finding/evidence only; no embedding/retrieval",
        "build_actions": dict(
            Counter(r["action"] for p in pages for r in p["results"])
        ),
        "rerun_actions": dict(Counter(r["action"] for r in rerun["results"])),
        "latest_knowledge": len(exported["records"]),
        "with_evidence": sum(bool(r["finding_evidence"]) for r in exported["records"]),
        "approved": len(approved["records"]),
        "review_status": dict(Counter(r["review_status"] for r in exported["records"])),
        "claims_by_category": dict(categories),
        "claim_count": sum(categories.values()),
        "all_citations_checked": True,
        "source_and_evidence_unchanged": True,
        "example_revision_id": example.revision_id if example else None,
        "limitations": [
            "Exact quote/line validation proves provenance, not semantic correctness.",
            "Extractive drafts classify paragraphs by report headings; missing fields remain explicit.",
            "Authored example is a draft and does not approve the finding or reproduce its PoC.",
        ],
    }
    _atomic_json(ROOT / "data/processed/phase7-verification.json", report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
