"""Explicit supplementary public-source acquisition; never edits the frozen corpus."""

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests/fixtures/patterns/missing-access-control/source"
REPO = "sherlock-audit/2023-09-Gitcoin"
CODE_PATH = "allo-v2/contracts/strategies/rfp-simple/RFPSimpleStrategy.sol"
ISSUE = "https://api.github.com/repos/sherlock-audit/2023-09-Gitcoin-judging/issues/458"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "kb-pattern-research", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def main():
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit("Capture exists; keep the recorded source immutable.")
    issue_bytes = fetch(ISSUE)
    issue = json.loads(issue_bytes)
    commit_bytes = fetch(f"https://api.github.com/repos/{REPO}/commits/main")
    commit = json.loads(commit_bytes)["sha"]
    code_url = f"https://raw.githubusercontent.com/{REPO}/{commit}/{CODE_PATH}"
    code_bytes = fetch(code_url)
    files = {"issue.json": issue_bytes, "report.md": issue["body"].encode("utf-8"),
             "commit.json": commit_bytes, "RFPSimpleStrategy.sol": code_bytes}
    metadata = {
        "schema_version": "1.0", "source": "sherlock", "source_id": "2023-09-Gitcoin-458",
        "source_url": issue["html_url"], "api_url": ISSUE, "title": issue["title"],
        "captured_at": datetime.now(UTC).isoformat(), "issue_updated_at": issue["updated_at"],
        "source_labels": [label["name"] for label in issue["labels"]],
        "repo": REPO, "commit_sha": commit, "code_path": CODE_PATH, "raw_url": code_url,
        "code_url": f"https://github.com/{REPO}/blob/{commit}/{CODE_PATH}",
        "hashes": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "source_snapshot_id": "external_sha256:" + hashlib.sha256(issue_bytes).hexdigest(),
        "storage": "supplementary_pattern_source_not_main_database",
        "limitations": ["Captured main was resolved to a commit; not asserted to be the original audit commit.",
                        "Historical issue concerns pool activation, not feeRecipient; the authorization mechanism is analogous.",
                        "Source labels are not local approval. Original protocol PoC not reproduced."],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (OUT / name).write_bytes(data)
    (OUT / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source": metadata["source_url"], "commit": commit, "output": str(OUT)}))


if __name__ == "__main__":
    main()
