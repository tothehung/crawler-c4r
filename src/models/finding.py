from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Warden(BaseModel):
    model_config = ConfigDict(extra="ignore")

    handle: str | None = None


class IssueFinder(BaseModel):
    model_config = ConfigDict(extra="ignore")

    wardens_warden: Warden | None = None


class AuditFirm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    logo_square: str | None = None


class Protocol(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    protocols_protocolcategoryscore: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("protocols_protocolcategoryscore", mode="before")
    @classmethod
    def none_category_scores_to_empty_list(cls, value: Any) -> Any:
        if value is None:
            return []
        return value


class Finding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    kind: str | None = None
    auditfirm_id: str | None = None
    impact: str | None = None
    finders_count: int = 0
    protocol_id: str | None = None
    title: str
    content: str = ""
    summary: str = ""
    report_date: date | None = None
    contest_prize_txt: str = ""
    contest_link: str = ""
    sponsor_name: str | None = None
    sponsor_link: str = ""
    quality_score: float = 0
    general_score: float = 0
    source_link: str = ""
    github_link: str = ""
    pdf_link: str = ""
    pdf_page_from: int = 0
    contest_id: str = ""
    slug: str
    firm_name: str | None = None
    firm_logo_square: str | None = None
    protocol_name: str | None = None
    bookmarked: bool = False
    read: bool = False
    issues_issue_finders: list[IssueFinder] = Field(default_factory=list)
    auditfirms_auditfirm: AuditFirm | None = None
    protocols_protocol: Protocol | None = None
    issues_issuetagscore: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("report_date", mode="before")
    @classmethod
    def empty_report_date_object_to_none(cls, value: Any) -> Any:
        if value == {}:
            return None
        return value

    @field_validator(
        "content",
        "summary",
        "contest_prize_txt",
        "contest_link",
        "sponsor_link",
        "source_link",
        "github_link",
        "pdf_link",
        "contest_id",
        mode="before",
    )
    @classmethod
    def none_string_to_empty_string(cls, value: Any) -> Any:
        if value is None:
            return ""
        return value

    @field_validator("impact", mode="before")
    @classmethod
    def normalize_impact(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized.upper() if normalized else None
        return value

    @field_validator("finders_count", "pdf_page_from", mode="before")
    @classmethod
    def empty_int_to_zero(cls, value: Any) -> Any:
        if value is None or value == "":
            return 0
        return value

    @field_validator("quality_score", "general_score", mode="before")
    @classmethod
    def empty_float_to_zero(cls, value: Any) -> Any:
        if value is None or value == "":
            return 0
        return value

    @field_validator("bookmarked", "read", mode="before")
    @classmethod
    def none_bool_to_false(cls, value: Any) -> Any:
        if value is None:
            return False
        return value

    @field_validator(
        "issues_issue_finders",
        "issues_issuetagscore",
        mode="before",
    )
    @classmethod
    def none_list_to_empty_list(cls, value: Any) -> Any:
        if value is None:
            return []
        return value
