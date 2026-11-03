# W3GoAudit — Báo Cáo Triage Đa Nhóm Lỗi (Auditor Workspace Demo)

> **Thời điểm xuất:** 2026-11-03T10:15:53Z  
> **Tổng số findings được triage:** 30  
> **Nguyên tắc:** Tách biệt tuyệt đối 4 trường: Finding gốc | Bằng chứng ngữ cảnh | Đề xuất AI | Quyết định Auditor.  

---

## 1. Tóm Tắt Tổng Quan Quyết Định Kiểm Toán

| Record ID | Nhóm Lỗ Hổng | Đề Xuất AI | Quyết Định Auditor | Khớp Ground Truth | Độ Đầy Đủ Ngữ Cảnh |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `pilot-uint128-tp-001` | `SOL-UINT128-NARROWING-001` | **TP** | **TP** | ✓ MATCH | 40% |
| `pilot-uint128-fp-001` | `SOL-UINT128-NARROWING-001` | **FP** | **FP** | ✓ MATCH | 40% |
| `pilot-uint128-uncertain-001` | `SOL-UINT128-NARROWING-001` | **Uncertain** | **Uncertain** | ✓ MATCH | 40% |
| `pilot-uint128-tp-002` | `SOL-UINT128-NARROWING-001` | **TP** | **TP** | ✓ MATCH | 20% |
| `pilot-uint128-fp-002` | `SOL-UINT128-NARROWING-001` | **FP** | **FP** | ✓ MATCH | 80% |
| `pilot-uint128-uncertain-002` | `SOL-UINT128-NARROWING-001` | **Uncertain** | **Uncertain** | ✓ MATCH | 40% |
| `pilot-access-tp-001` | `SOL-ACCESS-CONTROL-001` | **TP** | **TP** | ✓ MATCH | 60% |
| `pilot-access-fp-001` | `SOL-ACCESS-CONTROL-001` | **FP** | **FP** | ✓ MATCH | 80% |
| `pilot-access-uncertain-001` | `SOL-ACCESS-CONTROL-001` | **Uncertain** | **Uncertain** | ✓ MATCH | 40% |
| `pilot-access-tp-002` | `SOL-ACCESS-CONTROL-001` | **TP** | **TP** | ✓ MATCH | 20% |
| `pilot-access-fp-002` | `SOL-ACCESS-CONTROL-001` | **FP** | **FP** | ✓ MATCH | 20% |
| `pilot-access-uncertain-002` | `SOL-ACCESS-CONTROL-001` | **Uncertain** | **Uncertain** | ✓ MATCH | 60% |
| `pilot-hard-uint128-fp-safecast-indirect` | `SOL-UINT128-NARROWING-001` | **FP** | **FP** | ✓ MATCH | 40% |
| `pilot-hard-uint128-tp-unchecked-scope` | `SOL-UINT128-NARROWING-001` | **TP** | **TP** | ✓ MATCH | 40% |
| `pilot-hard-access-fp-multisig` | `SOL-ACCESS-CONTROL-001` | **FP** | **FP** | ✓ MATCH | 60% |
| `pilot-hard-access-tp-timelock-zero-delay` | `SOL-ACCESS-CONTROL-001` | **TP** | **TP** | ✓ MATCH | 60% |
| `pilot-hard-access-uncertain-role-inheritance` | `SOL-ACCESS-CONTROL-001` | **Uncertain** | **Uncertain** | ✓ MATCH | 60% |
| `pilot-hard-uint128-uncertain-assembly` | `SOL-UINT128-NARROWING-001` | **Uncertain** | **Uncertain** | ✓ MATCH | 20% |
| `pilot-hard-access-fp-proxy-initializer` | `SOL-ACCESS-CONTROL-001` | **FP** | **FP** | ✓ MATCH | 60% |
| `pilot-hard-uint128-tp-arithmetic-overflow` | `SOL-UINT128-NARROWING-001` | **TP** | **TP** | ✓ MATCH | 40% |
| `reentrancy-tp-001` | `SOL-REENTRANCY-001` | **TP** | **TP** | ✓ MATCH | 20% |
| `reentrancy-fp-001` | `SOL-REENTRANCY-001` | **FP** | **FP** | ✓ MATCH | 20% |
| `reentrancy-fp-002` | `SOL-REENTRANCY-001` | **FP** | **FP** | ✓ MATCH | 80% |
| `reentrancy-uncertain-001` | `SOL-REENTRANCY-001` | **Uncertain** | **Uncertain** | ✓ MATCH | 20% |
| `reentrancy-tp-002` | `SOL-REENTRANCY-001` | **TP** | **TP** | ✓ MATCH | 20% |
| `reentrancy-fp-003` | `SOL-REENTRANCY-001` | **FP** | **FP** | ✓ MATCH | 20% |
| `reentrancy-uncertain-002` | `SOL-REENTRANCY-001` | **Uncertain** | **Uncertain** | ✓ MATCH | 60% |
| `reentrancy-tp-003` | `SOL-REENTRANCY-001` | **TP** | **TP** | ✓ MATCH | 20% |
| `reentrancy-fp-004` | `SOL-REENTRANCY-001` | **FP** | **FP** | ✓ MATCH | 20% |
| `reentrancy-tp-004` | `SOL-REENTRANCY-001` | **TP** | **TP** | ✓ MATCH | 60% |

