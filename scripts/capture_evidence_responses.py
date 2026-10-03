"""Freeze a small set of public evidence HTTP responses for offline replay."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

DEST = Path(__file__).resolve().parents[1] / "tests/fixtures/evidence_benchmark_v1"


def capture() -> None:
    folder = DEST / "http"
    folder.mkdir(exist_ok=True)
    index_path = folder / "index.json"
    index = (
        json.loads(index_path.read_text(encoding="utf-8"))
        if index_path.exists()
        else []
    )
    by_url = {r["url"]: r for r in index}
    with httpx.Client(
        timeout=30, follow_redirects=True, headers={"User-Agent": "w3goaudit-benchmark"}
    ) as client:

        def get(url: str) -> dict:
            if url in by_url:
                return by_url[url]
            response = client.get(url)
            content = response.text.encode("utf-8")
            filename = hashlib.sha256(url.encode()).hexdigest() + ".txt"
            (folder / filename).write_bytes(content)
            row = {
                "url": url,
                "final_url": str(response.url),
                "status_code": response.status_code,
                "captured_at": datetime.now(UTC).isoformat(),
                "body_file": filename,
                "sha256": hashlib.sha256(content).hexdigest(),
                "headers": {
                    k: response.headers[k]
                    for k in ("content-type", "etag", "retry-after")
                    if k in response.headers
                },
                "fixture_kind": "recorded_http",
            }
            index.append(row)
            by_url[url] = row
            index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
            print(response.status_code, url)
            return row

        repo = "code-423n4/2023-04-caviar"
        ref = get(f"https://api.github.com/repos/{repo}/commits/main")
        if ref["status_code"] == 200:
            commit = json.loads(
                (folder / ref["body_file"]).read_text(encoding="utf-8")
            )["sha"]
            get(
                f"https://raw.githubusercontent.com/{repo}/{commit}/src/PrivatePool.sol"
            )
        repo = "code-423n4/2023-01-astaria"
        commit = "1bfc58b42109b839528ab1c21dc9803d663df898"
        get(f"https://api.github.com/repos/{repo}/commits/{commit}")
        get(f"https://raw.githubusercontent.com/{repo}/{commit}/src/LienToken.sol")
        get("https://api.github.com/gists/06238839330315780b90d9202042ea0f")
        get("https://github.com/outdoteth/caviar-private-pools/pull/6.diff")
        get(
            "https://github.com/Accountable-Protocol/credit-vaults-internal/commit/aea937ccb0d39600236526c1dbcfe78fadbb3865.diff"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", required=True)
    parser.parse_args()
    capture()
