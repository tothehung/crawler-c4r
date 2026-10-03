from src.services.evidence.dedup import Deduplicator, evidence_fingerprint
from src.services.evidence.github_fetcher import (
    DiffHunk,
    DiffResult,
    GitHubFetchError,
    GitHubFetcher,
    PathNotFoundError,
    RefNotFoundError,
    parse_diff,
)
from src.services.evidence.pipeline import (
    EvidencePipeline,
    EvidencePipelineResult,
)
from src.services.evidence.scan_body import ScanResult, scan
from src.services.evidence.snippet_cleaner import clean
from src.services.evidence.validator import (
    ValidationResult,
    expand_window,
    locate_symbol,
    looks_like_solidity,
    repair_by_wrapping,
    validate,
)

__all__ = [
    "DiffHunk",
    "DiffResult",
    "Deduplicator",
    "EvidencePipeline",
    "EvidencePipelineResult",
    "GitHubFetchError",
    "GitHubFetcher",
    "PathNotFoundError",
    "RefNotFoundError",
    "ScanResult",
    "ValidationResult",
    "clean",
    "evidence_fingerprint",
    "expand_window",
    "locate_symbol",
    "looks_like_solidity",
    "parse_diff",
    "repair_by_wrapping",
    "scan",
    "validate",
]
