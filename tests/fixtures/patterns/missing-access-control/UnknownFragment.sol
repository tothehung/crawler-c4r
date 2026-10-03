function _setFeeRecipient(address recipient) internal {
    require(recipient != address(0), "zero recipient");
    feeRecipient = recipient;
}
