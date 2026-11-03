"""Unit test for Pilot Dataset and Triage Evaluator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.run_pilot_triage import (
    calculate_metrics,
    triage_baseline_1_rule_only,
    triage_baseline_2_heuristic,
    triage_baseline_3_naive_llm,
    triage_baseline_4_knowledge_grounded,
)


def test_pilot_dataset_structure():
    dataset_path = ROOT / "data/pilot/pilot_dataset.json"
    assert dataset_path.exists(), "pilot_dataset.json must exist"

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert "meta" in data
    assert "cases" in data
    assert len(data["cases"]) == 12

    valid_labels = {"TP", "FP", "Uncertain"}
    for c in data["cases"]:
        assert c["ground_truth_label"] in valid_labels
        assert c["pattern_id"] in {"SOL-UINT128-NARROWING-001", "SOL-ACCESS-CONTROL-001"}
        assert len(c["code_snippet"]) > 0
        assert len(c["finding_title"]) > 0


def test_pilot_dataset_v2_structure():
    v2_path = ROOT / "data/pilot/pilot_dataset_v2.json"
    assert v2_path.exists(), "pilot_dataset_v2.json must exist"

    data = json.loads(v2_path.read_text(encoding="utf-8"))
    assert data["meta"]["version"] == "2.0"
    assert len(data["dev_cases"]) == 12
    assert len(data["test_cases"]) == 8

    valid_labels = {"TP", "FP", "Uncertain"}
    for c in data["dev_cases"] + data["test_cases"]:
        assert c["ground_truth_label"] in valid_labels
        assert c["pattern_id"] in {"SOL-UINT128-NARROWING-001", "SOL-ACCESS-CONTROL-001"}


def test_pilot_baselines_execution():
    dataset_path = ROOT / "data/pilot/pilot_dataset.json"
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = data["cases"]

    # Baseline 1
    p1 = [triage_baseline_1_rule_only(c) for c in cases]
    m1 = calculate_metrics(cases, p1)
    assert m1["recall"] == 100.0  # Rule engine catches all TPs
    assert m1["fp_rate"] == 100.0  # But also triggers on all FPs

    # Baseline 2
    p2 = [triage_baseline_2_heuristic(c) for c in cases]
    m2 = calculate_metrics(cases, p2)
    assert m2["fp_rate"] == 0.0  # Heuristic eliminates FPs with guard checks

    # Baseline 4
    p4 = [triage_baseline_4_knowledge_grounded(c, api_key=None) for c in cases]
    m4 = calculate_metrics(cases, p4)
    assert m4["accuracy"] == 100.0
    assert m4["f1_score"] == 100.0


def test_baseline_5_auditor_critic():
    from scripts.run_pilot_triage import triage_baseline_5_auditor_critic

    v2_path = ROOT / "data/pilot/pilot_dataset_v2.json"
    data = json.loads(v2_path.read_text(encoding="utf-8"))
    test_cases = data["test_cases"]

    # Baseline 5 on hard test cases
    p5 = [triage_baseline_5_auditor_critic(c, api_key=None) for c in test_cases]
    m5 = calculate_metrics(test_cases, p5)
    assert m5["accuracy"] == 100.0
    assert m5["fp_rate"] == 0.0


def test_context_assembler():
    from services.context_assembler import assemble_context_from_snippet

    snippet = """
    contract Vault is Ownable, ReentrancyGuard {
        using SafeCast for uint256;
        uint128 public maxDeposit;

        function updateDeposit(uint256 val) external onlyOwner {
            require(val <= type(uint128).max, "overflow");
            maxDeposit = uint128(val);
        }
    }
    """
    ctx = assemble_context_from_snippet(snippet, "SOL-UINT128-NARROWING-001", "updateDeposit")
    assert ctx.external_visibility is True
    assert "onlyOwner" in ctx.modifiers_on_function
    assert ctx.has_local_guard is True
    assert ctx.uses_safecast is True
    assert "Ownable" in ctx.inheritance_chain
    assert ctx.completeness_score >= 0.8
    assert "updateDeposit" in ctx.to_prompt_str()


def test_pilot_dataset_reentrancy_structure():
    reentrancy_path = ROOT / "data/pilot/pilot_dataset_reentrancy.json"
    assert reentrancy_path.exists(), "pilot_dataset_reentrancy.json must exist"

    data = json.loads(reentrancy_path.read_text(encoding="utf-8"))
    assert data["meta"]["pattern"] == "SOL-REENTRANCY-001"
    assert len(data["dev_cases"]) == 12
    assert len(data["test_cases"]) == 4

    valid_labels = {"TP", "FP", "Uncertain"}
    for c in data["dev_cases"] + data["test_cases"]:
        assert c["ground_truth_label"] in valid_labels
        assert c["pattern_id"] == "SOL-REENTRANCY-001"
        assert len(c["code_snippet"]) > 0


def test_reentrancy_context_extraction():
    from services.context_assembler import assemble_context_from_snippet

    snippet = """
    contract Vault is ReentrancyGuard {
        mapping(address => uint256) public balances;

        function withdraw(uint256 amount) external nonReentrant {
            require(balances[msg.sender] >= amount);
            balances[msg.sender] -= amount;
            (bool ok,) = msg.sender.call{value: amount}("");
            require(ok);
        }
    }
    """
    ctx = assemble_context_from_snippet(snippet, "SOL-REENTRANCY-001", "withdraw")
    assert ctx.has_reentrancy_guard is True
    assert ctx.has_external_call is True
    assert ctx.is_cei_compliant is True
    assert "nonReentrant" in ctx.modifiers_on_function
    assert "ReentrancyGuard" in ctx.inheritance_chain
    assert "Reentrancy Guard: YES" in ctx.to_prompt_str()


def test_reentrancy_triage_baselines():
    from scripts.run_pilot_triage import (
        triage_baseline_4_knowledge_grounded,
        triage_baseline_5_auditor_critic,
    )

    reentrancy_path = ROOT / "data/pilot/pilot_dataset_reentrancy.json"
    data = json.loads(reentrancy_path.read_text(encoding="utf-8"))
    cases = data["dev_cases"] + data["test_cases"]

    # Baseline 4 and Baseline 5 on Reentrancy
    p4 = [triage_baseline_4_knowledge_grounded(c, provider="offline") for c in cases]
    m4 = calculate_metrics(cases, p4)
    assert m4["accuracy"] == 100.0
    assert m4["fp_rate"] == 0.0

    p5 = [triage_baseline_5_auditor_critic(c, provider="offline", auditor_result=res) for c, res in zip(cases, p4)]
    m5 = calculate_metrics(cases, p5)
    assert m5["accuracy"] == 100.0
    assert m5["fp_rate"] == 0.0


def test_phase4a_datasets_structure():
    """Kiểm tra cấu trúc và tính toàn vẹn của 3 dataset Phase 4A."""
    patterns = [
        ("pilot_dataset_delegatecall.json", "SOL-DELEGATECALL-001"),
        ("pilot_dataset_arbitrary_from.json", "SOL-ARBITRARY-FROM-001"),
        ("pilot_dataset_unchecked_return.json", "SOL-UNCHECKED-RETURN-001"),
    ]
    valid_labels = {"TP", "FP", "Uncertain"}

    for filename, expected_pattern in patterns:
        path = ROOT / "data/pilot" / filename
        assert path.exists(), f"Missing dataset: {filename}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["meta"]["pattern"] == expected_pattern
        assert len(data["dev_cases"]) == 12, f"{filename} dev_cases != 12"
        assert len(data["test_cases"]) == 4, f"{filename} test_cases != 4"

        for c in data["dev_cases"] + data["test_cases"]:
            assert c["ground_truth_label"] in valid_labels
            assert c["pattern_id"] == expected_pattern
            assert len(c["code_snippet"]) > 0


def test_phase4a_context_extractors():
    """Kiểm tra Context Assembler trích xuất đúng signals cho 3 pattern mới."""
    from services.context_assembler import assemble_context_from_snippet

    # 1. Delegatecall signals
    del_code = """
    contract Proxy {
        address public immutable implementation;
        constructor(address _impl) { implementation = _impl; }
        fallback() external payable {
            (bool ok,) = implementation.delegatecall(msg.data);
            require(ok);
        }
    }
    """
    ctx_del = assemble_context_from_snippet(del_code, "SOL-DELEGATECALL-001", "fallback")
    assert ctx_del.has_delegatecall is True
    assert ctx_del.delegatecall_target_fixed is True

    # 2. Arbitrary From signals
    from_code = """
    function deposit(address from, uint256 amount) external {
        require(from == msg.sender, "only caller");
        token.transferFrom(from, address(this), amount);
    }
    """
    ctx_from = assemble_context_from_snippet(from_code, "SOL-ARBITRARY-FROM-001", "deposit")
    assert ctx_from.has_transfer_from is True
    assert ctx_from.from_is_msg_sender is True
    assert ctx_from.from_has_require_check is True

    # 3. Unchecked Return signals
    ret_code = """
    using SafeERC20 for IERC20;
    function payout(address to, uint256 amount) external {
        token.safeTransfer(to, amount);
    }
    """
    ctx_ret = assemble_context_from_snippet(ret_code, "SOL-UNCHECKED-RETURN-001", "payout")
    assert ctx_ret.uses_safe_erc20 is True
    assert ctx_ret.return_value_checked is True


def test_phase4a_baselines_accuracy():
    """Kiểm tra B4 và B5 đạt độ chính xác 100% trên cả 3 pattern mới."""
    from scripts.run_pilot_triage import (
        triage_baseline_4_knowledge_grounded,
        triage_baseline_5_auditor_critic,
    )

    filenames = [
        "pilot_dataset_delegatecall.json",
        "pilot_dataset_arbitrary_from.json",
        "pilot_dataset_unchecked_return.json",
    ]
    for fn in filenames:
        path = ROOT / "data/pilot" / fn
        data = json.loads(path.read_text(encoding="utf-8"))
        cases = data["dev_cases"] + data["test_cases"]

        p4 = [triage_baseline_4_knowledge_grounded(c, provider="offline") for c in cases]
        m4 = calculate_metrics(cases, p4)
        assert m4["accuracy"] == 100.0, f"B4 failed on {fn}"
        assert m4["fp_rate"] == 0.0

        p5 = [triage_baseline_5_auditor_critic(c, provider="offline", auditor_result=res) for c, res in zip(cases, p4)]
        m5 = calculate_metrics(cases, p5)
        assert m5["accuracy"] == 100.0, f"B5 failed on {fn}"
        assert m5["fp_rate"] == 0.0


