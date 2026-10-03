from __future__ import annotations

from src.models import Finding
from src.models.evidence import ParseStatus
from src.services.evidence.github_fetcher import (
    DiffHunk,
    DiffResult,
    GitHubFetcher,
    PathNotFoundError,
)
from src.services.evidence.pipeline import EvidencePipeline


class FakeFetcher(GitHubFetcher):
    def __init__(self) -> None:
        super().__init__(token=None)
        self.files: dict[tuple[str, str, str], str] = {}
        self.diffs: dict[str, DiffResult] = {}

    def resolve_ref_sha(self, repo: str, ref: str) -> str:
        return f"sha-{ref}"

    def fetch_file(self, repo: str, ref: str, path: str) -> str:
        key = (repo, ref, path)
        if key not in self.files:
            raise PathNotFoundError(f"missing {key}")
        return self.files[key]

    def fetch_commit_diff(self, repo: str, commit_sha: str) -> DiffResult:
        return self.diffs[commit_sha]


def make_finding(**overrides) -> Finding:
    payload = {
        "id": "f-1",
        "title": "Vault.withdraw reentrancy",
        "slug": "vault-withdraw-reentrancy",
    }
    payload.update(overrides)
    return Finding.model_validate(payload)


SAMPLE_FILE = "\n".join(  # noqa: FLY002
    [
        "pragma solidity ^0.8.20;",
        "",
        "contract Vault {",
        "    mapping(address => uint256) public balances;",
        "",
        "    function withdraw(uint256 amount) external {",
        '        (bool ok, ) = msg.sender.call{value: amount}("");',
        '        require(ok, "failed");',
        "        balances[msg.sender] -= amount;",
        "    }",
        "}",
    ]
)


def test_url_with_line_branch_slices_context_window() -> None:
    fetcher = FakeFetcher()
    fetcher.files[("acme/vaults", "sha-main", "src/Vault.sol")] = SAMPLE_FILE

    pipeline = EvidencePipeline(fetcher, context_lines=2)
    finding = make_finding(
        content="https://github.com/acme/vaults/blob/main/src/Vault.sol#L7-L9",
    )

    result = pipeline.process(finding)

    assert len(result.evidences) == 1
    evidence = result.evidences[0]
    assert evidence.kind.value == "url_with_line"
    assert evidence.ref_sha == "sha-main"
    # The requested context is lines 5-11: contract declaration is not present,
    # and the trailing contract brace cannot be repaired by adding a wrapper.
    assert evidence.parse_status is ParseStatus.INVALID
    assert evidence.contract_name is None
    assert evidence.function_name == "withdraw"
    assert evidence.start_line < 7
    assert evidence.end_line > 9


def test_located_by_symbol_falls_back_to_coarse_file() -> None:
    fetcher = FakeFetcher()
    fetcher.files[("acme/vaults", "sha-main", "src/Mystery.sol")] = SAMPLE_FILE

    pipeline = EvidencePipeline(fetcher)
    finding = make_finding(
        title="Unknown issue",
        content="https://github.com/acme/vaults/blob/main/src/Mystery.sol",
    )

    result = pipeline.process(finding)

    assert len(result.evidences) == 1
    evidence = result.evidences[0]
    assert evidence.kind.value == "coarse_file"
    assert evidence.start_line == 1


def test_missing_repo_is_soft_failure() -> None:
    fetcher = FakeFetcher()

    pipeline = EvidencePipeline(fetcher)
    finding = make_finding(
        content="https://github.com/gone/repo/blob/main/src/V.sol#L1-L5",
    )

    result = pipeline.process(finding)

    assert result.evidences == []
    assert result.unresolved_urls


def test_inline_snippet_is_validated_and_ranked() -> None:
    pipeline = EvidencePipeline(FakeFetcher())
    finding = make_finding(
        content=(
            "```solidity\n"
            "function withdraw(uint256 a) external {\n"
            '    msg.sender.call{value: a}("");\n'
            "}\n"
            "```"
        ),
    )

    result = pipeline.process(finding)

    assert len(result.evidences) == 1
    evidence = result.evidences[0]
    assert evidence.kind.value == "inline_snippet"
    assert evidence.confidence_rank == 4
    assert evidence.parse_status is ParseStatus.REPAIRED


def test_diff_branch_extracts_vulnerable_and_fixed_pairs() -> None:
    fetcher = FakeFetcher()
    fetcher.diffs["abc1234"] = DiffResult(
        commit_sha="abc1234",
        hunks=[
            DiffHunk(
                path="src/Vault.sol",
                removed_lines=["balances[msg.sender] -= amount;"],
                added_lines=[
                    "balances[msg.sender] -= amount;",
                    '(bool ok, ) = msg.sender.call{value: amount}("");',
                ],
                removed_start=9,
                added_start=9,
            )
        ],
    )

    pipeline = EvidencePipeline(fetcher)
    finding = make_finding(
        content="Fixed by https://github.com/acme/vaults/commit/abc1234",
    )

    result = pipeline.process(finding)

    assert len(result.evidences) == 1
    evidence = result.evidences[0]
    assert evidence.kind.value == "github_diff"
    assert evidence.confidence_rank == 1
    assert "balances" in evidence.snippet
    assert evidence.extra.get("fixed_snippet")
