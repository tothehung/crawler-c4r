"""Materialize selected, reviewed labels without importing the resolver under test."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "tests/fixtures/evidence_benchmark_v1"
FENCES = re.compile(r"^```([^\r\n]*)\r?\n(.*?)^```", re.MULTILINE | re.DOTALL)
URLS = re.compile(r"https?://[^\s<>\)\]]+")


def sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def url_target(url: str) -> dict:
    parts = urlsplit(url)
    result = {
        "type": "url",
        "url": url,
        "role": "unknown",
        "resolution_expectation": "not_fetched",
    }
    if parts.netloc == "gist.github.com":
        result.update(
            kind="gist",
            role="poc",
            role_basis="Report describes this Gist as the complete test file.",
        )
    elif "/commit/" in parts.path or "/pull/" in parts.path:
        result.update(
            kind="github_diff",
            role_basis="Report links a change; before/after contents have not been validated.",
        )
    else:
        result["kind"] = "github_file"
        loc = re.fullmatch(
            r"L{1,2}(\d+)(?:C\d+)?(?:-L?(\d+)(?:C\d+)?)?", parts.fragment
        )
        if loc:
            result["start_line"] = int(loc[1])
            result["end_line"] = int(loc[2] or loc[1])
        path_parts = parts.path.strip("/").split("/")
        if len(path_parts) >= 5 and path_parts[2] == "blob":
            result.update(
                repo="/".join(path_parts[:2]),
                ref=path_parts[3],
                path="/".join(path_parts[4:]),
            )
    return result


def build() -> list[dict]:
    cases = json.loads((DEST / "cases.json").read_text(encoding="utf-8"))
    plan = json.loads((DEST / "review_plan.json").read_text(encoding="utf-8"))
    annotations = []
    for case in cases:
        entries = [r for r in plan["cases"] if case["case_id"].startswith(r["match"])]
        if len(entries) != 1:
            raise ValueError(f"Exactly one review entry required: {case['case_id']}")
        review = entries[0]
        body = case["finding"]["content"]
        blocks = list(FENCES.finditer(body))
        item = {
            "case_id": case["case_id"],
            "input_sha256": sha(
                json.dumps(case["finding"], sort_keys=True, ensure_ascii=False)
            ),
            "annotation_scope": "selected_targets",
            "reviewer": plan["reviewer"],
            "status": "quarantined" if review.get("quarantine") else "report_reviewed",
            "review_note": review.get(
                "quarantine",
                review.get(
                    "note",
                    "Selected candidates and roles reviewed against report text; remote code not independently verified.",
                ),
            ),
            "expected": [],
            "forbidden": [],
        }
        if review.get("quarantine"):
            annotations.append(item)
            continue
        urls = list(dict.fromkeys(m[0].rstrip(".,;`") for m in URLS.finditer(body)))
        code_urls = [
            u
            for u in urls
            if "github.com/" in u and "/blob/" in u and ".sol" in urlsplit(u).path
        ]
        changes = [
            u for u in urls if "github.com/" in u and ("/commit/" in u or "/pull/" in u)
        ]
        selected = code_urls[:1] + changes[:1]
        for hint in review.get("extra_url_contains", []):
            found = [u for u in urls if hint in u]
            if not found:
                raise ValueError(f"Missing reviewed URL {hint} in {case['case_id']}")
            selected.append(found[0])
        for url in dict.fromkeys(selected):
            target = url_target(url)
            pos = body.find(url)
            target["report_location"] = {
                "field": "content",
                "start_offset": pos,
                "end_offset": pos + len(url),
            }
            item["expected"].append(target)
        for index, role in review["blocks"]:
            block = blocks[index]
            item["expected"].append(
                {
                    "type": "snippet",
                    "kind": (
                        "inline_diff"
                        if block[1].strip() == "diff"
                        else "inline_snippet"
                    ),
                    "block_index": index,
                    "language_label": block[1].strip(),
                    "snippet": block[2],
                    "snippet_sha256": sha(block[2].strip()),
                    "role": role,
                    "role_basis": body[max(0, block.start() - 250) : block.start()],
                    "report_location": {
                        "field": "content",
                        "start_offset": block.start(2),
                        "end_offset": block.end(2),
                    },
                }
            )
        for index in review.get("negative_blocks", []):
            item["forbidden"].append(
                {
                    "type": "snippet",
                    "snippet_sha256": sha(blocks[index][2].strip()),
                    "reason": "Console/transaction output is not Solidity source.",
                }
            )
        for field in ("source_link", "github_link"):
            url = case["finding"].get(field)
            if (
                url
                and (".md" in urlsplit(url).path or "/issues/" in urlsplit(url).path)
                and not any(n.get("url") == url for n in item["forbidden"])
            ):
                item["forbidden"].append(
                    {
                        "type": "url",
                        "url": url,
                        "reason": "Report/issue reference; not a code-file candidate. It may feed a report resolver.",
                    }
                )
        annotations.append(item)
    return annotations


if __name__ == "__main__":
    (DEST / "annotations.json").write_text(
        json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Materialized report-reviewed target labels")
