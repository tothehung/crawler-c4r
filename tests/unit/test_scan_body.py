from __future__ import annotations

import pytest

from src.models import Finding
from src.services.evidence.scan_body import scan


def make_finding(**overrides) -> Finding:
    payload = {
        "id": "f-1",
        "title": "Vault.withdraw reentrancy",
        "slug": "vault-withdraw-reentrancy",
    }
    payload.update(overrides)
    return Finding.model_validate(payload)


def test_url_with_line_number_becomes_url_with_line_candidate() -> None:
    finding = make_finding(
        content="See https://github.com/acme/vaults/blob/9d3f2a1/src/Vault.sol#L42-L88",
    )

    result = scan(finding)

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.kind.value == "url_with_line"
    assert candidate.repo == "acme/vaults"
    assert candidate.ref == "9d3f2a1"
    assert candidate.path == "src/Vault.sol"
    assert candidate.start_line == 42
    assert candidate.end_line == 88


def test_blob_url_without_lines_is_located_by_symbol() -> None:
    finding = make_finding(
        content="https://github.com/acme/vaults/blob/main/contracts/Vault.sol",
    )

    result = scan(finding)

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.kind.value == "located_by_symbol"
    assert candidate.ref == "main"


def test_commit_and_pull_urls_are_diff_candidates() -> None:
    finding = make_finding(
        content=(
            "Fixed in https://github.com/acme/vaults/commit/abcdef1234567890 "
            "and https://github.com/acme/vaults/pull/42"
        ),
    )

    result = scan(finding)

    kinds = sorted(c.kind.value for c in result.candidates)
    assert kinds == ["github_diff", "github_diff"]
    shas = [c.commit_sha for c in result.candidates if c.commit_sha]
    pulls = [c.pull_number for c in result.candidates if c.pull_number]
    assert shas == ["abcdef1234567890"]
    assert pulls == [42]


def test_fenced_solidity_block_becomes_inline_snippet() -> None:
    finding = make_finding(
        content="```solidity\ncontract Vault { function x() public {} }\n```",
    )

    result = scan(finding)

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.kind.value == "inline_snippet"
    assert candidate.language == "Solidity"
    assert "contract Vault" in candidate.snippet


def test_untagged_block_with_solidity_keywords_is_inline_snippet() -> None:
    finding = make_finding(content="```\nfunction withdraw() public payable {}\n```")

    result = scan(finding)

    assert len(result.candidates) == 1
    assert result.candidates[0].kind.value == "inline_snippet"


def test_non_solidity_block_is_ignored() -> None:
    finding = make_finding(content="```js\nconsole.log('hi');\n```")

    result = scan(finding)

    assert result.candidates == []


def test_symbol_hints_collected_from_title_and_body() -> None:
    finding = make_finding(
        title="Vault.withdraw can be reentered",
        content="The call to MasterChef.deposit allows reentry.",
    )

    result = scan(finding)

    inline = [c for c in result.candidates if c.kind.value == "inline_snippet"]
    assert inline == []

    hints = result.symbol_hints
    assert "Vault.withdraw" in hints
    assert "MasterChef.deposit" in hints


def test_duplicate_urls_are_deduplicated() -> None:
    url = "https://github.com/acme/vaults/blob/main/src/Vault.sol#L10-L20"
    finding = make_finding(github_link=url, content=f"Dup: {url}")

    result = scan(finding)

    assert len(result.candidates) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/acme/vaults/blob/main/src/Vault.sol",
        "not a url at all",
    ],
)
def test_non_github_links_are_ignored(url: str) -> None:
    finding = make_finding(content=url)

    result = scan(finding)

    assert result.candidates == []
