"""Faithful Reasoning Verifier (FRS - Faithful Reasoning Score).

Research Contribution for W3GoAudit DATN 2026:
Automated verification of LLM security reasoning faithfulness against
Abstract Syntax Tree (AST) facts and 6-layer Context Assembler artifacts.

Key Capabilities:
  1. AST Identifier Grounding: Confirms identifiers cited in AI explanation exist in AST/Context.
  2. Invariant Fact Alignment: Verifies defense claims (SafeCast, nonReentrant, onlyOwner, TWAP, nonce).
  3. Hallucination Detection: Identifies fabricated variables, functions, or modifiers.
  4. Faithful Reasoning Score (FRS): Quantitative metric (0.0 - 1.0) for research benchmarking.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set


SOLIDITY_KEYWORDS: Set[str] = {
    "pragma", "solidity", "contract", "interface", "library", "abstract",
    "function", "modifier", "event", "error", "struct", "enum",
    "public", "private", "internal", "external", "view", "pure", "payable",
    "constant", "immutable", "override", "virtual", "indexed",
    "uint", "uint8", "uint16", "uint32", "uint64", "uint128", "uint256",
    "int", "int8", "int16", "int32", "int64", "int128", "int256",
    "bytes", "bytes1", "bytes4", "bytes32", "string", "address", "bool",
    "mapping", "memory", "storage", "calldata",
    "return", "returns", "revert", "require", "assert",
    "if", "else", "for", "while", "do", "break", "continue",
    "true", "false", "this", "super", "msg", "tx", "block",
    "sender", "value", "data", "sig", "origin", "gasprice", "timestamp", "number",
    "transfer", "send", "call", "delegatecall", "staticcall",
}

COMMON_ENGLISH_WORDS: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall", "should",
    "may", "might", "must", "can", "could", "to", "of", "in", "for", "on",
    "with", "at", "by", "from", "up", "about", "into", "over", "after",
    "this", "that", "these", "those", "it", "its", "they", "them", "their",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "but", "and", "or", "yet", "if", "then", "else", "when", "while",
    "can", "will", "just", "now", "vulnerability", "finding", "scanner", "alert",
    "code", "variable", "function", "state", "contract", "attack", "exploit",
    "safe", "unsafe", "overflow", "underflow", "reentrancy", "access", "control",
    "true", "false", "positive", "negative", "uncertain", "because", "due", "risk",
    "check", "checked", "unchecked", "cast", "casting", "casts", "truncation", "loss",
    "value", "values", "call", "calls", "caller", "external", "internal",
    "used", "using", "uses", "use", "library", "via", "without", "lacks", "lacking",
    "missing", "protects", "protected", "protection", "restrict", "restricts", "restricted",
    "prevents", "prevented", "prevention", "defense", "defensive", "present", "absent",
    "parameter", "argument", "signature", "modifier", "modifiers", "logic", "statement",
}

SECURITY_DOMAIN_TERMS: Set[str] = {
    "safecast", "reentrancyguard", "ownable", "ierc20", "erc20", "ecdsa", "eip712",
    "math", "accesscontrol", "initializable", "pausable", "chainlink", "uniswap",
    "twap", "aggregatorv3", "openzeppelin", "solmate",
}


class FaithfulReasoningVerifier:
    """Verifies that LLM security conclusions are grounded in verifiable AST facts."""

    def __init__(self, token_grounding_weight: float = 0.5, invariant_weight: float = 0.5):
        self.w_grounding = token_grounding_weight
        self.w_invariant = invariant_weight

    def extract_identifiers(self, text: str) -> Set[str]:
        """Extracts code identifiers from prose or code snippets."""
        tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", text)
        result = set()
        for t in tokens:
            lower = t.lower()
            if len(t) <= 2:
                continue
            if lower in SOLIDITY_KEYWORDS or lower in COMMON_ENGLISH_WORDS or lower in SECURITY_DOMAIN_TERMS:
                continue
            result.add(t)
        return result

    def collect_ground_truth_identifiers(self, snippet: str, context: Dict[str, Any] | None) -> Set[str]:
        """Collects all valid identifiers from code snippet and 6-layer context bundle."""
        valid_ids = self.extract_identifiers(snippet)

        if not context:
            return valid_ids

        # Layer 1: Function signature & AST params
        fn_sig = str(context.get("function_signature", ""))
        valid_ids.update(self.extract_identifiers(fn_sig))

        # Layer 2: State variables
        state_vars = context.get("contract_state_vars", []) or context.get("state_variables", [])
        if isinstance(state_vars, list):
            for var in state_vars:
                valid_ids.update(self.extract_identifiers(str(var)))

        # Layer 3: Modifiers applied
        modifiers = context.get("modifiers_applied", []) or context.get("modifiers", [])
        if isinstance(modifiers, list):
            for mod in modifiers:
                valid_ids.update(self.extract_identifiers(str(mod)))

        # Layer 4: Interface inheritance
        parents = context.get("interface_inheritance", []) or context.get("parents", [])
        if isinstance(parents, list):
            for p in parents:
                valid_ids.update(self.extract_identifiers(str(p)))

        # Layer 5: External call targets
        calls = context.get("external_call_targets", []) or context.get("external_calls", [])
        if isinstance(calls, list):
            for c in calls:
                valid_ids.update(self.extract_identifiers(str(c)))

        # Layer 6: Library usage
        libs = context.get("library_usage", []) or context.get("libraries", [])
        if isinstance(libs, list):
            for lib in libs:
                valid_ids.update(self.extract_identifiers(str(lib)))

        # Pattern-specific signals
        signals = context.get("signals", {}) or {}
        if isinstance(signals, dict):
            for k, v in signals.items():
                valid_ids.update(self.extract_identifiers(str(k)))
                valid_ids.update(self.extract_identifiers(str(v)))

        return valid_ids

    def is_positive_claim(self, text: str, keyword: str) -> bool:
        """Determines if a keyword is claimed to be present and defensive (vs absent/missing)."""
        lower = text.lower()
        if keyword not in lower:
            return False
        # Check if preceded by negative qualifier within 30 characters
        negatives = ["without", "lacks", "lacking", "no ", "not ", "missing", "fails to use", "does not"]
        idx = lower.find(keyword)
        window = lower[max(0, idx - 30):idx]
        if any(neg in window for neg in negatives):
            return False
        return True

    def verify_invariant_claims(
        self,
        explanation: str,
        context: Dict[str, Any] | None,
        snippet: str,
    ) -> Dict[str, Any]:
        """Checks if specific defensive claims made by the LLM match reality."""
        lower_exp = explanation.lower()
        full_evidence = (snippet + " " + str(context or "")).lower()

        checks: Dict[str, Dict[str, Any]] = {}

        # 1. SafeCast defense claim
        if self.is_positive_claim(lower_exp, "safecast") or self.is_positive_claim(lower_exp, "touint"):
            passed = ("safecast" in full_evidence or "touint" in full_evidence or "toint" in full_evidence)
            checks["safecast_defense"] = {
                "claimed": True,
                "verified": passed,
                "detail": "Verified SafeCast usage" if passed else "Claimed SafeCast but not present in AST"
            }

        # 2. Access control / Auth defense claim
        if any(self.is_positive_claim(lower_exp, w) for w in ["onlyowner", "onlyrole", "auth", "access control"]):
            passed = any(w in full_evidence for w in ["onlyowner", "auth", "onlyrole", "require(msg.sender", "if (msg.sender"])
            checks["access_control_defense"] = {
                "claimed": True,
                "verified": passed,
                "detail": "Verified auth modifier or check" if passed else "Claimed auth check but none found in context"
            }

        # 3. Reentrancy guard / CEI claim
        if any(self.is_positive_claim(lower_exp, w) for w in ["nonreentrant", "reentrancyguard"]):
            passed = any(w in full_evidence for w in ["nonreentrant", "reentrancyguard", "mutex", "lock", "cei_state_updated_before_call"])
            checks["reentrancy_defense"] = {
                "claimed": True,
                "verified": passed,
                "detail": "Verified reentrancy guard or CEI" if passed else "Claimed reentrancy protection but not found"
            }

        # 4. Oracle TWAP / freshness claim
        if any(self.is_positive_claim(lower_exp, w) for w in ["twap", "latestrounddata", "heartbeat", "chainlink"]):
            passed = any(w in full_evidence for w in ["twap", "consult", "latestrounddata", "updatedat", "chainlink", "oracle"])
            checks["oracle_defense"] = {
                "claimed": True,
                "verified": passed,
                "detail": "Verified TWAP/Chainlink oracle protection" if passed else "Claimed TWAP/freshness without AST oracle evidence"
            }

        # 5. Nonce / replay claim
        if any(self.is_positive_claim(lower_exp, w) for w in ["nonce", "eip712"]):
            passed = any(w in full_evidence for w in ["nonce", "nonces", "_usenonce", "eip712", "separator", "usedsignatures"])
            checks["nonce_replay_defense"] = {
                "claimed": True,
                "verified": passed,
                "detail": "Verified nonce replay tracking" if passed else "Claimed nonce replay protection but not found"
            }

        # Calculate invariant score
        if not checks:
            # No specific defensive claim was made
            alignment_score = 1.0
            contradiction_count = 0
        else:
            total_claimed = len(checks)
            verified_count = sum(1 for c in checks.values() if c["verified"])
            contradiction_count = total_claimed - verified_count
            alignment_score = verified_count / total_claimed

        return {
            "checks": checks,
            "alignment_score": alignment_score,
            "contradiction_count": contradiction_count,
        }

    def verify(
        self,
        predicted_label: str,
        explanation: str,
        snippet: str,
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Performs full Faithful Reasoning Verification and returns FRS score."""
        explanation_tokens = self.extract_identifiers(explanation)
        valid_ast_tokens = self.collect_ground_truth_identifiers(snippet, context)

        # Grounding evaluation
        if not explanation_tokens:
            # If explanation has no specific tokens, grounding is neutral
            grounding_ratio = 1.0
            grounded_tokens = []
            hallucinated_tokens = []
        else:
            # Check overlap case-insensitively
            valid_lower = {t.lower() for t in valid_ast_tokens}
            grounded = [t for t in explanation_tokens if t.lower() in valid_lower]
            hallucinated = [t for t in explanation_tokens if t.lower() not in valid_lower]

            grounded_tokens = grounded
            hallucinated_tokens = hallucinated
            grounding_ratio = len(grounded) / len(explanation_tokens) if explanation_tokens else 1.0

        # Invariant evaluation
        inv_result = self.verify_invariant_claims(explanation, context, snippet)
        inv_score = inv_result["alignment_score"]

        # Composite FRS (Faithful Reasoning Score): 0.0 to 1.0
        # If there are severe invariant contradictions (e.g. claiming SafeCast when non-existent), apply heavy penalty
        penalty = inv_result["contradiction_count"] * 0.25
        raw_score = (self.w_grounding * grounding_ratio) + (self.w_invariant * inv_score) - penalty
        frs = max(0.0, min(1.0, round(raw_score, 3)))

        # Qualitative verdict
        if frs >= 0.80:
            verdict = "FAITHFUL"
            recommendation = "Reasoning is grounded in verifiable code facts and AST invariants."
        elif frs >= 0.50:
            verdict = "BORDERLINE"
            recommendation = "Reasoning contains partially ungrounded claims; manual auditor spot-check suggested."
        else:
            verdict = "UNFAITHFUL"
            recommendation = "High hallucination risk: explanation cites non-existent identifiers or false defense claims."

        return {
            "predicted_label": predicted_label,
            "faithful_reasoning_score": frs,
            "verdict": verdict,
            "grounding_ratio": round(grounding_ratio, 3),
            "invariant_alignment_score": round(inv_score, 3),
            "grounded_token_count": len(grounded_tokens),
            "hallucinated_token_count": len(hallucinated_tokens),
            "hallucinated_tokens": sorted(list(set(hallucinated_tokens)))[:10],
            "invariant_checks": inv_result["checks"],
            "recommendation": recommendation,
        }
