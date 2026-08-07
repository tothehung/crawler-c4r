from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.models.finding import Finding


class ResponseMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    totalResults: int
    currentPage: int
    pageSize: int
    totalPages: int
    elapsed: float


class RateLimit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    limit: int
    remaining: int
    reset: int


class FindingsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    findings: list[Finding]
    metadata: ResponseMetadata
    rateLimit: RateLimit
