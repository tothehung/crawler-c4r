"""Strict engine subprocess adapter. Annotates evidence without changing identity."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.models.knowledge_contract import CodeEvidence


class EngineValidationError(RuntimeError):
    """Infrastructure/protocol error; evidence must remain unchanged and retryable."""


class Diagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    snippet_line: int | None = None
    column: int | None = None


class FunctionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_name: str
    function_name: str
    function_signature: str | None = None
    selector_4byte: str | None = Field(default=None, pattern=r"^0x[0-9a-f]{8}$")
    snippet_start_line: int = Field(ge=1)
    snippet_end_line: int = Field(ge=1)
    source_start_line: int | None = None
    source_end_line: int | None = None


class EngineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal["1.0"]
    evidence_id: str
    input_sha256: str
    parser_version: str
    syntax_status: Literal["parsed", "invalid", "insufficient_context"]
    solidity_pragma: str | None = None
    contracts: list[str]
    functions: list[FunctionMetadata]
    diagnostics: list[Diagnostic]


class EngineValidator:
    def __init__(self, executable: Path, *, timeout: float = 30):
        self.executable = Path(executable).resolve(strict=True)
        if not self.executable.is_file() or not 0 < timeout <= 300:
            raise ValueError("Engine executable and timeout in (0, 300] required")
        self.timeout = timeout
        with self.executable.open("rb") as stream:
            self.binary_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        info = self._call(["validate-evidence", "--info"])
        if (
            info.get("protocol_version") != "1.0"
            or not isinstance(info.get("parser_version"), str)
            or not info["parser_version"]
        ):
            raise EngineValidationError("Unsupported engine evidence protocol")
        self.engine_parser_version = info["parser_version"]
        self.parser_version = (
            self.engine_parser_version + "/binary-sha256:" + self.binary_hash
        )

    def _call(self, arguments: list[str], payload: dict | None = None) -> dict:
        try:
            result = subprocess.run(
                [str(self.executable), *arguments],
                input=(
                    json.dumps(payload, ensure_ascii=False)
                    if payload is not None
                    else None
                ),
                encoding="utf-8",
                capture_output=True,
                timeout=self.timeout,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EngineValidationError(
                f"Engine process failed: {type(exc).__name__}"
            ) from exc
        if result.returncode:
            raise EngineValidationError(
                f"Engine exit {result.returncode}: {result.stderr[:1000]}"
            )
        if len(result.stdout) > 8_000_000:
            raise EngineValidationError("Engine response exceeds size limit")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise EngineValidationError("Engine returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise EngineValidationError("Engine response must be an object")
        return data

    def validate(self, evidence: CodeEvidence) -> tuple[CodeEvidence, EngineResult]:
        text = evidence.normalized_snippet
        if len(text.encode("utf-8")) > 2_000_000:
            raise EngineValidationError("Evidence exceeds engine input limit")
        # Line offsets are meaningful only for unmodified, contiguous source.
        source_start = 0
        if (
            evidence.source_range
            and not evidence.transformations
            and text == evidence.raw_snippet
        ):
            expected_lines = (
                evidence.source_range.end_line - evidence.source_range.start_line + 1
            )
            if len(text.splitlines()) != expected_lines:
                raise EngineValidationError(
                    "Evidence source range does not match snippet line count"
                )
            source_start = evidence.source_range.start_line
        request = {
            "evidence_id": evidence.evidence_id,
            "content": text,
            "path": evidence.path or "Evidence.sol",
            "fragment": evidence.origin_kind != "gist",
            "source_start_line": source_start,
        }
        try:
            result = EngineResult.model_validate(
                self._call(["validate-evidence"], request)
            )
        except ValidationError as exc:
            raise EngineValidationError(
                "Engine response violates the validation contract"
            ) from exc
        if (
            result.evidence_id != evidence.evidence_id
            or result.input_sha256 != hashlib.sha256(text.encode("utf-8")).hexdigest()
            or result.parser_version != self.engine_parser_version
        ):
            raise EngineValidationError(
                "Engine response does not match evidence or parser version"
            )
        for fn in result.functions:
            if (
                fn.snippet_end_line < fn.snippet_start_line
                or fn.snippet_end_line > len(text.splitlines())
            ):
                raise EngineValidationError("Engine function range exceeds snippet")
            if source_start:
                if (
                    fn.source_start_line != source_start + fn.snippet_start_line - 1
                    or fn.source_end_line != source_start + fn.snippet_end_line - 1
                ):
                    raise EngineValidationError("Engine source mapping is inconsistent")
            elif fn.source_start_line is not None or fn.source_end_line is not None:
                raise EngineValidationError("Engine invented a source range")
        metadata = {
            "contract_name": None,
            "function_name": None,
            "function_signature": None,
            "selector_4byte": None,
        }
        if result.syntax_status == "parsed":
            if len(result.contracts) == 1:
                metadata["contract_name"] = result.contracts[0]
            if len(result.functions) == 1:
                fn = result.functions[0]
                metadata.update(
                    contract_name=fn.contract_name,
                    function_name=fn.function_name,
                    function_signature=fn.function_signature,
                    selector_4byte=fn.selector_4byte,
                )
        diagnostics = [d.model_dump(exclude_none=True) for d in result.diagnostics]
        if len(result.functions) > 1:
            diagnostics.append(
                {
                    "code": "multiple_functions",
                    "message": "Evidence contains multiple functions; scalar function metadata remains null.",
                }
            )
        row = (
            evidence.model_dump()
            | metadata
            | {
                "syntax_status": result.syntax_status,
                "parser_version": self.parser_version,
                "solidity_pragma": result.solidity_pragma,
                "diagnostics": [
                    json.dumps(d, ensure_ascii=False, sort_keys=True)
                    for d in diagnostics
                ],
            }
        )
        return CodeEvidence.model_validate(row), result


def validate_batch(
    store, validator: EngineValidator, *, after: str = "", limit: int = 100
) -> dict:
    """CAS annotation only. A timeout/protocol error never masquerades as invalid code."""
    rows = store.evidence(after=after, limit=limit)
    results = []
    for row in rows:
        evidence = CodeEvidence.model_validate(row)
        if (
            evidence.parser_version == validator.parser_version
            and evidence.syntax_status != "not_checked"
        ):
            results.append(
                {
                    "evidence_id": evidence.evidence_id,
                    "action": "skipped",
                    "syntax_status": evidence.syntax_status,
                }
            )
            continue
        try:
            annotated, detail = validator.validate(evidence)
            with store.transaction() as tx:
                current = tx.get("code_evidence", evidence.evidence_id)
                if current != evidence.model_dump(mode="json"):
                    raise EngineValidationError(
                        "Concurrent annotation changed; retry from fresh state"
                    )
                tx.put("code_evidence", annotated.model_dump(mode="json"))
            results.append(
                {
                    "evidence_id": evidence.evidence_id,
                    "action": "validated",
                    "syntax_status": annotated.syntax_status,
                    "detail": detail.model_dump(exclude_none=True),
                }
            )
        except EngineValidationError as exc:
            results.append(
                {
                    "evidence_id": evidence.evidence_id,
                    "action": "error",
                    "error": str(exc),
                }
            )
    return {
        "parser_version": validator.parser_version,
        "next_after": rows[-1]["evidence_id"] if rows else None,
        "validated": sum(row["action"] == "validated" for row in results),
        "skipped": sum(row["action"] == "skipped" for row in results),
        "errors": sum(row["action"] == "error" for row in results),
        "results": results,
    }
