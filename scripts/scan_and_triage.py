"""W3GoAudit End-to-End AI-Assisted Audit Runner.

Orchestrates the complete pipeline:
  1. Go Engine (w3goaudit.exe): Fast static scan -> WQL findings + AST analysis
  2. AST Context Bundle (extract bundle): Exact callers, callees, state, inheritance
  3. Knowledge Base: 8-facet verification checklist
  4. Local AI LLM (Ollama Qwen2.5-Coder-7B on RTX 3050): Two-pass Auditor + Critic Triage
  5. Final Audit Report: Confirmed vulnerabilities + filtered false positives

Usage:
  python scripts/scan_and_triage.py --target ../w3goaudit-main/test-data/security/unrestricted-transferownership.sol
  python scripts/scan_and_triage.py --target ../w3goaudit-main/test-data/security/unchecked-arithmetic.sol
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from services.engine_bridge import W3GoAuditEngineBridge
from scripts.run_pilot_triage import (
    CHECKLISTS_BY_PATTERN,
    call_llm_api,
    ensure_ollama_running,
    triage_baseline_4_knowledge_grounded,
    triage_baseline_5_auditor_critic,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("w3goaudit.full_scan")


def map_template_to_pattern(template_id: str) -> str:
    """Map w3goaudit template IDs to W3GoAudit Knowledge Patterns."""
    tid = template_id.upper()
    if "TRANSFEROWNERSHIP" in tid or "ACCESS" in tid or "OWNER" in tid or "INITIALIZER" in tid:
        return "SOL-ACCESS-CONTROL-001"
    if "ARITHMETIC" in tid or "NARROWING" in tid or "CAST" in tid or "OVERFLOW" in tid:
        return "SOL-UINT128-NARROWING-001"
    if "REENTRANCY" in tid:
        return "SOL-REENTRANCY-001"
    return "SOL-GENERIC-001"


def run_full_pipeline(
    target_path: Path,
    output_dir: Path,
    provider: str = "ollama",
    model: str = "qwen2.5-coder:7b",
    skip_ai: bool = False,
) -> Dict[str, Any]:
    bridge = W3GoAuditEngineBridge()
    if not bridge.is_available():
        logger.error("w3goaudit.exe binary not found at %s. Please run 'go build ./cmd/w3goaudit' first.", bridge.executable)
        sys.exit(1)

    print("=" * 80)
    print(f" W3GoAudit — End-to-End Hybrid Static & AI Audit Pipeline")
    print(f" Target: {target_path}")
    print(f" Static Engine: {bridge.executable}")
    print(f" AI Provider: {provider.upper()} | Model: {model}")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # STAGE 1: Go Static Analysis Scan
    # -------------------------------------------------------------------------
    start_time = time.time()
    logger.info("[Stage 1] Running w3goaudit static scan...")
    scan_result = bridge.run_scan(target_path, output_dir=output_dir)
    scan_duration = time.time() - start_time

    findings = scan_result.get("findings", [])
    auth_facts = scan_result.get("authorization_facts", {})
    logger.info("[Stage 1 Completed] Scan finished in %.2fs. Found %d raw findings.", scan_duration, len(findings))

    if not findings:
        print("\n[OK] No findings reported by static scanner. Project clean.")
        return {"status": "clean", "findings": []}

    print(f"\nRaw Static Findings: {len(findings)}")
    for idx, f in enumerate(findings, 1):
        loc = f.get("location", {})
        print(f"  {idx}. [{f.get('severity')}] {f.get('title')} — {loc.get('contract', '')}.{loc.get('function', '')}() (Line {loc.get('line', '?')})")

    # -------------------------------------------------------------------------
    # STAGE 2 & 3: Context Extraction + AI Triage
    # -------------------------------------------------------------------------
    if not skip_ai and provider == "ollama":
        ensure_ollama_running()

    triaged_findings = []
    print("\n" + "-" * 80)
    print(" [Stage 2 & 3] AST Context Enrichment & Two-Pass AI Triage")
    print("-" * 80)

    for idx, f in enumerate(findings, 1):
        func_name = f.get("location", {}).get("function", "")
        contract_name = f.get("location", {}).get("contract", "")
        file_path = f.get("location", {}).get("file", str(target_path))
        pattern_id = map_template_to_pattern(f.get("template_id", ""))

        print(f"\n>>> Triaging Finding #{idx}: {f.get('title')} ({contract_name}.{func_name})")

        # 1. Extract AST bundle from Go engine
        ast_bundle_str = ""
        try:
            raw_bundle = bridge.extract_bundle(func_name, file_path, contract_name=contract_name, output_format="md")
            if isinstance(raw_bundle, str) and not raw_bundle.startswith("error"):
                ast_bundle_str = raw_bundle
                logger.info("  ✓ AST Bundle extracted via w3goaudit for %s.%s", contract_name, func_name)
        except Exception as err:
            logger.warning("  Could not extract AST bundle: %s", err)

        # 2. Check authorization fact if available
        auth_fact_summary = ""
        func_full_id = f"{file_path}#{contract_name}.{func_name}"
        matched_auth = next((v for k, v in auth_facts.items() if contract_name in k and func_name in k), None)
        if matched_auth:
            verdict = matched_auth.get("verdict", "unknown")
            reasons = matched_auth.get("reasons", [])
            auth_fact_summary = f"W3GoAudit Auth Verdict: {verdict.upper()} (reasons: {', '.join(reasons)})"
            logger.info("  ✓ Authorization Fact: %s", auth_fact_summary)

        # 3. Form case dict for AI triage
        code_snippet = f.get("reachability", {}).get("steps", [{}])[0].get("snippet", "")
        if not code_snippet:
            code_snippet = f"contract {contract_name} {{\n    // function {func_name} (Line {f.get('location', {}).get('line')})\n}}"

        enriched_context = f.get("message", "")
        if auth_fact_summary:
            enriched_context += f"\n\n{auth_fact_summary}"
        if ast_bundle_str:
            enriched_context += f"\n\n### AST EXTRACTED CONTEXT:\n{ast_bundle_str[:1500]}"

        case = {
            "case_id": f"w3goaudit-{idx:03d}",
            "pattern_id": pattern_id,
            "finding_title": f.get("title", ""),
            "finding_content": f.get("message", "") + "\nRecommendation: " + f.get("recommendation", ""),
            "code_snippet": code_snippet,
            "context_notes": enriched_context,
            "ground_truth_label": "Unknown",
            "ground_truth_reason": "",
        }

        if skip_ai:
            triaged_findings.append({
                "static_finding": f,
                "ai_decision": "SKIPPED",
                "ai_reason": "AI triage disabled by user flag",
            })
            continue

        # 4. Pass 1: Auditor Pass (Checklist Grounded)
        t_start = time.time()
        logger.info("  Running Pass 1 (Auditor Checklist Pass on %s)...", model)
        auditor_res = triage_baseline_4_knowledge_grounded(case, provider=provider, model=model)

        # 5. Pass 2: Critic Pass (Devil's Advocate)
        logger.info("  Running Pass 2 (Critic Adversarial Pass on %s)...", model)
        critic_res = triage_baseline_5_auditor_critic(case, provider=provider, auditor_result=auditor_res, model=model)
        t_duration = time.time() - t_start

        final_label = critic_res.get("label", "Uncertain")
        final_reason = critic_res.get("reason", auditor_res.get("reason", ""))

        status_icon = "TRUE POSITIVE (CONFIRMED)" if final_label == "TP" else (
            "FALSE POSITIVE (FILTERED OUT)" if final_label == "FP" else "🟡 UNCERTAIN (NEEDS REVIEW)"
        )
        print(f"  Result: {status_icon} (took {t_duration:.1f}s)")
        print(f"  Reason: {final_reason}")

        triaged_findings.append({
            "finding_id": f"finding-{idx:03d}",
            "template_id": f.get("template_id"),
            "severity": f.get("severity"),
            "title": f.get("title"),
            "location": f.get("location"),
            "ai_triage": {
                "verdict": final_label,
                "auditor_pass": auditor_res.get("label"),
                "critic_consensus": critic_res.get("critic_consensus", True),
                "reasoning": final_reason,
                "checklist_evaluations": auditor_res.get("checklist_answers", []),
            },
        })

    # -------------------------------------------------------------------------
    # STAGE 4: Final Summary Report
    # -------------------------------------------------------------------------
    report_file = output_dir / "final_ai_audit_report.json"
    report_data = {
        "metadata": {
            "target": str(target_path),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "static_findings_count": len(findings),
            "ai_confirmed_tp": sum(1 for tf in triaged_findings if tf.get("ai_triage", {}).get("verdict") == "TP"),
            "ai_filtered_fp": sum(1 for tf in triaged_findings if tf.get("ai_triage", {}).get("verdict") == "FP"),
            "ai_uncertain": sum(1 for tf in triaged_findings if tf.get("ai_triage", {}).get("verdict") == "Uncertain"),
            "engine": "w3goaudit.exe (Go AST/WQL)",
            "ai_model": f"{provider}:{model}",
        },
        "findings": triaged_findings,
    }

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print(" W3GoAudit — Final Audit Summary")
    print("=" * 80)
    meta = report_data["metadata"]
    print(f" Raw Static Findings:    {meta['static_findings_count']}")
    print(f" Confirmed Bugs (TP):    {meta['ai_confirmed_tp']} (Action required)")
    print(f" Filtered Out (FP):      {meta['ai_filtered_fp']} (Saved auditor review time)")
    print(f" Uncertain (Review):     {meta['ai_uncertain']}")
    print(f"\n[OK] Full Report successfully written to: {report_file}\n")

    return report_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Solidity source file or contracts directory to scan")
    parser.add_argument("--output", default=None, help="Output directory for reports (default: ./w3goaudit_ai_out)")
    parser.add_argument("--provider", default="ollama", choices=["ollama", "groq", "gemini", "offline"], help="AI provider")
    parser.add_argument("--model", default="qwen2.5-coder:7b", help="AI model name")
    parser.add_argument("--skip-ai", action="store_true", help="Run static scan only without AI triage")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    if not target.exists():
        logger.error("Target path %s does not exist.", target)
        sys.exit(1)

    out_dir = Path(args.output).resolve() if args.output else target.parent / "w3goaudit_ai_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_full_pipeline(target, out_dir, provider=args.provider, model=args.model, skip_ai=args.skip_ai)


if __name__ == "__main__":
    main()
