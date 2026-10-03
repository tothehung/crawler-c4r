// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// Synthetic requirement: accepted amounts must be preserved exactly or revert.
contract GuardedReserve {
    uint128 public reserve;
    function record(uint256 amount) external {
        require(amount <= type(uint128).max, "amount exceeds uint128");
        reserve = uint128(amount);
    }
}
