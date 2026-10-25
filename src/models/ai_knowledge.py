"""Pydantic schema for AI-driven finding decomposition into structured security knowledge."""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class GroundedItem(BaseModel):
    """A claim or statement coupled with an exact quote from the report to prevent hallucination."""
    statement: str = Field(
        ...,
        description="Nội dung phân tích hoặc nhận định bảo mật của AI.",
    )
    quote_from_report: str = Field(
        ...,
        description="Đoạn trích dẫn nguyên văn ngắn từ bài viết gốc làm căn cứ đối soát.",
    )


class AIDecomposedFinding(BaseModel):
    """The complete 8-facet structured security knowledge schema requested by the advisor."""

    finding_id: str = Field(
        ...,
        description="Định danh duy nhất của finding nguồn.",
    )
    vulnerability_category: str = Field(
        ...,
        description="Phân loại lỗ hổng bảo mật (VD: Integer Truncation, Missing Access Control, Reentrancy).",
    )
    suspicious_pattern: GroundedItem = Field(
        ...,
        description="Mẫu code hoặc hành vi đáng ngờ nhận diện được trên mã nguồn.",
    )
    necessary_condition: GroundedItem = Field(
        ...,
        description="Điều kiện cần: Thuộc tính tĩnh về kiểu dữ liệu hoặc cấu trúc hàm khiến code rơi vào diện nghi vấn.",
    )
    sufficient_condition: GroundedItem = Field(
        ...,
        description="Điều kiện đủ: Tình trạng runtime cho phép giá trị vượt ngoài giả định an toàn và trở thành lỗi thực sự.",
    )
    trigger_condition: GroundedItem = Field(
        ...,
        description="Điều kiện kích hoạt: Kịch bản hoặc giao dịch cụ thể để khai thác lỗi tại runtime.",
    )
    verification_checklist: List[str] = Field(
        ...,
        min_length=2,
        description="Danh sách 3-5 câu hỏi Yes/No để auditor hoặc AI Agent kiểm tra trên hợp đồng mới.",
    )
    verification_method: str = Field(
        ...,
        description="Cách thức kiểm chứng tính đúng đắn của lỗi (VD: Viết test case PoC, invariant testing).",
    )
    remediation: GroundedItem = Field(
        ...,
        description="Cách khắc phục và giải pháp sửa lỗi chuẩn xác.",
    )
    missing_context_signals: List[str] = Field(
        default_factory=list,
        description="Các ngữ cảnh còn thiếu nếu chỉ nhìn vào đoạn code cục bộ (VD: thiếu caller, thiếu modifier).",
    )
