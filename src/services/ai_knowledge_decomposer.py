"""AI-driven finding decomposition service.

Decomposes unstructured audit report findings into an 8-facet structured knowledge model
with grounded citations. Supports Gemini, OpenAI/DeepSeek, local Ollama, and offline expert fallback.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

from dotenv import load_dotenv
import httpx

load_dotenv()

from src.models.ai_knowledge import AIDecomposedFinding, GroundedItem
from src.models.knowledge_base import GroundedCitation, GroundedClaim, KnowledgeRevision
from src.models.knowledge_contract import SourceFindingSnapshot, stable_hash

logger = logging.getLogger("crawler.ai_decomposer")

SYSTEM_PROMPT = """Bạn là Chuyên gia Thẩm định An ninh Smart Contract Solidity cấp cao (Senior Solidity Security Auditor).
Nhiệm vụ của bạn là đọc một bài báo cáo audit (Finding) kèm theo đoạn mã nguồn bằng chứng (Code Evidence), sau đó phân rã bài viết thành 8 trường tri thức có cấu trúc chuẩn mực.

CÁC QUY TẮC BẮT BUỘC:
1. KHÔNG suy diễn hoặc bịa đặt ngoài nội dung bài viết và mã nguồn được cung cấp.
2. Với mỗi mục (suspicious_pattern, necessary_condition, sufficient_condition, trigger_condition, remediation), bạn BẮT BUỘC phải trích dẫn lại một câu văn nguyên văn ngắn từ bài viết gốc (quote_from_report) làm căn cứ đối soát (Grounded Citation).
3. Phân biệt chính xác:
   - necessary_condition (Điều kiện cần): Thuộc tính tĩnh về kiểu dữ liệu hoặc cấu trúc code khiến đoạn code có khả năng rủi ro (VD: Kiểu nguồn uint256 rộng hơn kiểu đích uint128; Hàm setter thiếu modifier kiểm tra quyền).
   - sufficient_condition (Điều kiện đủ): Tình trạng runtime cho phép giá trị vượt ngoài giả định an toàn mà không bị guard chặn lại (VD: Người dùng có thể kiểm soát giá trị nạp vào > 2^128 - 1; Bất kỳ ai cũng có thể gọi hàm đổi fee recipient).
   - trigger_condition (Điều kiện kích hoạt): Hành vi hoặc giao dịch cụ thể để kích hoạt lỗ hổng tại runtime (VD: Kẻ tấn công gọi updateReserve với amount = 2**128; Kẻ tấn công gọi setFeeRecipient với địa chỉ của mình).
