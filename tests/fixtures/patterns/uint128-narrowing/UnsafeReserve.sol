// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// Synthetic requirement: accepted amounts must be preserved exactly or revert.
contract UnsafeReserve {
    uint128 public reserve;
    function record(uint256 amount) external {
        reserve = uint128(amount);
    }
}
