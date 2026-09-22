from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://code4rena.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Code4renaContest:
    slug: str
    title: str
    sponsor: str | None = None
    date: str | None = None
    findings_url: str | None = None
    contest_id: str | None = None
    alt_url: str | None = None


class HTMLToMarkdownConverter(HTMLParser):
    """Converts HTML content inside Code4rena audit reports to clean Markdown."""

    def __init__(self) -> None:
        super().__init__()
        self.result: list[str] = []
        self.in_code_block = False
        self.code_lang = ""
        self.code_lines: list[str] = []
        self.in_link = False
        self.link_href = ""
        self.link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "pre":
            self.in_code_block = True
            self.code_lang = attrs_dict.get("data-language") or ""
            self.code_lines = []
        elif tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(tag[1])
            self.result.append(f"\n\n{'#' * level} ")
        elif tag in ["p", "div"]:
            self.result.append("\n\n")
        elif tag == "br":
            self.result.append("\n")
        elif tag == "li":
            self.result.append("\n- ")
        elif tag == "code" and not self.in_code_block:
            self.result.append("`")
        elif tag == "a":
            self.in_link = True
            self.link_href = attrs_dict.get("href") or ""
            self.link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre":
            self.in_code_block = False
            code_content = "".join(self.code_lines).strip("\r\n")
            self.result.append(f"\n```{self.code_lang}\n{code_content}\n```\n")
            self.code_lines = []
        elif tag == "code" and not self.in_code_block:
            self.result.append("`")
        elif tag == "a":
            self.in_link = False
            text = "".join(self.link_text).strip()
            if self.link_href and text and not self.link_href.startswith("#"):
                self.result.append(f"[{text}]({self.link_href})")
            else:
                self.result.append(text)
            self.link_text = []

    def handle_data(self, data: str) -> None:
        if self.in_code_block:
            self.code_lines.append(data)
        elif self.in_link:
            self.link_text.append(data)
        else:
            self.result.append(data)

    def get_markdown(self) -> str:
        raw = "".join(self.result)
        clean = re.sub(r"\n{3,}", "\n\n", raw).strip()
        return clean


