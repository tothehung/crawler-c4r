from __future__ import annotations

from src.models.evidence import ParseStatus
from src.services.evidence.validator import (
    expand_window,
    locate_symbol,
    repair_by_wrapping,
    validate,
)


CONTRACT_SNIPPET = """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Vault {
    mapping(address => uint256) public balances;

    function deposit() public payable {
        balances[msg.sender] += msg.value;
    }
}
"""


def test_balanced_contract_is_ok_with_symbols() -> None:
    result = validate(CONTRACT_SNIPPET)

    assert result.status is ParseStatus.OK
    assert result.contract_name == "Vault"
    assert result.function_name == "deposit"


def test_unbalanced_function_fragment_repairs_to_repaired() -> None:
    fragment = "function withdraw(uint256 amount) external {\n        msg.sender.call{value: amount}(\"\");\n    }"

    result = validate(fragment)

    assert result.status is ParseStatus.REPAIRED
    assert repair_by_wrapping(fragment) is not None


def test_contract_snippet_is_not_wrapped() -> None:
    wrapped = repair_by_wrapping(CONTRACT_SNIPPET)

    assert wrapped is None


def test_garbage_is_invalid() -> None:
    result = validate("}{ total nonsense (((")

    assert result.status is ParseStatus.INVALID


def test_empty_snippet_is_unresolved() -> None:
    assert validate("").status is ParseStatus.UNRESOLVED
    assert validate("   \n  ").status is ParseStatus.UNRESOLVED


def test_locate_symbol_finds_function_block() -> None:
    start, end = locate_symbol(
        CONTRACT_SNIPPET,
        ["Vault.deposit"],
    )

    assert start is not None and end is not None
    located = "\n".join(CONTRACT_SNIPPET.split("\n")[start - 1 : end])
    assert "function deposit" in located
    assert end >= start


def test_locate_symbol_falls_back_to_contract_block() -> None:
    snippet = CONTRACT_SNIPPET.replace("function deposit", "function stake")
    start, end = locate_symbol(snippet, ["Vault.deposit"])

    assert start is not None and end is not None
    assert "contract Vault" in "\n".join(snippet.split("\n")[start - 1 : end])


def test_expand_window_respects_bounds() -> None:
    total = 50

    assert expand_window(total, 5, 10, context=20) == (1, 30)
    assert expand_window(total, 40, 45, context=10) == (30, 50)
