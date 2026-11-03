#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.run_pilot_triage import (
    calculate_metrics,
    triage_baseline_1_rule_only,
    triage_baseline_2_heuristic,
    triage_baseline_3_naive_llm,
    triage_baseline_4_knowledge_grounded,
    triage_baseline_5_auditor_critic,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("regression_suite")

REGRESSION_REPORT_PATH = ROOT / "data/pilot/regression_report.json"


def run_unit_tests() -> tuple[bool, str]:
    """Chạy pytest trên toàn bộ unit test suite."""
    logger.info("==================================================================")
    logger.info("STEP 1: Chạy Pytest Unit Test Suite (249+ tests)...")
    logger.info("==================================================================")
    cmd = [sys.executable, "-m", "pytest", "-q"]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    passed = res.returncode == 0
    output = (res.stdout + res.stderr).strip()
    last_line = output.splitlines()[-1] if output else "No output"
    logger.info("Pytest result: %s (%s)", "PASSED" if passed else "FAILED", last_line)
    return passed, last_line


def evaluate_dataset(dataset_name: str, dataset_path: Path) -> dict:
    """Đánh giá 5 baselines trên một tập dataset pilot."""
    logger.info("------------------------------------------------------------------")
    logger.info("Evaluating dataset: %s (%s)", dataset_name, dataset_path.name)
    logger.info("------------------------------------------------------------------")

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "cases" in data:
        cases = data["cases"]
    else:
        cases = data.get("dev_cases", []) + data.get("test_cases", [])

    results = {}

    # B1: Rule-Only
    p1 = [triage_baseline_1_rule_only(c) for c in cases]
    results["Baseline 1 (Rule-Only)"] = calculate_metrics(cases, p1)

    # B2: Static Heuristic
    p2 = [triage_baseline_2_heuristic(c) for c in cases]
    results["Baseline 2 (Heuristic)"] = calculate_metrics(cases, p2)

    # B3: Naive LLM
    p3 = [triage_baseline_3_naive_llm(c, provider="offline") for c in cases]
    results["Baseline 3 (Naive LLM)"] = calculate_metrics(cases, p3)

    # B4: Grounded Checklist
    p4 = [triage_baseline_4_knowledge_grounded(c, provider="offline") for c in cases]
    results["Baseline 4 (W3GoAudit Checklist)"] = calculate_metrics(cases, p4)

    # B5: Auditor + Critic Pass
    p5 = [
        triage_baseline_5_auditor_critic(c, provider="offline", auditor_result=res)
        for c, res in zip(cases, p4)
    ]
    results["Baseline 5 (Auditor + Critic)"] = calculate_metrics(cases, p5)

    return {
        "dataset_name": dataset_name,
        "total_cases": len(cases),
        "baselines": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-unit-tests", action="store_true", help="Skip pytest unit tests step")
    args = parser.parse_args()

    start_time = time.time()
    all_passed = True
    invariants_checked = []

    # Step 1: Unit tests
    if not args.skip_unit_tests:
        pytest_ok, pytest_summary = run_unit_tests()
        invariants_checked.append({
            "check": "Unit Tests Pass Rate == 100%",
            "passed": pytest_ok,
            "details": pytest_summary,
        })
        if not pytest_ok:
            all_passed = False
    else:
        pytest_summary = "SKIPPED"

    # Step 2: Benchmark Pilot v2 (Narrowing Cast & Access Control - 20 cases)
    v2_path = ROOT / "data/pilot/pilot_dataset_v2.json"
    eval_v2 = evaluate_dataset("Pilot v2 (Narrowing Cast & Access Control)", v2_path)

    # Step 3: Benchmark Reentrancy (16 cases)
    reentrancy_path = ROOT / "data/pilot/pilot_dataset_reentrancy.json"
    eval_reentrancy = evaluate_dataset("Pilot Reentrancy (SOL-REENTRANCY-001)", reentrancy_path)

    # Step 4: Benchmark Delegatecall (16 cases)
    delegatecall_path = ROOT / "data/pilot/pilot_dataset_delegatecall.json"
    eval_delegatecall = evaluate_dataset("Pilot Delegatecall (SOL-DELEGATECALL-001)", delegatecall_path)

    # Step 5: Benchmark Arbitrary From (16 cases)
    arbitrary_from_path = ROOT / "data/pilot/pilot_dataset_arbitrary_from.json"
    eval_arbitrary_from = evaluate_dataset("Pilot Arbitrary From (SOL-ARBITRARY-FROM-001)", arbitrary_from_path)

    # Step 6: Benchmark Unchecked Return (16 cases)
    unchecked_return_path = ROOT / "data/pilot/pilot_dataset_unchecked_return.json"
    eval_unchecked_return = evaluate_dataset("Pilot Unchecked Return (SOL-UNCHECKED-RETURN-001)", unchecked_return_path)

    # Step 7: Quality Gate Invariant Verification
    logger.info("==================================================================")
    logger.info("STEP 7: Kiểm tra Invariants Chất Lượng (Quality Gates — 5 Datasets)...")
    logger.info("==================================================================")

    datasets_to_check = [
        ("Pilot v2", eval_v2),
        ("Reentrancy", eval_reentrancy),
        ("Delegatecall", eval_delegatecall),
        ("Arbitrary From", eval_arbitrary_from),
        ("Unchecked Return", eval_unchecked_return),
    ]

    for name, eval_data in datasets_to_check:
        b4 = eval_data["baselines"]["Baseline 4 (W3GoAudit Checklist)"]
        b5 = eval_data["baselines"]["Baseline 5 (Auditor + Critic)"]

        inv_b4_prec = b4["precision"] >= 95.0
        inv_b4_rec = b4["recall"] >= 95.0
        inv_b4_fp = b4["fp_rate"] <= 5.0
        inv_b5_prec = b5["precision"] >= 95.0
        inv_b5_rec = b5["recall"] >= 95.0
        inv_b5_fp = b5["fp_rate"] <= 5.0

        invariants_checked.extend([
            {"check": f"{name} B4 Precision >= 95%", "passed": inv_b4_prec, "value": f"{b4['precision']}%"},
            {"check": f"{name} B4 Recall >= 95%", "passed": inv_b4_rec, "value": f"{b4['recall']}%"},
            {"check": f"{name} B4 FP Rate <= 5%", "passed": inv_b4_fp, "value": f"{b4['fp_rate']}%"},
            {"check": f"{name} B5 Precision >= 95%", "passed": inv_b5_prec, "value": f"{b5['precision']}%"},
            {"check": f"{name} B5 Recall >= 95%", "passed": inv_b5_rec, "value": f"{b5['recall']}%"},
            {"check": f"{name} B5 FP Rate <= 5%", "passed": inv_b5_fp, "value": f"{b5['fp_rate']}%"},
        ])

    for inv in invariants_checked:
        status = "✓ PASS" if inv["passed"] else "✗ FAIL"
        val = f" ({inv.get('value', inv.get('details', ''))})"
        logger.info("  [%s] %s%s", status, inv["check"], val)
        if not inv["passed"]:
            all_passed = False

    # Export full regression report
    elapsed = time.time() - start_time
    report = {
        "metadata": {
            "title": "W3GoAudit Regression Suite Execution Report",
            "phase": "Đợt 4A — Multi-group Expansion (5 Patterns, 84 cases)",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_seconds": round(elapsed, 2),
            "status": "PASSED" if all_passed else "FAILED",
            "total_benchmark_cases": 84,
            "patterns_covered": [
                "SOL-UINT128-NARROWING-001",
                "SOL-ACCESS-CONTROL-001",
                "SOL-REENTRANCY-001",
                "SOL-DELEGATECALL-001",
                "SOL-ARBITRARY-FROM-001",
                "SOL-UNCHECKED-RETURN-001",
            ],
        },
        "invariants": invariants_checked,
        "datasets": {
            "pilot_v2": eval_v2,
            "pilot_reentrancy": eval_reentrancy,
            "pilot_delegatecall": eval_delegatecall,
            "pilot_arbitrary_from": eval_arbitrary_from,
            "pilot_unchecked_return": eval_unchecked_return,
        },
    }

    with open(REGRESSION_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("==================================================================")
    logger.info("Báo cáo hồi quy đã lưu tại: %s", REGRESSION_REPORT_PATH)
    logger.info("KẾT LUẬN TỔNG THỂ: %s (Thời gian: %.2fs)", "TẤT CẢ INVARIANTS ĐẠT YÊU CẦU ✅" if all_passed else "CÓ INVARIANT THẤT BẠI ❌", elapsed)
    logger.info("==================================================================")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