class Code4renaClient:
    """HTTP client and parser for Code4rena contest audit reports."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        request_delay_seconds: float = 0.5,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.request_delay_seconds = request_delay_seconds
        self.client = httpx.Client(
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            timeout=timeout_seconds,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> Code4renaClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def fetch_all_contests(self) -> list[Code4renaContest]:
        """Fetch the full list of official audit contest reports from https://code4rena.com/reports."""
        url = f"{self.base_url}/reports"
        logger.info("Fetching Code4rena contest reports list from %s", url)
        response = self._get_with_retry(url)
        html_text = response.text
        return self.parse_contests_from_html(html_text)

    @classmethod
    def parse_contests_from_html(cls, html_text: str) -> list[Code4renaContest]:
        """Parse contest objects embedded in the Code4rena /reports HTML page."""
        # Find all JSON-like definitions of contests
        # Pattern captures: {"alt_url":..., "slug":"...", "title":"...", ...}
        # In Next.js App Router HTML, quotes are escaped as \"
        raw_slugs = re.findall(r'\\\"slug\\\":\\\"([^\\\"]+)\\\"', html_text)
        if not raw_slugs:
            # Try unescaped
            raw_slugs = re.findall(r'"slug":"([^"]+)"', html_text)

        unique_slugs = list(dict.fromkeys(raw_slugs))
        logger.info("Found %d unique contest slugs in reports page", len(unique_slugs))

        contests: list[Code4renaContest] = []
        for slug in unique_slugs:
            # Extract attributes associated with this slug
            # Look for block containing slug
            pattern = rf'\{{[^{{}}]*?(?:\\\"slug\\\"|"slug")\s*:\s*(?:\\\"{re.escape(slug)}\\\"|"{re.escape(slug)}")[^{{}}]*?\}}'
            match = re.search(pattern, html_text)
            title = slug
            sponsor = None
            date_str = None
            findings_url = None
            contest_id = None
            alt_url = None

            if match:
                block = match.group(0)
                # Unescape for clean regex matching
                clean_block = block.replace(r'\"', '"').replace(r"\\", "\\")

                m_title = re.search(r'"title"\s*:\s*"([^"]+)"', clean_block)
                if m_title:
                    title = m_title.group(1)

                m_sponsor = re.search(r'"sponsor"\s*:\s*"([^"]+)"', clean_block)
                if m_sponsor:
                    sponsor = m_sponsor.group(1)

                m_date = re.search(r'"date"\s*:\s*"([^"]+)"', clean_block)
                if m_date:
                    date_str = m_date.group(1)

                m_findings = re.search(r'"findings"\s*:\s*"([^"]+)"', clean_block)
                if m_findings:
                    findings_url = m_findings.group(1)

                m_cid = re.search(r'"contest"\s*:\s*(\d+)', clean_block)
                if m_cid:
                    contest_id = m_cid.group(1)

                m_alt = re.search(r'"alt_url"\s*:\s*"([^"]+)"', clean_block)
                if m_alt:
                    alt_url = m_alt.group(1)

            contests.append(
                Code4renaContest(
                    slug=slug,
                    title=title,
                    sponsor=sponsor,
                    date=date_str,
                    findings_url=findings_url,
                    contest_id=contest_id,
                    alt_url=alt_url,
                )
            )

        return contests

    def fetch_report_findings(
        self,
        contest: Code4renaContest,
    ) -> list[dict[str, Any]]:
        """Fetch and extract all findings from a contest audit report page."""
        url = f"{self.base_url}/reports/{contest.slug}"
        logger.info("Fetching report findings for contest %s from %s", contest.slug, url)
        if self.request_delay_seconds > 0:
            time.sleep(self.request_delay_seconds)

        response = self._get_with_retry(url)
        return self.parse_report_findings_from_html(response.text, contest)

    @classmethod
    def parse_report_findings_from_html(
        cls,
        html_text: str,
        contest: Code4renaContest,
    ) -> list[dict[str, Any]]:
        """Parse individual findings from the HTML of a contest report page."""
        # Locate the report contents section
        start_idx = html_text.find('<div class="report-contents markdown-body">')
        if start_idx == -1:
            start_idx = html_text.find('class="report-contents')
        if start_idx == -1:
            start_idx = 0

        end_idx = html_text.find("</main>", start_idx)
        if end_idx == -1:
            end_idx = len(html_text)

        report_html = html_text[start_idx:end_idx]

        # Break report into sections by H1 / H2
        # Example H1: <h1 id="medium-risk-findings-3" ...>Medium Risk Findings (3)</h1>
        # Example H2: <h2 id="m-01-..." ...><a href="...">[M-01] Title</a></h2>
        header_regex = re.compile(
            r'<(h[12])\s+id="([^"]+)"[^>]*>(.*?)</\1>',
            re.DOTALL | re.IGNORECASE,
        )

        matches = list(header_regex.finditer(report_html))
        if not matches:
            return []

        findings: list[dict[str, Any]] = []
        current_section_severity: str | None = None

        for idx, match in enumerate(matches):
            tag = match.group(1).lower()
            header_id = match.group(2)
            header_content = match.group(3)

            # Strip inner HTML from header text
            clean_header_text = re.sub(r"<[^>]+>", "", header_content).strip()

            # End of this section is the start of next section
            content_start = match.end()
            content_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(report_html)
            section_html = report_html[content_start:content_end]

            # Check if this header represents a category (e.g. High Risk Findings, Gas Optimizations)
            section_severity = cls._detect_category_severity(header_id, clean_header_text)
            if section_severity:
                current_section_severity = section_severity
                continue

            # Determine if this header represents an individual finding
            finding_severity = cls._detect_finding_severity(
                header_id, clean_header_text, current_section_severity
            )
            if not finding_severity:
                continue

            # Extract GitHub issue link if present in header
            github_link = ""
            m_gh = re.search(r'href="(https://github\.com/[^"]+)"', header_content)
            if m_gh:
                github_link = m_gh.group(1)
            elif contest.findings_url:
                github_link = contest.findings_url

            # Extract wardens / authors from the introductory lines of section_html
            finders, wardens = cls._extract_finders(section_html)

            # Convert body to Markdown
            converter = HTMLToMarkdownConverter()
            converter.feed(section_html)
            markdown_content = converter.get_markdown()

            # Extract report date
            parsed_report_date: date | None = None
            if contest.date:
                try:
                    parsed_report_date = datetime.strptime(
                        contest.date.strip(), "%Y-%m-%d"
                    ).date()
                except ValueError:
                    parsed_report_date = None

            # Generate stable unique ID
            slug_clean = header_id.replace(" ", "-")
            finding_id = f"c4-{contest.slug}-{slug_clean}"

            findings.append(
                {
                    "id": finding_id,
                    "kind": "MARKDOWN",
                    "auditfirm_id": "code4rena",
                    "impact": finding_severity,
                    "finders_count": len(finders),
                    "protocol_id": None,
                    "title": clean_header_text,
                    "content": markdown_content,
                    "summary": "",
                    "report_date": parsed_report_date,
                    "contest_prize_txt": "",
                    "contest_link": f"{DEFAULT_BASE_URL}/reports/{contest.slug}",
                    "sponsor_name": contest.sponsor,
                    "sponsor_link": "",
                    "quality_score": 0.0,
                    "general_score": 0.0,
                    "source_link": github_link or f"{DEFAULT_BASE_URL}/reports/{contest.slug}#{header_id}",
                    "github_link": github_link,
                    "pdf_link": "",
                    "pdf_page_from": 0,
                    "contest_id": contest.contest_id or "",
                    "slug": f"{contest.slug}-{slug_clean}",
                    "firm_name": "Code4rena",
                    "firm_logo_square": "https://code4rena.com/logos/c4/c4-logo.svg",
                    "protocol_name": contest.sponsor or contest.title,
                    "bookmarked": False,
                    "read": False,
                    "issues_issue_finders": [
                        {"wardens_warden": {"handle": h}} for h in finders
                    ],
                    "auditfirms_auditfirm": {
                        "name": "Code4rena",
                        "logo_square": "https://code4rena.com/logos/c4/c4-logo.svg",
                    },
                    "protocols_protocol": {
                        "name": contest.sponsor or contest.title,
                        "protocols_protocolcategoryscore": [],
                    },
                    "issues_issuetagscore": [],
                }
            )

        return findings

    @staticmethod
    def _detect_category_severity(header_id: str, title: str) -> str | None:
        """Detect category-level severity from H1/H2 category headings."""
        hid = header_id.lower()
        t = title.lower()

        if "high risk" in hid or "high risk" in t or "high severity" in t:
            return "HIGH"
        if "medium risk" in hid or "medium risk" in t or "medium severity" in t:
            return "MEDIUM"
        if "low risk" in hid or "low risk" in t:
            return "LOW"
        if "non-critical" in hid or "non-critical" in t or "informational" in t:
            return "INFORMATIONAL"
        if "gas optimization" in hid or "gas optimization" in t or "gas optimizations" in t:
            return "GAS"
        return None

    @staticmethod
    def _detect_finding_severity(
        header_id: str,
        title: str,
        current_section_severity: str | None,
    ) -> str | None:
        """Determine severity for an individual finding."""
        hid = header_id.lower()
        t = title.upper()

        # Check explicit prefix in title or header_id
        if re.search(r"\[H-\d+\]", t) or hid.startswith("h-"):
            return "HIGH"
        if re.search(r"\[M-\d+\]", t) or hid.startswith("m-"):
            return "MEDIUM"
        if re.search(r"\[L-\d+\]", t) or hid.startswith("l-"):
            return "LOW"
        if (
            re.search(r"\[N-\d+\]", t)
            or re.search(r"\[I-\d+\]", t)
            or hid.startswith("n-")
            or hid.startswith("i-")
        ):
            return "INFORMATIONAL"
        if re.search(r"\[G-\d+\]", t) or hid.startswith("g-"):
            return "GAS"

        # Check skip list (non-finding headers)
        skip_headers = [
            "overview",
            "about-c4",
            "wardens",
            "summary",
            "scope",
            "severity-criteria",
            "disclosures",
            "gasreport",
            "low-risk-and-non-critical-issues",
            "gas-optimizations-summary",
            "low-risk-issues",
            "non-critical-issues",
        ]
        if hid in skip_headers:
            return None

        # Fallback to current section severity if inside a findings section
        return current_section_severity

    @staticmethod
    def _extract_finders(section_html: str) -> tuple[list[str], list[str]]:
        """Extract wardens from 'Submitted by [author], also found by ...' line."""
        finders: list[str] = []
        wardens: list[str] = []

        # Find submitted line
        m_sub = re.search(
            r"Submitted by (.*?)(?:</p>|\n\n)",
            section_html,
            re.DOTALL | re.IGNORECASE,
        )
        if not m_sub:
            return finders, wardens

        line_html = m_sub.group(1)
        # Extract names from <a> tags
        links = re.findall(r">([^<]+)</a>", line_html)
        seen = set()
        for name in links:
            clean_name = name.strip()
            if clean_name and clean_name not in seen:
                finders.append(clean_name)
                seen.add(clean_name)

        if not finders:
            # Fallback to plain text comma split
            plain = re.sub(r"<[^>]+>", "", line_html)
            plain = re.sub(r"also found by|,|and", " ", plain)
            for token in plain.split():
                clean_token = token.strip().strip(".,()")
                if clean_token and clean_token not in seen:
                    finders.append(clean_token)
                    seen.add(clean_token)

        return finders, wardens

    def _get_with_retry(self, url: str, max_retries: int = 3) -> httpx.Response:
        """Execute HTTP GET with exponential backoff on failure."""
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.get(url)
                response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                logger.warning(
                    "Attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                    attempt,
                    max_retries,
                    url,
                    exc,
                    delay,
                )
                if attempt == max_retries:
                    break
                time.sleep(delay)
                delay *= 2

        raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_exc}") from last_exc
