from __future__ import annotations

import re
from dataclasses import dataclass

from src.models.evidence import ParseStatus

CONTRACT_PATTERN = re.compile(
    r"\b(?:abstract\s+)?(?:contract|interface|library)\s+([A-Za-z_][A-Za-z0-9_]*)"
)

FUNCTION_PATTERN = re.compile(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")

SOLIDITY_SIGNALS_PATTERN = re.compile(
    r"\b(?:pragma\s+solidity|contract\s+\w+|interface\s+\w+|library\s+\w+"
    r"|function\s+\w+\s*\(|modifier\s+\w+|mapping\s*\(|payable\b"
    r"|address\s+(?:payable\s+)?\w+|require\s*\(|emit\s+\w+)\b"
)


@dataclass(frozen=True)
class ValidationResult:
    status: ParseStatus
    contract_name: str | None = None
    function_name: str | None = None


def looks_like_solidity(snippet: str) -> bool:
    return bool(SOLIDITY_SIGNALS_PATTERN.search(snippet))


def validate(snippet: str) -> ValidationResult:
    if not snippet.strip():
        return ValidationResult(status=ParseStatus.UNRESOLVED)

    if _is_balanced(snippet) and CONTRACT_PATTERN.search(snippet):
        return ValidationResult(
            status=ParseStatus.OK,
            contract_name=_first_match(CONTRACT_PATTERN, snippet),
            function_name=_first_match(FUNCTION_PATTERN, snippet),
        )

    repaired = repair_by_wrapping(snippet)
    if repaired is not None and _is_balanced(snippet) and _is_balanced(repaired):
        return ValidationResult(
            status=ParseStatus.REPAIRED,
            contract_name=_first_match(CONTRACT_PATTERN, snippet) or None,
            function_name=_first_match(FUNCTION_PATTERN, snippet),
        )

    return ValidationResult(
        status=ParseStatus.INVALID,
        contract_name=_first_match(CONTRACT_PATTERN, snippet),
        function_name=_first_match(FUNCTION_PATTERN, snippet),
    )


def locate_symbol(
    snippet: str, symbol_hints: list[str]
) -> tuple[int | None, int | None]:
    """Locate the best (start_line, end_line) window covering a hinted symbol.

    Returns line numbers (1-based) of the enclosing function block for the
    first hint found in the snippet. Falls back to the whole snippet.
    """
    lines = snippet.split("\n")

    for hint in symbol_hints:
        function_name = hint.split(".")[-1]
        pattern = re.compile(rf"\bfunction\s+{re.escape(function_name)}\b")

        for index, line in enumerate(lines):
            if pattern.search(line):
                end = _find_block_end(lines, index)
                return index + 1, end + 1

    for hint in symbol_hints:
        contract_name = hint.split(".")[0]
        pattern = re.compile(
            rf"\b(?:contract|interface|library)\s+{re.escape(contract_name)}\b"
        )

        for index, line in enumerate(lines):
            if pattern.search(line):
                end = _find_block_end(lines, index)
                return index + 1, end + 1

    return None, None


def expand_window(
    total_lines: int,
    start_line: int,
    end_line: int,
    *,
    context: int = 10,
) -> tuple[int, int]:
    new_start = max(1, start_line - context)
    new_end = min(total_lines, end_line + context)
    return new_start, new_end


def repair_by_wrapping(snippet: str) -> str | None:
    """Wrap a fragment into a minimal compilable skeleton.

    Used when the snippet is a function/statement-level fragment cut out
    of its original contract.
    """
    stripped = snippet.strip()
    if not stripped:
        return None

    if CONTRACT_PATTERN.search(stripped):
        return None
    if not looks_like_solidity(stripped):
        return None

    return "\n".join(
        [
            "// SPDX-License-Identifier: MIT",
            "pragma solidity ^0.8.20;",
            "",
            "contract EvidenceWrapper {",
            f"{stripped}",
            "}",
        ]
    )


def _is_balanced(code: str) -> bool:
    depth = 0

    for char in _strip_comments_and_strings(code):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False

    return depth == 0


_LINE_COMMENT_PATTERN = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_PATTERN = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL_PATTERN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')


def _strip_comments_and_strings(code: str) -> str:
    code = _STRING_LITERAL_PATTERN.sub('""', code)
    code = _BLOCK_COMMENT_PATTERN.sub("", code)
    return _LINE_COMMENT_PATTERN.sub("", code)


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _find_block_end(lines: list[str], open_index: int) -> int:
    depth = 0
    opened = False

    for index in range(open_index, len(lines)):
        for char in lines[index]:
            if char == "{":
                depth += 1
                opened = True
            elif char == "}":
                depth -= 1

        if opened and depth <= 0:
            return index

    return len(lines) - 1
