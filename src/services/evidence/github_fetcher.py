from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://github.com"
DEFAULT_RAW_BASE_URL = "https://raw.githubusercontent.com"
DEFAULT_API_BASE_URL = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0


class GitHubFetchError(Exception):
    pass


class RefNotFoundError(GitHubFetchError):
    pass


class PathNotFoundError(GitHubFetchError):
    pass


@dataclass(frozen=True)
class DiffHunk:
    path: str
    removed_lines: list[str]
    added_lines: list[str]
    removed_start: int | None = None
    added_start: int | None = None


@dataclass(frozen=True)
class DiffResult:
    commit_sha: str | None
    hunks: list[DiffHunk]

    def hunks_for_paths(self, paths: list[str]) -> list[DiffHunk]:
        if not paths:
            return self.hunks
        lowered = [p.lower() for p in paths]
        return [h for h in self.hunks if h.path.lower() in lowered]


@dataclass
class _CacheEntry:
    etag: str | None
    content: str


@dataclass
class GitHubFetcher:
    token: str | None = None
    base_url: str = DEFAULT_BASE_URL
    raw_base_url: str = DEFAULT_RAW_BASE_URL
    api_base_url: str = DEFAULT_API_BASE_URL
    timeout: float = DEFAULT_TIMEOUT
    http_client: httpx.Client | None = None
    _etag_cache: dict[str, _CacheEntry] = field(default_factory=dict)

    def resolve_ref_sha(self, repo: str, ref: str) -> str:
        owner, name = _split_repo(repo)
        url = f"{self.api_base_url}/repos/{owner}/{name}/commits/{ref}"
        data = self._get_json(url)
        sha = data.get("sha")
        if not isinstance(sha, str):
            raise RefNotFoundError(f"Cannot resolve ref '{ref}' of {repo}")
        return sha

    def fetch_file(self, repo: str, ref: str, path: str) -> str:
        owner, name = _split_repo(repo)
        url = f"{self.raw_base_url}/{owner}/{name}/{ref}/{path.lstrip('/')}"
        return self._get_text(url)

    def fetch_commit_diff(self, repo: str, commit_sha: str) -> DiffResult:
        owner, name = _split_repo(repo)
        url = f"{self.base_url}/{owner}/{name}/commit/{commit_sha}.diff"
        body = self._get_text(url)
        return DiffResult(commit_sha=commit_sha, hunks=parse_diff(body))

    def fetch_pull_request_diff(self, repo: str, pull_number: int) -> DiffResult:
        owner, name = _split_repo(repo)
        url = f"{self.base_url}/{owner}/{name}/pull/{pull_number}.diff"
        body = self._get_text(url)
        return DiffResult(commit_sha=None, hunks=parse_diff(body))

    def _client(self) -> httpx.Client:
        if self.http_client is None:
            self.http_client = httpx.Client(timeout=self.timeout)
        return self.http_client

    def _headers(self, *, raw_etag_cache_key: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {"User-Agent": "w3goaudit-crawler"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        entry = self._etag_cache.get(raw_etag_cache_key or "")
        if entry and entry.etag:
            headers["If-None-Match"] = entry.etag
        return headers

    def _request_text(self, url: str, cacheable: bool = True) -> str:
        cache_key = url if cacheable else ""
        response = self._client().get(
            url, headers=self._headers(raw_etag_cache_key=cache_key)
        )

        if response.status_code == 304 and (entry := self._etag_cache.get(cache_key)):
            logger.debug("ETag cache hit for %s", url)
            return entry.content

        if response.status_code == 404:
            raise PathNotFoundError(f"Not found: {url}")
        if response.status_code == 301:
            raise GitHubFetchError(f"Moved permanently: {url}")
        response.raise_for_status()

        if cacheable:
            etag = response.headers.get("ETag")
            self._etag_cache[url] = _CacheEntry(etag=etag, content=response.text)

        return response.text

    def _get_text(self, url: str) -> str:
        try:
            return self._request_text(url)
        except httpx.HTTPStatusError as exc:
            raise GitHubFetchError(f"HTTP error fetching {url}: {exc}") from exc

    def _get_json(self, url: str) -> dict[str, Any]:
        text = self._get_text(url)
        data = json.loads(text)
        if not isinstance(data, dict):
            raise GitHubFetchError(f"Unexpected JSON payload from {url}")
        return data


def _split_repo(repo: str) -> tuple[str, str]:
    parts = repo.strip("/").split("/")
    if len(parts) != 2:
        raise GitHubFetchError(f"Invalid repository identifier: '{repo}'")
    return parts[0], parts[1]


def parse_diff(diff_body: str) -> list[DiffHunk]:
    hunks: list[DiffHunk] = []
    current_path: str | None = None
    current: DiffHunk | None = None
    old_line = 0
    new_line = 0

    hunk_header_pattern = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")

    for line in diff_body.split("\n"):
        if line.startswith("diff --git"):
            current_path = None
            current = None
            continue

        if line.startswith(("--- ", "+++ ")):
            marker_path = line[4:].split("\t")[0].strip()
            if marker_path.startswith(("a/", "b/")):
                marker_path = marker_path[2:]
            if line.startswith("--- ") and marker_path != "/dev/null":
                current_path = marker_path
            elif line.startswith("+++ ") and marker_path != "/dev/null":
                current_path = current_path or marker_path
            continue

        match = hunk_header_pattern.match(line)
        if match and current_path is not None:
            current = DiffHunk(
                path=current_path,
                removed_lines=[],
                added_lines=[],
                removed_start=int(match.group(1)),
                added_start=int(match.group(2)),
            )
            hunks.append(current)
            old_line = int(match.group(1))
            new_line = int(match.group(2))
            continue

        if current is None:
            continue

        if line.startswith("-"):
            current.removed_lines.append(line[1:])
            old_line += 1
        elif line.startswith("+"):
            current.added_lines.append(line[1:])
            new_line += 1
        elif line.startswith((" ", "\n")) or line == "":
            old_line += 1
            new_line += 1

    return [h for h in hunks if h.removed_lines or h.added_lines]