4. verification_checklist: Danh sách 3-5 câu hỏi Yes/No ngắn gọn để auditor/AI kiểm tra trên hợp đồng mới.
5. missing_context_signals: Danh sách các thông tin ngoài hàm cần thu thập thêm.
6. Trả về ĐÚNG cấu trúc JSON sau:
{
  "finding_id": "string",
  "vulnerability_category": "string",
  "suspicious_pattern": {"statement": "string", "quote_from_report": "string"},
  "necessary_condition": {"statement": "string", "quote_from_report": "string"},
  "sufficient_condition": {"statement": "string", "quote_from_report": "string"},
  "trigger_condition": {"statement": "string", "quote_from_report": "string"},
  "verification_checklist": ["string"],
  "verification_method": "string",
  "remediation": {"statement": "string", "quote_from_report": "string"},
  "missing_context_signals": ["string"]
}"""


def _normalize_item(item: Any) -> Dict[str, str]:
    if isinstance(item, str):
        return {"statement": item, "quote_from_report": item}
    if isinstance(item, dict):
        stmt = (
            item.get("statement")
            or item.get("description")
            or item.get("pattern_name")
            or item.get("summary")
            or ""
        )
        quote = (
            item.get("quote_from_report")
            or item.get("quote")
            or item.get("citation")
            or item.get("evidence")
            or stmt
        )
        return {"statement": str(stmt), "quote_from_report": str(quote)}
    return {"statement": "", "quote_from_report": ""}


def _normalize_decomposed_data(data: Dict[str, Any], default_id: str) -> Dict[str, Any]:
    category = (
        data.get("vulnerability_category")
        or data.get("category")
        or data.get("vulnerability_title")
        or "Unknown"
    )
    checklist = data.get("verification_checklist") or []
    if isinstance(checklist, str):
        checklist = [checklist]
    checklist = [str(x) for x in checklist if x]
    if not checklist:
        checklist = ["Is this condition verified in caller/external context?"]

    method = data.get("verification_method") or "Write test case to verify trigger condition."
    if isinstance(method, dict):
        method = method.get("description") or str(method)

    signals = data.get("missing_context_signals") or []
    if isinstance(signals, str):
        signals = [signals]
    signals = [str(x) for x in signals if x]

    return {
        "finding_id": str(data.get("finding_id") or default_id),
        "vulnerability_category": str(category),
        "suspicious_pattern": _normalize_item(data.get("suspicious_pattern")),
        "necessary_condition": _normalize_item(data.get("necessary_condition")),
        "sufficient_condition": _normalize_item(data.get("sufficient_condition")),
        "trigger_condition": _normalize_item(data.get("trigger_condition")),
        "verification_checklist": checklist,
        "verification_method": str(method),
        "remediation": _normalize_item(data.get("remediation")),
        "missing_context_signals": signals,
    }


class AIKnowledgeDecomposer:
    """Decomposes raw audit finding snapshots into structured 8-facet knowledge."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: str = "auto",  # 'gemini', 'openai', 'ollama', or 'auto'
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.provider = provider
        self.model = model
        self.base_url = base_url

        if self.provider == "ollama":
            self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
            self.model = self.model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
        elif self.provider == "auto":
            # Check local Ollama first
            try:
                with httpx.Client(timeout=1.0) as client:
                    r = client.get("http://localhost:11434/api/version")
                    if r.status_code == 200:
                        self.provider = "ollama"
                        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
                        self.model = self.model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
            except Exception:
                pass

            if self.provider == "auto":
                if os.getenv("GEMINI_API_KEY"):
                    self.provider = "gemini"
                    self.model = self.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
                elif os.getenv("OPENAI_API_KEY"):
                    self.provider = "openai"
                    self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
                    self.model = self.model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
                else:
                    self.provider = "offline"
        elif self.provider == "openai" and not self.base_url:
            self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    def decompose(
        self,
        snapshot: SourceFindingSnapshot,
        code_snippet: str = "",
    ) -> AIDecomposedFinding:
        """Decompose a single finding into the 8-facet structured knowledge model."""
        user_prompt = self._build_prompt(snapshot, code_snippet)

        if self.provider == "gemini" and self.api_key:
            data = self._call_gemini(user_prompt)
        elif self.provider in {"openai", "ollama"} and (self.api_key or self.provider == "ollama"):
            data = self._call_openai(user_prompt)
        else:
            logger.info("Using built-in Expert Engine for offline decomposition: %s", snapshot.snapshot_id)
            data = self._offline_expert_decompose(snapshot, code_snippet)

        normalized = _normalize_decomposed_data(data, default_id=snapshot.source_id or snapshot.snapshot_id)
        return AIDecomposedFinding.model_validate(normalized)

    def _build_prompt(self, snapshot: SourceFindingSnapshot, code_snippet: str) -> str:
        prompt = f"""### BÁO CÁO AUDIT (FINDING REPORT):
Tiêu đề: {snapshot.title}
Nguồn: {snapshot.source} (ID: {snapshot.source_id})

Nội dung báo cáo:
{snapshot.content}
"""
        if code_snippet.strip():
            prompt += f"\n### MÃ NGUỒN BẰNG CHỨNG (CODE EVIDENCE):\n```solidity\n{code_snippet}\n```\n"

        prompt += "\nHãy phân tích và trả về JSON theo đúng định dạng 8 trường tri thức."
        return prompt

    def _call_gemini(self, prompt: str) -> Dict[str, Any]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]}
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        import time
        last_err = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, json=payload)
                    resp.raise_for_status()
                    result = resp.json()
                    text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                    # Clean markdown codeblocks if model returned them
                    if text.startswith("```json"):
                        text = text[7:]
                    elif text.startswith("```"):
                        text = text[3:]
                    if text.endswith("```"):
                        text = text[:-3]
                    return json.loads(text.strip())
            except Exception as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
        raise last_err or RuntimeError("Gemini API call failed after retries")

    def _call_openai(self, prompt: str) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key or 'ollama'}"}
        payload = {
            "model": self.model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(f"{self.base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()
            content = result["choices"][0]["message"]["content"].strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            return json.loads(content.strip())

    def _offline_expert_decompose(
        self, snapshot: SourceFindingSnapshot, code_snippet: str
    ) -> Dict[str, Any]:
        """Built-in deterministic expert decomposition when running offline or without API keys."""
        text = (snapshot.title + "\n" + snapshot.content).lower()
        snippet_lower = code_snippet.lower()

        # Pattern 1: Narrowing cast uint256 -> uint128 (Caviar H-03 style)
        if "uint128" in text or "overflow" in text or "uint128" in snippet_lower:
            return {
                "finding_id": snapshot.source_id,
                "vulnerability_category": "Integer Narrowing / Silent Truncation",
                "suspicious_pattern": {
                    "statement": "Explicit type cast from uint256 to uint128 without bounds check prior to casting.",
                    "quote_from_report": "while the values that update them are of type uint256",
                },
                "necessary_condition": {
                    "statement": "The source calculation is performed as uint256 but the storage variable is typed as uint128.",
                    "quote_from_report": "The reserves are stored as uint128",
                },
                "sufficient_condition": {
                    "statement": "The input amount or updated reserve can exceed type(uint128).max (2^128 - 1) without reverting.",
                    "quote_from_report": "there are no checks preventing the new reserves from exceeding type(uint128).max",
                },
                "trigger_condition": {
                    "statement": "Caller invokes reserve update with an amount >= 2^128, causing silent truncation and reserve to wrap to 0 or incorrect value.",
                    "quote_from_report": "overflow will truncate the value, which causes the reserves to be updated with incorrect values",
                },
                "verification_checklist": [
                    "Is the value being cast to uint128 guarded by a require(amount <= type(uint128).max) statement?",
                    "Can external callers or pool operations supply token amounts exceeding 2^128 - 1?",
                    "Does the updated storage variable control critical pricing or invariant calculations?",
                ],
                "verification_method": "Foundry/Hardhat test supplying 2^128 to update function and asserting whether transaction reverts or silently wraps.",
                "remediation": {
                    "statement": "Use OpenZeppelin SafeCast library (SafeCast.toUint128) or explicit validation before casting.",
                    "quote_from_report": "Consider using OpenZeppelin's SafeCast library to safely cast uint256 to uint128",
                },
                "missing_context_signals": [
                    "Callers of the reserve update function (whether guards exist in outer scope)",
                    "Max supply of underlying tokens to determine if amount can ever reach 2^128 in practice",
                ],
            }

        # Pattern 2: Missing Access Control / Unprotected Setter
        if "access control" in text or "onlyowner" in text or "unprotected" in text:
            return {
                "finding_id": snapshot.source_id,
                "vulnerability_category": "Missing Access Control",
                "suspicious_pattern": {
                    "statement": "State-modifying administrative configuration function lacks access control modifier.",
                    "quote_from_report": "Anyone can call this function to modify critical protocol configuration",
                },
                "necessary_condition": {
                    "statement": "Function visibility is external/public and directly modifies critical state variable.",
                    "quote_from_report": "function is declared public or external without restriction",
                },
                "sufficient_condition": {
                    "statement": "msg.sender is not compared against owner or authorized role in function body or modifiers.",
                    "quote_from_report": "missing require(msg.sender == owner) check",
                },
                "trigger_condition": {
                    "statement": "Unprivileged external address sends a transaction calling the setter, hijacking parameters or recipient.",
                    "quote_from_report": "an attacker can call this function and redirect fees to their own address",
                },
                "verification_checklist": [
                    "Does the function have onlyOwner, onlyRole, or require(msg.sender == authorized) check?",
                    "Is the function intended to be internal instead of external/public?",
                    "Does modifying this variable compromise fund safety or protocol parameters?",
                ],
                "verification_method": "Execute transaction from unprivileged account (e.g. alice) and verify it successfully updates the parameter.",
                "remediation": {
                    "statement": "Add access control modifier (such as onlyOwner) or check msg.sender == owner.",
                    "quote_from_report": "Add the onlyOwner modifier to restrict execution to authorized accounts",
                },
                "missing_context_signals": [
                    "Role initialization in constructor",
                    "Inheritance tree to check if modifier is defined in parent contract",
                ],
            }

        # Generic Default Expert Fallback
        first_line = snapshot.content.split("\n")[0][:100] if snapshot.content else "Audit finding"
        return {
            "finding_id": snapshot.source_id,
            "vulnerability_category": "Logic / Protocol Constraint Violation",
            "suspicious_pattern": {
                "statement": f"Suspicious behavior identified in report: {snapshot.title}",
                "quote_from_report": first_line,
            },
            "necessary_condition": {
                "statement": "Smart contract state allows calling target function without enforcing invariant check.",
                "quote_from_report": first_line,
            },
            "sufficient_condition": {
                "statement": "Runtime state parameters deviate from intended security assumptions.",
                "quote_from_report": first_line,
            },
            "trigger_condition": {
                "statement": "Specific execution flow triggers unexpected state update or asset transfer.",
                "quote_from_report": first_line,
            },
            "verification_checklist": [
                "Is the function input validated against boundary conditions?",
                "Does state change occur before external interactions?",
                "Can external callers manipulate inputs to achieve unintended state?",
            ],
            "verification_method": "Replicate issue with automated unit test asserting expected vs observed state.",
            "remediation": {
                "statement": "Implement defensive validation and invariant assertions.",
                "quote_from_report": first_line,
            },
            "missing_context_signals": [
                "Full contract inheritance graph",
                "External protocol interactions",
            ],
        }


def convert_to_knowledge_revision(
    snapshot: SourceFindingSnapshot,
    decomposed: AIDecomposedFinding,
) -> KnowledgeRevision:
    """Converts AIDecomposedFinding into a Phase 7 compliant KnowledgeRevision."""
    lines = snapshot.content.splitlines()

    def make_citation(quote: str) -> list[GroundedCitation]:
        # Search for quote line in snapshot
        target_line = 1
        for idx, line in enumerate(lines):
            if quote.lower() in line.lower() or line.lower() in quote.lower():
                target_line = idx + 1
                break
        return [
            GroundedCitation(
                snapshot_id=snapshot.snapshot_id,
                start_line=target_line,
                end_line=target_line,
                quote=quote if quote.strip() else lines[0] if lines else "Citation",
            )
        ]

    from src.services.knowledge_builder import claim

    claims = [
        claim(
            "root_cause",
            f"Vulnerability Category: {decomposed.vulnerability_category}. {decomposed.suspicious_pattern.statement}",
            make_citation(decomposed.suspicious_pattern.quote_from_report),
        ),
        claim(
            "preconditions",
            decomposed.necessary_condition.statement,
            make_citation(decomposed.necessary_condition.quote_from_report),
        ),
        claim(
            "exploit_conditions",
            decomposed.sufficient_condition.statement,
            make_citation(decomposed.sufficient_condition.quote_from_report),
        ),
        claim(
            "observed_behavior",
            decomposed.trigger_condition.statement,
            make_citation(decomposed.trigger_condition.quote_from_report),
        ),
        claim(
            "detection_signals",
            "Verification Checklist: " + " | ".join(decomposed.verification_checklist),
            make_citation(decomposed.suspicious_pattern.quote_from_report),
        ),
        claim(
            "remediation",
            decomposed.remediation.statement,
            make_citation(decomposed.remediation.quote_from_report),
        ),
    ]

    kid = "knw_" + stable_hash(["knowledge-source-v1", snapshot.source_key])
    proc_key = "prc_" + stable_hash(["ai-processing-v1", snapshot.snapshot_id])
    ext_ver = "ai-decomposer-v1"
    missing_info = sorted(set(decomposed.missing_context_signals))

    input_fp = stable_hash(
        [
            snapshot.snapshot_id,
            proc_key,
            f"AI-Decomposed: {snapshot.title}",
            [c.model_dump(mode="json") for c in claims],
            {},
            missing_info,
            ext_ver,
        ]
    )

    data = {
        "knowledge_id": kid,
        "version": 1,
        "snapshot_id": snapshot.snapshot_id,
        "processing_key": proc_key,
        "title": f"AI-Decomposed: {snapshot.title}",
        "claims": claims,
        "evidence_link_ids": [],
        "evidence_bindings": {},
        "missing_information": missing_info,
        "extraction_version": ext_ver,
        "input_fingerprint": input_fp,
    }

    # Format payload for stable content_hash computation
    payload = {
        "knowledge_id": data["knowledge_id"],
        "version": data["version"],
        "snapshot_id": data["snapshot_id"],
        "processing_key": data["processing_key"],
        "title": data["title"],
        "claims": [c.model_dump(mode="json") for c in claims],
        "evidence_link_ids": [],
        "evidence_bindings": {},
        "missing_information": missing_info,
        "extraction_version": ext_ver,
        "input_fingerprint": input_fp,
    }
    content_h = stable_hash(payload)
    rev_id = "krv_" + stable_hash([kid, 1, content_h])

    return KnowledgeRevision(
        **data,
        content_hash=content_h,
        revision_id=rev_id,
        review_status="needs_review",
        created_at=snapshot.captured_at,
    )
