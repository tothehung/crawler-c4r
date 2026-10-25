"""CLI script to run AI-driven finding decomposition on benchmark or custom findings.

Usage:
    py scripts/decompose_finding.py --case-id 2023-04-caviar-h-03
    py scripts/decompose_finding.py --all --output data/processed/ai_grounded_knowledge.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.knowledge_contract import SourceFindingSnapshot, snapshot_id, source_key, stable_hash
from src.services.ai_knowledge_decomposer import (
    AIKnowledgeDecomposer,
    convert_to_knowledge_revision,
)


def load_benchmark_cases():
    cases_file = ROOT / "tests/fixtures/evidence_benchmark_v1/cases.json"
    if not cases_file.exists():
        print(f"Error: Fixture file not found at {cases_file}", file=sys.stderr)
        sys.exit(1)
    return json.loads(cases_file.read_text(encoding="utf-8"))


def case_to_snapshot(case: dict) -> tuple[SourceFindingSnapshot, str]:
    finding = case["finding"]
    skey = source_key(case["source"], str(finding["id"]))
    digest = stable_hash(finding)
    snap = SourceFindingSnapshot(
        snapshot_id=snapshot_id(skey, digest),
        source_key=skey,
        source=case["source"],
        source_id=str(finding["id"]),
        source_url=case["provenance"]["source_url"],
        title=finding["title"],
        content=finding["content"],
        payload_kind="legacy_normalized_json",
        raw_payload=finding,
        raw_payload_hash=digest,
        captured_at=case.get("captured_at", "2026-09-30T00:00:00Z"),
    )
    # Collect snippet if available in targets
    snippet = ""
    for target in case.get("targets", []):
        if target.get("snippet"):
            snippet = target["snippet"]
            break
    return snap, snippet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-id",
        type=str,
        help="Specific case_id to decompose (e.g. '2023-04-caviar-h-03')",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Decompose all benchmark findings",
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "gemini", "openai", "ollama", "offline"],
        default="auto",
        help="LLM provider (default: auto)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/processed/ai_grounded_knowledge.json",
        help="Output path for decomposed knowledge JSON",
    )
    args = parser.parse_args()

    cases = load_benchmark_cases()
    decomposer = AIKnowledgeDecomposer(provider=args.provider)
    print(f"[*] Initialized AI Knowledge Decomposer (Provider: {decomposer.provider})")

    selected_cases = []
    if args.case_id:
        target = next((c for c in cases if c["case_id"] == args.case_id or args.case_id in c["case_id"]), None)
        if not target:
            print(f"Error: case_id '{args.case_id}' not found in benchmark.", file=sys.stderr)
            return 1
        selected_cases = [target]
    elif args.all:
        selected_cases = cases
    else:
        # Default: pick Caviar H-03 as standard demonstration
        target = next((c for c in cases if "caviar" in c["case_id"].lower() and "h-03" in c["case_id"].lower()), cases[0])
        selected_cases = [target]
        print(f"[*] No --case-id or --all provided. Defaulting to pilot demonstration: '{target['case_id']}'")

    results = []
    revisions = []
    for c in selected_cases:
        print(f"[*] Processing finding: {c['case_id']} - {c['finding']['title'][:60]}...")
        snap, snippet = case_to_snapshot(c)
        decomposed = decomposer.decompose(snap, code_snippet=snippet)
        rev = convert_to_knowledge_revision(snap, decomposed)
        results.append(decomposed.model_dump(mode="json"))
        revisions.append(rev.model_dump(mode="json"))

    # Print first result summary nicely
    first = results[0]
    print("\n" + "=" * 70)
    print("Result")
    print("=" * 70)
    print(f"• ID Finding              : {first['finding_id']}")
    print(f"• Vulnerability Category  : {first['vulnerability_category']}")
    print(f"• Suspicious Pattern      : {first['suspicious_pattern']['statement']}")
    print(f"• Necessary Condition     : {first['necessary_condition']['statement']}")
    print(f"• Sufficient Condition    : {first['sufficient_condition']['statement']}")
    print(f"• Trigger Condition       : {first['trigger_condition']['statement']}")
    print("• Verification Checklist  :")
    for idx, q in enumerate(first["verification_checklist"], 1):
        print(f"    {idx}. [ ] {q}")
    print(f"• Verification Method     : {first['verification_method']}")
    print(f"• Remediation             : {first['remediation']['statement']}")
    print(f"• Missing Context Signals : {', '.join(first['missing_context_signals'])}")
    print("=" * 70)

    # Save to file
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "count": len(results),
        "decomposed_findings": results,
        "knowledge_revisions": revisions,
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[+] Successfully saved {len(results)} decomposed findings to: {args.output}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
