"""Collect a bounded, replayable phase-2 corpus. Never touches crawler checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from src.clients.code4rena_client import Code4renaClient, Code4renaContest

DEST = ROOT / "tests" / "fixtures" / "evidence_benchmark_v1"
REPORTS = ("2023-04-caviar", "2023-05-juicebox", "2023-01-astaria")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collect(fetch: bool) -> None:
    raw_dir = DEST / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    acquisitions = []
    local = ROOT / "data" / "findings.jsonl"
    target = raw_dir / "solodit-local.jsonl"
    if not target.exists():
        target.write_bytes(local.read_bytes())
    acquisitions.append(
        {
            "source": "solodit",
            "file": target.relative_to(DEST).as_posix(),
            "sha256": digest(target.read_bytes()),
            "origin": "data/findings.jsonl",
            "payload_kind": "legacy_normalized_json",
            "note": "Frozen local crawl output; original API response bytes unavailable.",
        }
    )
    for slug in REPORTS:
        target = raw_dir / f"{slug}.html"
        metadata = raw_dir / f"{slug}.acquisition.json"
        url = f"https://code4rena.com/reports/{slug}"
        if not target.exists():
            if not fetch:
                raise SystemExit(f"Missing {target.name}; opt in with --fetch-reports")
            with httpx.Client(follow_redirects=True, timeout=45) as client:
                response = client.get(url)
                response.raise_for_status()
            target.write_text(response.text, encoding="utf-8")
            metadata.write_text(
                json.dumps(
                    {
                        "url": url,
                        "final_url": str(response.url),
                        "status_code": response.status_code,
                        "captured_at": datetime.now(UTC).isoformat(),
                        "note": "Saved decoded HTML as UTF-8, not original wire bytes.",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        acquisitions.append(
            {
                "source": "code4rena",
                "file": target.relative_to(DEST).as_posix(),
                "sha256": digest(target.read_bytes()),
                **json.loads(metadata.read_text(encoding="utf-8")),
            }
        )
    cases = []
    seen = set()
    for line, text in enumerate(
        (raw_dir / "solodit-local.jsonl").read_text(encoding="utf-8").splitlines(), 1
    ):
        row = json.loads(text)
        finding = row.get("source_payload", row)
        if isinstance(finding, str):
            finding = json.loads(finding)
        if finding["id"] in seen:
            continue
        seen.add(finding["id"])
        cases.append(
            {
                "case_id": f"solodit-{finding['id']}",
                "source": "solodit",
                "fixture_kind": "real",
                "finding": finding,
                "provenance": {
                    "artifact": "raw/solodit-local.jsonl",
                    "line": line,
                    "source_url": finding.get("source_link"),
                    "payload_kind": "legacy_normalized_json",
                },
            }
        )
    for slug in REPORTS:
        html = (raw_dir / f"{slug}.html").read_text(encoding="utf-8")
        contest = Code4renaContest(slug=slug, title=slug)
        parsed = Code4renaClient.parse_report_findings_from_html(html, contest)
        # Fixed quotas and source order: sample can be reproduced offline.
        quota = {"2023-04-caviar": 7, "2023-05-juicebox": 3, "2023-01-astaria": 5}[slug]
        chosen = [r for r in parsed if r["impact"] in ("HIGH", "MEDIUM")][:quota]
        print(slug, "parsed", len(parsed), "selected", len(chosen))
        for row in chosen:
            cases.append(
                {
                    "case_id": row["id"],
                    "source": "code4rena",
                    "fixture_kind": "real",
                    "finding": row,
                    "provenance": {
                        "artifact": f"raw/{slug}.html",
                        "source_url": row.get("source_link"),
                        "payload_kind": "report_html",
                        "parser": "Code4renaClient.parse_report_findings_from_html",
                    },
                }
            )
    (DEST / "acquisitions.json").write_text(
        json.dumps(acquisitions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (DEST / "cases.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Saved", len(cases), "real cases")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-reports", action="store_true")
    collect(parser.parse_args().fetch_reports)
