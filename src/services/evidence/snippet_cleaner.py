from __future__ import annotations

import re

LINE_NUMBER_PREFIX_PATTERN = re.compile(r"^\s*(?:L?\d+\s*[:|]|\d+\s*\|)\s?")

DIFF_HEADER_PATTERN = re.compile(r"^(?:diff --git|index |--- |\+\+\+ |@@ )")

ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def clean(snippet: str) -> str:
    lines = snippet.replace("\r\n", "\n").split("\n")
    cleaned: list[str] = []
    is_diff = any(DIFF_HEADER_PATTERN.match(line) for line in lines)

    for line in lines:
        line = ANSI_ESCAPE_PATTERN.sub("", line)
        line = LINE_NUMBER_PREFIX_PATTERN.sub("", line)

        if DIFF_HEADER_PATTERN.match(line):
            continue

        if is_diff and line.startswith("-"):
            continue
        if is_diff and line.startswith(" "):
            line = line[1:]

        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            line = line[1:]

        cleaned.append(line.rstrip())

    text = "\n".join(cleaned)
    return text.strip("\n") + "\n" if text.strip() else ""