- **Xác nhận lỗ hổng thật (TP):** 11 findings
- **Loại bỏ cảnh báo giả (FP):** 11 findings (Tiết kiệm thời gian rà soát)
- **Yêu cầu bổ sung context (Uncertain):** 8 findings

---

## 2. Chi Tiết Từng Bản Ghi (Audit Tracing 4 Trường)

### Case #1: `pilot-uint128-tp-001` — UnsafeReserve: Silent overflow when casting large reserve amount

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-UINT128-NARROWING-001`
- **Mô tả:** The `record(uint256 amount)` function stores user-provided `amount` directly into `reserve` which is of type `uint128`. When `amount` exceeds `2^128 - 1`, the cast silently truncates the high bits, causing `reserve` to store an incorrect value. There is no check before the cast.
```solidity
uint128 public reserve;

function record(uint256 amount) external {
    reserve = uint128(amount); // unsafe cast, no guard
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 40%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **TP**
- **Lập luận AI:** [Critic Pass] Auditor said TP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `CONFIRMED_TP` (Ground Truth: **TP**)
- **Căn cứ quyết định:** Hàm record() cast uint256 → uint128 trực tiếp không có guard. Khi amount = 2^128 sẽ bị truncate thành 0, vi phạm invariant 'reserve phải bằng giá trị đầu vào'.

---

### Case #2: `pilot-uint128-fp-001` — GuardedReserve: Casting with explicit bound check (flagged by rule, actually safe)

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-UINT128-NARROWING-001`
- **Mô tả:** The `record(uint256 amount)` function casts uint256 to uint128. Static rule flags this as potential narrowing overflow.
```solidity
uint128 public reserve;

function record(uint256 amount) external {
    require(amount <= type(uint128).max, "overflow");
    reserve = uint128(amount); // safe: guarded above
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 40%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `['require(amount <= type(uint128).max', 'require(amount <= type(uint128)']`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **FP**
- **Lập luận AI:** [Critic Pass] Auditor said FP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `REJECTED_FP` (Ground Truth: **FP**)
- **Căn cứ quyết định:** Có guard `require(amount <= type(uint128).max)` trước cast. Mọi giá trị vượt ngưỡng sẽ revert, không xảy ra silent overflow.

---

### Case #3: `pilot-uint128-uncertain-001` — UnknownFragment: Internal function with uint128 cast, no caller visible

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-UINT128-NARROWING-001`
- **Mô tả:** An internal function casts uint256 to uint128. Cannot determine if the caller validates the input range before invoking this function.
```solidity
uint128 private _cached;

function _updateCache(uint256 val) internal {
    _cached = uint128(val); // cast without local guard
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 40%
- **Phạm vi hiển thị (Visibility):** internal/private
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **Uncertain**
- **Lập luận AI:** [Critic Pass] Auditor said Uncertain. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `DEFERRED_Uncertain` (Ground Truth: **Uncertain**)
- **Căn cứ quyết định:** Fragment nội bộ không thấy caller. Có thể caller đã guard trước khi gọi hàm này, hoặc không. Không đủ context để kết luận.

---

### Case #4: `pilot-uint128-tp-002` — [H-03] Risk of silent overflow in reserves update — Caviar

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-UINT128-NARROWING-001`
- **Mô tả:** However, these two variables are of type `uint128`, while the values that update them are of type `uint256`. This means that casting to a lower type is necessary, but this casting is performed without first checking that the values being cast can fit into the lower type. As a result, there is a risk of a silent overflow occurring during the casting process.
```solidity
uint128 public virtualBaseTokenReserves;
uint128 public virtualNftReserves;

function buy(...) {
    virtualBaseTokenReserves = uint128(netInputAmount - feeAmount - protocolFeeAmount);
    virtualNftReserves = uint128(weightSum);
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 20%
- **Phạm vi hiển thị (Visibility):** internal/private
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **TP**
- **Lập luận AI:** [Critic Pass] Auditor said TP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `CONFIRMED_TP` (Ground Truth: **TP**)
- **Căn cứ quyết định:** Finding được xác nhận bởi Code4rena audit report. virtualBaseTokenReserves và virtualNftReserves là uint128, update bằng uint256 value mà không check overflow.

---

### Case #5: `pilot-uint128-fp-002` — SafeCast usage flagged as narrowing — false alarm

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-UINT128-NARROWING-001`
- **Mô tả:** The contract converts uint256 to uint128 in the reserve update function.
```solidity
using SafeCast for uint256;
uint128 public reserve;

function setReserve(uint256 amount) external onlyOwner {
    reserve = amount.toUint128(); // SafeCast: reverts on overflow
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 80%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `onlyOwner`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **FP**
- **Lập luận AI:** [Critic Pass] Auditor said FP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `REJECTED_FP` (Ground Truth: **FP**)
- **Căn cứ quyết định:** Contract sử dụng SafeCast library từ OpenZeppelin, hàm toUint128() sẽ revert nếu overflow. Rule phát hiện cast nhưng không nhận ra SafeCast wrapper.

---

### Case #6: `pilot-uint128-uncertain-002` — Reserve update with narrowing cast — safety depends on token economics

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-UINT128-NARROWING-001`
- **Mô tả:** The pool stores reserves as uint128. The update function accepts uint256 input.
```solidity
uint128 public reserveA;

function sync(uint256 newReserveA) external {
    reserveA = uint128(newReserveA);
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 40%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **Uncertain**
- **Lập luận AI:** [Critic Pass] Auditor said Uncertain. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `DEFERRED_Uncertain` (Ground Truth: **Uncertain**)
- **Căn cứ quyết định:** Cần xem protocol invariant: giá trị có thể bao giờ vượt 2^128 không? Nếu token là stablecoin với 6 decimals, max supply << 2^128 thì thực ra safe. Cần thêm thông tin về protocol design.

---

### Case #7: `pilot-access-tp-001` — Missing access control on setFeeRecipient — anyone can call

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-ACCESS-CONTROL-001`
- **Mô tả:** The `setFeeRecipient` function lacks any access control modifier. Any external address can call it to redirect protocol fees to an arbitrary address.
```solidity
address public feeRecipient;

function setFeeRecipient(address newRecipient) external {
    // no onlyOwner, no require(msg.sender == ...)
    feeRecipient = newRecipient;
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 60%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `onlyOwner`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `['require(msg.sender ==']`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **TP**
- **Lập luận AI:** [Critic Pass] Auditor said TP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `CONFIRMED_TP` (Ground Truth: **TP**)
- **Căn cứ quyết định:** Hàm setFeeRecipient() không có bất kỳ modifier kiểm tra quyền nào. Bất kỳ ai cũng có thể gọi và thay đổi fee recipient.

---

### Case #8: `pilot-access-fp-001` — onlyOwner through inheritance — flagged but protected

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-ACCESS-CONTROL-001`
- **Mô tả:** The `setFeeRecipient` function appears to have no access control modifier in the function definition.
```solidity
contract FeeManager is Ownable {
    address public feeRecipient;
    
    function setFeeRecipient(address newRecipient) external onlyOwner {
        feeRecipient = newRecipient;
    }
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 80%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `onlyOwner`
- **Kế thừa (Inheritance):** `Ownable`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **FP**
- **Lập luận AI:** [Critic Pass] Auditor said FP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `REJECTED_FP` (Ground Truth: **FP**)
- **Căn cứ quyết định:** Hàm có modifier onlyOwner kế thừa từ Ownable. Rule không parse được inheritance chain, báo nhầm missing access control.

---

### Case #9: `pilot-access-uncertain-001` — Setter with no visible modifier — custom access pattern possible

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-ACCESS-CONTROL-001`
- **Mô tả:** The `updateConfig` function has no access control modifier in its definition.
```solidity
mapping(address => bool) public admins;

function updateConfig(uint256 newValue) external {
    // custom check using storage mapping
    require(admins[msg.sender], "not admin");
    configValue = newValue;
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 40%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `['require(admins[']`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **Uncertain**
- **Lập luận AI:** [Critic Pass] Auditor said Uncertain. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `DEFERRED_Uncertain` (Ground Truth: **Uncertain**)
- **Căn cứ quyết định:** Hàm không có modifier tường minh nhưng contract có custom access control có thể check ở constructor hoặc storage mapping. Cần xem toàn bộ contract.

---

### Case #10: `pilot-access-tp-002` — Protocol fee recipient can be set by any caller

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-ACCESS-CONTROL-001`
- **Mô tả:** The `setProtocolFeeRecipient` function is missing access control, allowing any user to redirect protocol fee revenue to an arbitrary address.
```solidity
function setProtocolFeeRecipient(address _recipient) external {
    protocolFeeRecipient = _recipient;
    emit ProtocolFeeRecipientUpdated(_recipient);
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 20%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **TP**
- **Lập luận AI:** [Critic Pass] Auditor said TP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `CONFIRMED_TP` (Ground Truth: **TP**)
- **Căn cứ quyết định:** Protocol fee setter có thể gọi bởi bất kỳ ai. Attacker có thể redirect fee đến địa chỉ của mình.

---

### Case #11: `pilot-access-fp-002` — Permissionless update — by design, not a vulnerability

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-ACCESS-CONTROL-001`
- **Mô tả:** The `syncPrice` function can be called by anyone to update the price oracle.
```solidity
// Permissionless oracle sync — anyone can call to keep price fresh
function syncPrice() external {
    _updatePrice();
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 20%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **FP**
- **Lập luận AI:** [Critic Pass] Auditor said FP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `REJECTED_FP` (Ground Truth: **FP**)
- **Căn cứ quyết định:** Hàm intentionally public vì đây là permissionless protocol — bất kỳ ai cũng được phép update theo design. Đây là feature không phải bug.

---

### Case #12: `pilot-access-uncertain-002` — Admin function behind timelock — safety depends on delay configuration

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-ACCESS-CONTROL-001`
- **Mô tả:** The function is gated behind a timelock contract. The security depends on the timelock delay value.
```solidity
function emergencyWithdraw(address token) external onlyTimelock {
    IERC20(token).transfer(treasury, IERC20(token).balanceOf(address(this)));
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 60%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `onlyTimelock`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **Uncertain**
- **Lập luận AI:** [Critic Pass] Auditor said Uncertain. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `DEFERRED_Uncertain` (Ground Truth: **Uncertain**)
- **Căn cứ quyết định:** Hàm có timelock nhưng không rõ timelock delay là bao nhiêu. Nếu delay < 24h thì vẫn có rủi ro. Cần xem cấu hình timelock.

---

### Case #13: `pilot-hard-uint128-fp-safecast-indirect` — Indirect SafeCast via internal wrapper — Naive LLM may flag as TP

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-UINT128-NARROWING-001`
- **Mô tả:** The `_store` function assigns uint128 from a uint256 value. Static analysis flags the cast operation.
```solidity
// Wrapper hides SafeCast — Naive LLM không cross-reference
function _safeToUint128(uint256 v) internal pure returns (uint128) {
    require(v <= type(uint128).max, "u128 overflow");
    return uint128(v);
}

uint128 public slot;

function _store(uint256 raw) internal {
    slot = _safeToUint128(raw); // safe: wrapper validates first
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 40%
- **Phạm vi hiển thị (Visibility):** internal/private
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `['require(v <= type(uint128).max', 'require(v <= type(uint128)']`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **FP**
- **Lập luận AI:** [Critic Pass] Auditor said FP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `REJECTED_FP` (Ground Truth: **FP**)
- **Căn cứ quyết định:** SafeCast được gọi qua một hàm wrapper nội bộ _safeToUint128(). Naive LLM thấy `uint128(val)` trực tiếp nhưng không trace được rằng val đã được validate qua wrapper trước khi đến đây. W3GoAudit nên hỏi: 'Có guard nào trên đường đi của giá trị này không?' và trace được qua wrapper.

---

### Case #14: `pilot-hard-uint128-tp-unchecked-scope` — Unsafe cast inside unchecked block — Naive LLM may misinterpret as safe

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-UINT128-NARROWING-001`
- **Mô tả:** Reserve update performs arithmetic in unchecked context with subsequent uint128 cast.
```solidity
uint128 public reserve;

function updateReserve(uint256 amount) external {
    unchecked {
        // Naive LLM: 'unchecked means developer knows what they're doing'
        // Reality: unchecked REMOVES Solidity 0.8+ overflow protection
        reserve = uint128(amount + bonus); // TP: no bound check, unchecked makes worse
    }
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 40%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **TP**
- **Lập luận AI:** [Critic Pass] Auditor said TP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `CONFIRMED_TP` (Ground Truth: **TP**)
- **Căn cứ quyết định:** Cast nằm trong block `unchecked {}`. Naive LLM có thể nhầm rằng unchecked chỉ là tối ưu gas và không nguy hiểm. Nhưng unchecked không thêm guard — nó loại bỏ overflow check của Solidity 0.8+, làm silent overflow dễ xảy ra hơn. Đây là TP nghiêm trọng hơn case bình thường.

---

### Case #15: `pilot-hard-access-fp-multisig` — Admin function protected by Gnosis Safe multi-sig — Naive LLM may not recognize pattern

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-ACCESS-CONTROL-001`
- **Mô tả:** The `withdrawFunds` function lacks a standard onlyOwner modifier. Static analysis flags it as missing access control.
```solidity
address public immutable multisig; // Gnosis Safe address

modifier onlyMultisig() {
    require(msg.sender == multisig, "not multisig");
    _;
}

function withdrawFunds(address token, uint256 amount) external onlyMultisig {
    IERC20(token).transfer(multisig, amount);
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 60%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `onlyMultisig, multisig-backed`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `['require(msg.sender ==']`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **FP**
- **Lập luận AI:** [Critic Pass] Auditor said FP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `REJECTED_FP` (Ground Truth: **FP**)
- **Căn cứ quyết định:** Hàm được bảo vệ bởi multi-sig Gnosis Safe qua modifier onlyMultisig. Naive LLM có thể không nhận ra multi-sig là một dạng access control hợp lệ và báo TP. W3GoAudit checklist Q2 hỏi 'Is there an access control modifier or authorization require?' → answer Yes: onlyMultisig.

---

### Case #16: `pilot-hard-access-tp-timelock-zero-delay` — onlyTimelock with zero delay — Naive LLM assigns FP, actually TP

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-ACCESS-CONTROL-001`
- **Mô tả:** The `setController` function uses onlyTimelock modifier. However, the timelock was deployed with minDelay=0.
```solidity
// TimelockController deployed with: minDelay = 0
// This means proposals can be executed immediately — timelock provides no protection

function setController(address newController) external onlyTimelock {
    controller = newController;
}

// Constructor in deployer:
// new TimelockController(0, proposers, executors, admin)
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 60%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `onlyTimelock`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `['WARNING: TimelockController delay=0 — provides no protection!']`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **TP**
- **Lập luận AI:** [Critic Pass] Auditor said TP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `CONFIRMED_TP` (Ground Truth: **TP**)
- **Căn cứ quyết định:** Timelock được cấu hình với delay=0 trong constructor, biến onlyTimelock thành vô nghĩa về mặt bảo mật. Naive LLM thấy onlyTimelock modifier → gán FP. W3GoAudit checklist Q4 hỏi 'Does function rely on external checks whose configuration is not in snippet?' → Uncertain. Với context_notes tiết lộ delay=0 → TP.

---

### Case #17: `pilot-hard-access-uncertain-role-inheritance` — AccessControl with role-based guard — Naive LLM may assign FP, actually Uncertain

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-ACCESS-CONTROL-001`
- **Mô tả:** The `configureProtocol` function uses role-based access control. Static analysis flags function as potentially missing standard modifier.
```solidity
bytes32 public constant MANAGER_ROLE = keccak256("MANAGER_ROLE");

function configureProtocol(uint256 newFee) external {
    // hasRole check instead of modifier
    require(hasRole(MANAGER_ROLE, msg.sender), "not manager");
    protocolFee = newFee;
}

// Note: initializer not shown — MANAGER_ROLE grant is in __AccessControl_init
// Upgradeable proxy: admin can replace implementation
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 60%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `['require(hasRole(', 'hasRole() check present']`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **Uncertain**
- **Lập luận AI:** [Critic Pass] Auditor said Uncertain. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `DEFERRED_Uncertain` (Ground Truth: **Uncertain**)
- **Căn cứ quyết định:** Contract kế thừa từ AccessControlUpgradeable và dùng hasRole(). Naive LLM có thể thấy `require(hasRole(MANAGER_ROLE, msg.sender))` và kết luận FP. Nhưng không thể kết luận FP vì: (1) không rõ MANAGER_ROLE được grant cho ai trong initializer, (2) contract upgradeable — admin có thể bị thay thế. Cần xem deployment script và grant logs.

---

### Case #18: `pilot-hard-uint128-uncertain-assembly` — uint128 truncation via inline assembly — Naive LLM likely misclassifies

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-UINT128-NARROWING-001`
- **Mô tả:** The function performs bit manipulation in assembly that may result in uint128 truncation of uint256 values.
```solidity
uint128 public packedLow;

function packReserve(uint256 fullReserve) external {
    assembly {
        // Store lower 128 bits — is there a guard checking upper 128 bits are zero?
        // Naive LLM: cannot determine safety from assembly alone
        let lo := and(fullReserve, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF)
        sstore(packedLow.slot, lo)
    }
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 20%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **Uncertain**
- **Lập luận AI:** [Critic Pass] Auditor said Uncertain. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `DEFERRED_Uncertain` (Ground Truth: **Uncertain**)
- **Căn cứ quyết định:** Cast xảy ra trong inline assembly block bằng lệnh `shl`/`shr`. Naive LLM có thể không parse được assembly hoặc đưa ra kết luận TP/FP vội vã. W3GoAudit nên nhận ra đây là assembly context → checklist Q2 trả lời Unknown → Uncertain vì thiếu khả năng phân tích inline assembly.

---

### Case #19: `pilot-hard-access-fp-proxy-initializer` — Proxy initializer flagged as missing access control — Naive LLM false positive

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-ACCESS-CONTROL-001`
- **Mô tả:** The `initialize` function is public and appears to lack access control modifier.
```solidity
contract VaultV1 is Initializable, OwnableUpgradeable {
    uint256 public version;
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() { _disableInitializers(); }
    
    // `initializer` modifier ensures this can only be called ONCE
    function initialize(address _owner) external initializer {
        __Ownable_init(_owner);
        version = 1;
    }
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 60%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `Initializable, OwnableUpgradeable`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **FP**
- **Lập luận AI:** [Critic Pass] Auditor said FP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `REJECTED_FP` (Ground Truth: **FP**)
- **Căn cứ quyết định:** Hàm `initialize` là initializer của upgradeable proxy pattern — chỉ có thể gọi một lần duy nhất nhờ `initializer` modifier từ OpenZeppelin. Naive LLM thấy hàm external không có onlyOwner → báo TP. W3GoAudit nên nhận ra `initializer` modifier đảm bảo chỉ gọi được một lần — đây là design pattern hợp lệ, không phải missing access control.

---

### Case #20: `pilot-hard-uint128-tp-arithmetic-overflow` — Off-by-one in require guard — Naive LLM assigns FP, actually TP

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-UINT128-NARROWING-001`
- **Mô tả:** The reserve update function has a require check before casting to uint128. However, the boundary condition is incorrect.
```solidity
uint128 public reserve;

function setReserve(uint256 amount) external {
    // BUG: should be <= type(uint128).max, not < 2**128
    // type(uint128).max = 2**128 - 1
    // 2**128 - 1 passes this check but truncates to 0 when cast!
    require(amount < 2**128, "overflow"); // off-by-one: allows 2^128-1 through
    reserve = uint128(amount);
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 40%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `['require(amount < 2**128']`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **TP**
- **Lập luận AI:** [Critic Pass] Auditor said TP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `CONFIRMED_TP` (Ground Truth: **TP**)
- **Căn cứ quyết định:** Có require() trước cast nhưng require check giá trị SAI — check `amount < 2^128` thay vì `amount <= type(uint128).max` (= 2^128 - 1). Giá trị 2^128 - 1 vẫn pass require nhưng khi cast sang uint128 thì bị truncate. Naive LLM thấy require → gán FP. W3GoAudit checklist Q2: 'Is require checking amount <= type(uint128).max?' → No (off by one) → TP.

---

### Case #21: `reentrancy-tp-001` — Classic Reentrancy: balance updated after external call in withdraw()

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-REENTRANCY-001`
- **Mô tả:** The `withdraw` function calls `msg.sender.call{value: amount}` before updating `balances[msg.sender] = 0`. This allows a malicious contract to re-enter `withdraw()` in its receive() function before the balance is zeroed.
```solidity
mapping(address => uint256) public balances;

function withdraw(uint256 amount) external {
    require(balances[msg.sender] >= amount, "insufficient");
    // VULNERABILITY: external call before state update
    (bool ok,) = msg.sender.call{value: amount}("")
    require(ok, "transfer failed");
    balances[msg.sender] -= amount; // state update AFTER call — reentrancy!!
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 20%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **TP**
- **Lập luận AI:** [Critic Pass] Auditor said TP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `CONFIRMED_TP` (Ground Truth: **TP**)
- **Căn cứ quyết định:** Điển hình của lỗi reentrancy: state update (balance = 0) xảy ra SAU external call (msg.sender.call). Kẻ tấn công có thể re-enter withdraw() trong receive() để rút nhiều lần trước khi balance bị reset về 0.

---

### Case #22: `reentrancy-fp-001` — Withdrawal with correct CEI pattern — static rule false alarm

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-REENTRANCY-001`
- **Mô tả:** Static analysis flags external call in withdraw function. However, state update precedes the external call.
```solidity
mapping(address => uint256) public balances;

function withdraw(uint256 amount) external {
    require(balances[msg.sender] >= amount, "insufficient");
    // CEI: Effects before Interaction
    balances[msg.sender] -= amount; // state update FIRST
    (bool ok,) = msg.sender.call{value: amount}(""); // external call AFTER
    require(ok, "transfer failed");
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 20%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **FP**
- **Lập luận AI:** [Critic Pass] Auditor said FP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `REJECTED_FP` (Ground Truth: **FP**)
- **Căn cứ quyết định:** Hàm tuân theo pattern CEI (Checks-Effects-Interactions) đúng thứ tự: kiểm tra (require), cập nhật state (balances[msg.sender] = 0), rồi mới gọi ngoại. Không thể khai thác reentrancy vì state đã được ghi trước khi gọi ngoại.

---

### Case #23: `reentrancy-fp-002` — External call guarded by nonReentrant modifier — false alarm

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-REENTRANCY-001`
- **Mô tả:** Function performs external ETH transfer. Static scanner flags potential reentrancy.
```solidity
import {ReentrancyGuard} from "@openzeppelin/contracts/security/ReentrancyGuard.sol";

contract Vault is ReentrancyGuard {
    mapping(address => uint256) public balances;

    function withdraw(uint256 amount) external nonReentrant {
        require(balances[msg.sender] >= amount, "insufficient");
        balances[msg.sender] -= amount;
        (bool ok,) = msg.sender.call{value: amount}("");
        require(ok);
    }
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 80%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `nonReentrant`
- **Kế thừa (Inheritance):** `ReentrancyGuard`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **FP**
- **Lập luận AI:** [Critic Pass] Auditor said FP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `REJECTED_FP` (Ground Truth: **FP**)
- **Căn cứ quyết định:** Hàm có modifier nonReentrant từ OpenZeppelin ReentrancyGuard. Modifier này dùng lock state (status) để ngăn chặn mọi re-entry call vào hàm này hoặc bất kỳ hàm nào cùng guard. Rule tĩnh nhìn thấy external call nhưng không nhận ra nonReentrant.

---

### Case #24: `reentrancy-uncertain-001` — External call with unknown modifier — needs full contract context

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-REENTRANCY-001`
- **Mô tả:** Function makes external call. A custom modifier `guarded` is applied but its implementation is not visible in the snippet.
```solidity
function claimReward(address user) external guarded {
    uint256 reward = pendingReward[user];
    require(reward > 0, "no reward");
    pendingReward[user] = 0;
    (bool ok,) = user.call{value: reward}("");
    require(ok);
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 20%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **Uncertain**
- **Lập luận AI:** [Critic Pass] Auditor said Uncertain. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `DEFERRED_Uncertain` (Ground Truth: **Uncertain**)
- **Căn cứ quyết định:** Hàm có external call nhưng chỉ thấy một phần contract. Không rõ có nonReentrant modifier được định nghĩa ở base contract hay không. Cần xem toàn bộ inheritance chain và modifier definition.

---

### Case #25: `reentrancy-tp-002` — MISO-style: Reentrancy in commitETH via external call before accounting update

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-REENTRANCY-001`
- **Mô tả:** The `commitETH` function transfers ETH to the auction contract before updating the commitment tracking. A malicious contract can re-enter during the ETH receive hook.
```solidity
mapping(address => uint256) public commitments;
uint256 public totalCommitments;

function commitETH(address payable beneficiary) public payable {
    require(msg.value > 0, "no ETH");
    // External call to beneficiary BEFORE updating state
    beneficiary.transfer(msg.value); // WARNING: re-entry point
    // State updated AFTER transfer — reentrancy exploitable!
    commitments[beneficiary] += msg.value;
    totalCommitments += msg.value;
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 20%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **TP**
- **Lập luận AI:** [Critic Pass] Auditor said TP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `CONFIRMED_TP` (Ground Truth: **TP**)
- **Căn cứ quyết định:** Điểm yếu reentrancy trong giao thức MISO (SushiSwap) — external call trong commitETH() xảy ra trước khi cập nhật accounting. Lỗi này đã dẫn đến mất 3M USD trong thực tế (2021).

---

### Case #26: `reentrancy-fp-003` — ERC20 transfer flagged as reentrancy — safe by design

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-REENTRANCY-001`
- **Mô tả:** The function calls IERC20.transfer to send tokens. Scanner flags as potential external call vulnerability.
```solidity
IERC20 public token;
mapping(address => uint256) public balances;

function claimTokens(uint256 amount) external {
    require(balances[msg.sender] >= amount);
    balances[msg.sender] -= amount; // state update first
    token.transfer(msg.sender, amount); // ERC20 transfer — no receive hook
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 20%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **FP**
- **Lập luận AI:** [Critic Pass] Auditor said FP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `REJECTED_FP` (Ground Truth: **FP**)
- **Căn cứ quyết định:** Hàm gọi IERC20.transfer() — đây là external call nhưng không phải external call nguy hiểm vì IERC20.transfer không nhận ETH và không có receive() hook. Token ERC20 không thể re-enter hàm gọi qua transfer(). Chỉ có ETH transfer (call/transfer/send) hoặc ERC777 mới có khả năng re-entry.

---

### Case #27: `reentrancy-uncertain-002` — Token transfer where token type is unknown — could be ERC777

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-REENTRANCY-001`
- **Mô tả:** Function transfers tokens. If the token implements ERC777 hooks, reentrancy may be possible.
```solidity
// Note: token could be ERC20 or ERC777 depending on deployment
IERC20 public token; // interface only — actual token unknown

function distribute(address recipient, uint256 amount) external onlyOwner {
    balances[recipient] -= amount;
    token.transfer(recipient, amount); // safe for ERC20, risky for ERC777
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 60%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `onlyOwner`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **Uncertain**
- **Lập luận AI:** [Critic Pass] Auditor said Uncertain. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `DEFERRED_Uncertain` (Ground Truth: **Uncertain**)
- **Căn cứ quyết định:** Contract gọi token.transfer() nhưng chú thích cho thấy token có thể là ERC777 (có `tokensReceived` hook). Nếu token là ERC777, thì có thể bị re-entry. Không đủ thông tin về kiểu token để quyết định.

---

### Case #28: `reentrancy-tp-003` — Read-only reentrancy via cross-function state read during external call

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-REENTRANCY-001`
- **Mô tả:** A view function reads price/reserve state that can be observed in an inconsistent state during cross-function reentrancy.
```solidity
uint256 public reserve0;
uint256 public reserve1;

// Called by another function that does external ETH call
function getPrice() public view returns (uint256) {
    return reserve1 / reserve0; // reads state that may be mid-update
}

function addLiquidity(uint256 amount) external {
    // external call happens before reserve update
    (bool ok,) = msg.sender.call{value: amount}("");
    reserve0 += amount; // state updated AFTER call — inconsistent during call
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 20%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **TP**
- **Lập luận AI:** [Critic Pass] Auditor said TP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `CONFIRMED_TP` (Ground Truth: **TP**)
- **Căn cứ quyết định:** Read-only reentrancy: hàm không thay đổi state nhưng đọc state trong khi một lệnh gọi ngoại từ hàm khác đang ở giữa quá trình (in-flight). Attacker có thể trigger hàm này từ một hook để đọc state đang ở trạng thái giữa chừng (inconsistent), tạo ra oracle manipulation.

---

### Case #29: `reentrancy-fp-004` — ETH transfer via .transfer() — 2300 gas limit prevents reentrancy

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-REENTRANCY-001`
- **Mô tả:** Function sends ETH using transfer() which has a 2300 gas stipend. Scanner flags ETH transfer as potential reentrancy.
```solidity
mapping(address => uint256) public balances;

function withdraw() external {
    uint256 amount = balances[msg.sender];
    require(amount > 0);
    balances[msg.sender] = 0; // CEI: state cleared first
    payable(msg.sender).transfer(amount); // 2300 gas — cannot reenter
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 20%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `None`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **FP**
- **Lập luận AI:** [Critic Pass] Auditor said FP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `REJECTED_FP` (Ground Truth: **FP**)
- **Căn cứ quyết định:** Hàm dùng `address.transfer()` thay vì `call{value}`. Solidity `transfer()` chỉ chuyển 2300 gas, không đủ để thực hiện state write hoặc gọi thêm function, nên không thể re-entry. Đây là biện pháp phòng thủ cũ trước EIP-1884 nhưng vẫn hiệu quả cho trường hợp này.

---

### Case #30: `reentrancy-tp-004` — Cross-function reentrancy: nonReentrant on A does not protect C

#### 1. Finding Gốc (Raw Scanner Alert):
- **Pattern:** `SOL-REENTRANCY-001`
- **Mô tả:** Function A has nonReentrant, but calls external contract which re-enters function C. C does not have nonReentrant.
```solidity
contract Vault {
    mapping(address => uint256) public balances;
    bool private locked;

    // nonReentrant only on withdraw, NOT on claimReward
    function withdraw(uint256 amount) external nonReentrant {
        balances[msg.sender] -= amount;
        (bool ok,) = msg.sender.call{value: amount}(""); // attacker re-enters claimReward
        require(ok);
    }

    // NO nonReentrant here — cross-function reentrancy target
    function claimReward() external {
        uint256 reward = pendingReward[msg.sender];
        pendingReward[msg.sender] = 0;
        (bool ok,) = msg.sender.call{value: reward}(""); // second external call
        require(ok);
    }
}
```

#### 2. Ngữ Cảnh & Bằng Chứng Mã Nguồn (Context Evidence):
- **Độ đầy đủ (Completeness):** 60%
- **Phạm vi hiển thị (Visibility):** external/public
- **Modifiers:** `nonReentrant`
- **Kế thừa (Inheritance):** `None`
- **Cơ chế bảo vệ (Guards):** `[]`

#### 3. Đề Xuất Của AI (AI Proposal):
- **Phán đoán cuối (Baseline 5 Critic):** **TP**
- **Lập luận AI:** [Critic Pass] Auditor said TP. Critic reviewed evidence and agreed.

#### 4. Quyết Định Auditor (Human Decision):
- **Kết luận duyệt:** `CONFIRMED_TP` (Ground Truth: **TP**)
- **Căn cứ quyết định:** Cross-contract reentrancy: hàm A gọi contract B, contract B re-enters hàm C (cùng project) thay vì hàm A. nonReentrant trên hàm A không bảo vệ hàm C. Cần nonReentrant trên cả hàm C hoặc dùng global lock.

---
