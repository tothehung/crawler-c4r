"""Offline baseline for selected candidate targets. Does not claim full precision."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from src.models import Finding
from src.services.evidence.discovery import discover
from src.services.evidence.github_fetcher import GitHubFetcher, GitHubFetchError

FIXTURES = ROOT / "tests/fixtures/evidence_benchmark_v1"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def snippet_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()


def matches(target: dict, observed: dict) -> bool:
    if target["type"] == "snippet":
        return target["snippet_sha256"] == observed.get("snippet_sha256")
    if not observed.get("url"):
        return False
    # URL identity preserves query strings; anchor is assessed as a separate range.
    expected_url = urlsplit(target["url"])._replace(fragment="").geturl()
    actual_url = urlsplit(observed["url"])._replace(fragment="").geturl()
    if expected_url != actual_url:
        return False
    return "start_line" not in target or (
        target["start_line"] == observed.get("start_line")
        and target["end_line"] == observed.get("end_line")
    )


def observe(finding: dict) -> list[dict]:
    finding = Finding.model_validate(finding)
    candidates = discover(
        "\n".join(p for p in (finding.summary, finding.content) if p),
        metadata_urls=[finding.github_link, finding.source_link],
    )
    return [
        {
            "kind": c.kind,
            "url": c.url or None,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "snippet_sha256": snippet_hash(c.snippet) if c.snippet else None,
        }
        for c in candidates
    ]


def score(cases: list[dict], annotations: list[dict], observations: dict) -> dict:
    rows = []
    categories = {}
    source_totals = {}
    for case, annotation in zip(cases, annotations, strict=True):
        if case["case_id"] != annotation["case_id"]:
            raise ValueError("Annotations must align with frozen cases")
        if annotation["status"] == "quarantined":
            continue
        actual = observations[case["case_id"]]
        hits = []
        for i, target in enumerate(annotation["expected"]):
            hit = any(matches(target, c) for c in actual)
            hits.append(hit)
            count = categories.setdefault(target["kind"], {"targets": 0, "matched": 0})
            count["targets"] += 1
            count["matched"] += int(hit)
        negatives = [
            i
            for i, target in enumerate(annotation["forbidden"])
            if any(matches(target, c) for c in actual)
        ]
        counts = source_totals.setdefault(case["source"], {"targets": 0, "matched": 0})
        counts["targets"] += len(hits)
        counts["matched"] += sum(hits)
        rows.append(
            {
                "case_id": case["case_id"],
                "target_count": len(hits),
                "matched_count": sum(hits),
                "missing_target_indexes": [i for i, hit in enumerate(hits) if not hit],
                "forbidden_match_indexes": negatives,
                "observed_count": len(actual),
            }
        )
    total = sum(r["target_count"] for r in rows)
    matched = sum(r["matched_count"] for r in rows)
    return {
        "metric": "selected_target_recall",
        "targets": total,
        "matched": matched,
        "recall": matched / total if total else None,
        "forbidden_matches": sum(len(r["forbidden_match_indexes"]) for r in rows),
        "forbidden_targets": sum(
            len(a["forbidden"]) for a in annotations if a["status"] != "quarantined"
        ),
        "by_kind": categories,
        "by_source": source_totals,
        "cases": rows,
        "not_scored": [
            "global precision",
            "remote-resolution success rate",
            "role accuracy",
            "Solidity parse accuracy",
            "cross-source dedup accuracy",
        ],
    }


def replay_client() -> httpx.Client:
    index = {r["url"]: r for r in load("http/index.json")}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url not in index:
            raise AssertionError(f"Unrecorded request: {url}")
        row = index[url]
        body = (FIXTURES / "http" / row["body_file"]).read_bytes()
        return httpx.Response(
            row["status_code"], content=body, headers=row["headers"], request=request
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def transport_probe() -> list[dict]:
    results = []
    probes = [
        ("code-423n4/2023-04-caviar", "main"),
        ("code-423n4/2023-01-astaria", "1bfc58b42109b839528ab1c21dc9803d663df898"),
    ]
    with replay_client() as client:
        fetcher = GitHubFetcher(http_client=client)
        for repo, ref in probes:
            try:
                sha = fetcher.resolve_ref_sha(repo, ref)
                results.append(
                    {"repo": repo, "ref": ref, "status": "resolved", "sha": sha}
                )
            except (TypeError, ValueError, GitHubFetchError, httpx.HTTPError) as exc:
                results.append(
                    {
                        "repo": repo,
                        "ref": ref,
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
    return results


def baseline() -> dict:
    cases, annotations = load("cases.json"), load("annotations.json")
    excluded = {a["case_id"] for a in annotations if a["status"] == "quarantined"}
    observations = {
        c["case_id"]: observe(c["finding"])
        for c in cases
        if c["case_id"] not in excluded
    }
    files = [ROOT / "src/models/finding.py", ROOT / "src/models/evidence.py"] + sorted(
        (ROOT / "src/services/evidence").glob("*.py")
    )
    return {
        "benchmark_version": "1.0",
        "mode": "offline",
        "annotation_status": "assistant-report-reviewed; auditor review pending",
        "real_case_count": len(cases),
        "source_counts": dict(Counter(c["source"] for c in cases)),
        "quarantined": [
            a["case_id"] for a in annotations if a["status"] == "quarantined"
        ],
        "input_hashes": {
            name: hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
            for name in (
                "cases.json",
                "annotations.json",
                "review_plan.json",
                "controls.json",
                "http/index.json",
            )
        },
        "implementation_hashes": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        },
        "candidate_metrics": score(cases, annotations, observations),
        "http_transport_probe": transport_probe(),
        "observations": observations,
        "synthetic_candidate_controls": [
            {
                "case_id": c["case_id"],
                "expected": c["expected_candidate_count"],
                "observed": len(observe(c["finding"])),
            }
            for c in load("controls.json")["findings"]
        ],
    }


def markdown(report: dict) -> str:
    metrics = report["candidate_metrics"]
    lines = [
        "# Evidence benchmark v1 — baseline",
        "",
        "Offline, selected report-reviewed targets; not a security accuracy score.",
        "",
        f"Real findings: {report['real_case_count']}; quarantined: {len(report['quarantined'])}.",
        f"Selected target recall: {metrics['matched']}/{metrics['targets']} ({metrics['recall']:.1%}).",
        f"Forbidden matches: {metrics['forbidden_matches']}/{metrics['forbidden_targets']}.",
        "",
        "| Candidate kind | Matched | Targets |",
        "|---|---:|---:|",
    ]
    for kind, counts in metrics["by_kind"].items():
        lines.append(f"| {kind} | {counts['matched']} | {counts['targets']} |")
    lines += ["", "## Transport probes (recorded HTTP)", ""]
    for probe in report["http_transport_probe"]:
        lines.append(
            f"- `{probe['repo']}`: {probe['status']} — {probe.get('message', probe.get('sha', ''))}"
        )
    lines += [
        "",
        "## Scope",
        "",
        "Unlabelled candidates are unscored; do not interpret selected-target recall as global precision/recall. Roles are annotated for future checks, not predicted by the current scanner. Real duplicate pairs and entirely no-code findings remain corpus gaps; synthetic controls are reported separately.",
        "",
        "See baseline.json for missing target indexes, forbidden matches, per-source counts, observations and implementation hashes.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=FIXTURES / "baseline.json")
    args = parser.parse_args()
    report = baseline()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                k: report["candidate_metrics"][k]
                for k in ("targets", "matched", "recall", "forbidden_matches")
            }
        )
    )
