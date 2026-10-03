// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// Synthetic requirement: only the deployer may change feeRecipient after deployment.
contract GuardedFeeConfig {
    address public immutable owner;
    address public feeRecipient;
    constructor() { owner = msg.sender; feeRecipient = msg.sender; }

    function setFeeRecipient(address recipient) external {
        require(msg.sender == owner, "unauthorized");
        require(recipient != address(0), "zero recipient");
        feeRecipient = recipient;
    }
}
