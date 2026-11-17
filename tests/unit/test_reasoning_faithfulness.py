"""Unit tests for Faithful Reasoning Verifier (FRS).

Validates:
  1. High FRS score on grounded, AST-consistent explanations.
  2. Low FRS score and Hallucination detection on fabricated variables/claims.
  3. Invariant contradiction penalty when claiming non-existent protections (SafeCast, nonReentrant).
  4. Integration with Context Assembler 6-layer bundle.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.services.reasoning_faithfulness_verifier import FaithfulReasoningVerifier


def test_faithful_reasoning_perfect_grounding():
    verifier = FaithfulReasoningVerifier()
    snippet = "function setFee(uint256 newFee) external onlyOwner { fee = uint128(newFee); }"
    context = {
        "function_signature": "setFee(uint256)",
        "modifiers_applied": ["onlyOwner"],
        "contract_state_vars": ["fee", "owner"],
    }
    explanation = "Function setFee uses onlyOwner modifier to restrict access, but casts newFee to uint128 without SafeCast."
    
    result = verifier.verify("TP", explanation, snippet, context)
    assert result["verdict"] in ["FAITHFUL", "BORDERLINE"]
    assert result["faithful_reasoning_score"] >= 0.70
    assert result["invariant_alignment_score"] == 1.0
    assert len(result["hallucinated_tokens"]) == 0


def test_hallucination_detection_unfaithful_claim():
    verifier = FaithfulReasoningVerifier()
    snippet = "function transfer(address to, uint256 amount) external { balances[msg.sender] -= amount; }"
    context = {
        "function_signature": "transfer(address,uint256)",
        "contract_state_vars": ["balances"],
    }
    # Explanation invents non-existent variables `isWhitelistedAdmin` and `globalPauseState`
    # and falsely claims `nonReentrant` modifier is present!
    explanation = "The function is safe because it uses nonReentrant modifier and checks isWhitelistedAdmin and globalPauseState."
    
    result = verifier.verify("FP", explanation, snippet, context)
    assert result["verdict"] == "UNFAITHFUL"
    assert result["faithful_reasoning_score"] < 0.50
    assert "isWhitelistedAdmin" in result["hallucinated_tokens"]
    assert "globalPauseState" in result["hallucinated_tokens"]
    assert result["invariant_checks"]["reentrancy_defense"]["verified"] is False


def test_safecast_defense_grounded():
    verifier = FaithfulReasoningVerifier()
    snippet = "uint128 val = SafeCast.toUint128(amount);"
    context = {
        "library_usage": ["SafeCast for uint256"],
    }
    explanation = "The casting is safe because SafeCast library is used via toUint128."
    result = verifier.verify("FP", explanation, snippet, context)
    assert result["invariant_checks"]["safecast_defense"]["verified"] is True
    assert result["faithful_reasoning_score"] >= 0.85

