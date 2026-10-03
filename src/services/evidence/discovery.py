"""Markdown AST discovery. Locations describe report nodes, never source lines."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

URL = re.compile(r"https?://[^\s<>\"`]+")
RANGE = re.compile(r"L{1,2}(\d+)(?:C\d+)?(?:-L?(\d+)(?:C\d+)?)?$")
SIGNALS = re.compile(
    r"\b(?:pragma\s+solidity|(?:contract|interface|library)\s+\w+|function\s+\w+\s*\([^)]*\)\s*(?:public|external|internal|private)|mapping\s*\(|uint\d*\b|address\s+\w+|require\s*\()"
)
TRACE = re.compile(
    r"(?m)^\s*(?:\[PASS\]|\[FAIL|Traces:|Suite result:|Ran \d+ test|[│├└]─|[│ ]*\[\d+\]\s+\w+::)"
)


@dataclass(frozen=True)
class Candidate:
    kind: str
    locator: str
    url: str | None = None
    snippet: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    role: str = "unknown"
    role_basis: str | None = None
    context: str = ""


def url_kind(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.username or parsed.password or port:
        return None
    parts = unquote(parsed.path).strip("/").split("/")
    if any(part in {".", "..", ""} for part in parts) or "\\" in parsed.path:
        return None
    host = parsed.hostname
    if host in {"github.com", "www.github.com", "raw.githubusercontent.com"} and (
        len(parts) < 2
        or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts[:2])
    ):
        return None
    if host in {"github.com", "www.github.com"} and len(parts) >= 4:
        if parts[2] in {"blob", "tree"} and parts[-1].lower().endswith(".sol"):
            return "github_file"
        if parts[2] == "commit" and re.fullmatch(
            r"[0-9a-fA-F]{7,40}(?:\.diff|\.patch)?", parts[3]
        ):
            return "github_diff"
        if parts[2] == "pull" and re.fullmatch(r"\d+(?:\.diff|\.patch)?", parts[3]):
            return "github_diff"
    if (
        host == "raw.githubusercontent.com"
        and len(parts) >= 4
        and parts[-1].lower().endswith(".sol")
    ):
        return "github_file"
    if host == "gist.github.com" and 1 <= len(parts) <= 3:
        ids = parts if len(parts) == 1 else parts[1:]
        if ids and re.fullmatch(r"[0-9a-fA-F]{5,64}", ids[0]):
            return "gist"
    return None


def role_from_context(context: str) -> tuple[str, str | None]:
    # Assign only from report wording; never infer exploitability from code.
    for pattern, role in [
        (
            r"(?i)\b(?:recommended mitigation|recommendation|remediation|fixed code|proposed fix|fixed by|fixed in)\b",
            "fix",
        ),
        (r"(?i)\b(?:proof of concept|proof-of-concept|poc|test file)\b", "poc"),
        (r"(?i)\bvulnerable code\b", "vulnerable"),
    ]:
        match = re.search(pattern, context)
        if match:
            return role, f"Report wording: {match.group(0)}"
    return "unknown", None


def discover(body: str, *, metadata_urls: list[str] | None = None) -> list[Candidate]:
    tokens = MarkdownIt("commonmark", {"html": False}).parse(body)
    candidates = []
    seen = set()
    heading = ""
    preceding = ""

    def add_url(url: str, locator: str, context: str):
        url = url.rstrip(".,;)")
        kind = url_kind(url)
        if not kind or url in seen:
            return
        seen.add(url)
        anchor = RANGE.fullmatch(urlsplit(url).fragment)
        start = int(anchor[1]) if anchor else None
        end = int(anchor[2] or anchor[1]) if anchor else None
        role, basis = role_from_context(context)
        candidates.append(
            Candidate(
                kind,
                locator,
                url=url,
                start_line=start,
                end_line=end,
                role=role,
                role_basis=basis,
                context=context[-1000:],
            )
        )

    for index, token in enumerate(tokens):
        line = token.map[0] + 1 if token.map else 0
        if token.type == "inline":
            if index and tokens[index - 1].type == "heading_open":
                heading = token.content
                preceding = ""
            context = heading + "\n" + token.content
            for child_index, child in enumerate(token.children or []):
                if child.type == "link_open":
                    add_url(
                        child.attrGet("href") or "",
                        f"body:line:{line}:link:{child_index}",
                        context,
                    )
                elif child.type == "text":
                    for number, match in enumerate(URL.finditer(child.content)):
                        add_url(
                            match[0],
                            f"body:line:{line}:text:{child_index}:url:{number}",
                            context,
                        )
            preceding = token.content[-600:]
        elif token.type in {"fence", "code_block"}:
            snippet = token.content
            if not snippet.strip() or TRACE.search(snippet):
                continue
            language = token.info.split()[0].lower() if token.info.strip() else ""
            is_diff = language == "diff" or bool(
                re.search(r"(?m)^@@ |^diff --git ", snippet)
            )
            if language not in {"solidity", "sol"} and not SIGNALS.search(snippet):
                continue
            context = heading + "\n" + preceding
            role, basis = role_from_context(context)
            candidates.append(
                Candidate(
                    "inline_diff" if is_diff else "inline",
                    f"body:line:{line}:block",
                    snippet=snippet,
                    role=role,
                    role_basis=basis,
                    context=context[-1000:],
                )
            )
            preceding = ""  # Do not carry a preceding paragraph across several blocks.
    for index, url in enumerate(metadata_urls or []):
        if url:
            add_url(url, f"metadata:url:{index}", "")
    return candidates
