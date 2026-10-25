# Kế Hoạch Mở Rộng Nhóm Lỗ Hổng — W3GoAudit Expansion Backlog

> **Giai đoạn:** Đợt 3 (26/10/2026 – 01/11/2026) -> Chuẩn bị cho Đợt 4 (02/11/2026 – 15/11/2026)  
> **Trạng thái:** Sẵn sàng triển khai  
> **Mục tiêu:** Chuẩn hóa quy trình mở rộng các pattern lỗ hổng mới vào hệ thống W3GoAudit, đảm bảo chất lượng kiểm thử hồi quy không suy giảm.

---

## 1. Tổng Quan Tiến Độ Mở Rộng Pattern

| Đợt | Pattern ID | Tên Lỗ Hổng / Nhóm | Số Cases Pilot | B4/B5 Acc | Trạng Thái |
| :---: | :--- | :--- | :---: | :---: | :---: |
| **Đợt 1-2** | `SOL-UINT128-NARROWING-001` | Truncation / Narrowing Cast `uint256 -> uint128` | 10 | 100.0% | ✅ Hoàn thành |
| **Đợt 1-2** | `SOL-ACCESS-CONTROL-001` | Missing / Broken Access Control | 10 | 100.0% | ✅ Hoàn thành |
| **Đợt 3** | `SOL-REENTRANCY-001` | Single/Cross-function & Read-only Reentrancy | 16 | 100.0% | ✅ Đã tích hợp |
| **Đợt 4 (A)** | `SOL-DELEGATECALL-001` | Arbitrary / Untrusted `delegatecall` | 15 (dự kiến) | TBD | ⏳ Backlog |
| **Đợt 4 (A)** | `SOL-ARBITRARY-FROM-001` | Arbitrary `from` in `transferFrom` | 15 (dự kiến) | TBD | ⏳ Backlog |
| **Đợt 4 (B)** | `SOL-ORACLE-MANIP-001` | Spot Price Oracle Manipulation (AMM/Reserves) | 16 (dự kiến) | TBD | ⏳ Backlog |
| **Đợt 4 (B)** | `SOL-UNCHECKED-RETURN-001` | Unchecked Low-level Call / Token Return Values | 15 (dự kiến) | TBD | ⏳ Backlog |
| **Đợt 4 (C)** | `SOL-SIG-REPLAY-001` | Signature Malleability & Cross-Chain Replay | 14 (dự kiến) | TBD | ⏳ Backlog |

---

## 2. Tiêu Chuẩn Sẵn Sàng Mở Rộng (Definition of Ready - DoR)

Để một pattern lỗ hổng mới từ DB raw findings được đưa vào pipeline chính thức, nó bắt buộc phải thỏa mãn **5 tiêu chí DoR**:

```
[Raw Findings DB] 
       │
       ▼ (1. Pattern Spec)
[Formal Rule & Taxonomy] 
       │
       ▼ (2. Grounded Checklist)
[4-Facet Verification Questions]
       │
       ▼ (3. Context Signals)
[ContextAssembler Extractor]
       │
       ▼ (4. Benchmark Dataset)
[12-16 Balanced Cases (TP/FP/Uncertain)]
       │
       ▼ (5. Regression Suite)
[Regression Gate: Prec/Rec >= 95%, FP <= 5%]
       │
       ▼
[Official Production Rule]
```

### Chi tiết 5 Tiêu Chí DoR:

1. **Formal Pattern Specification:**
   - Định danh `SOL-<CATEGORY>-<INDEX>`.
   - Mô tả CWE tương ứng (e.g., CWE-841, CWE-197, CWE-284).
   - Biểu thức nhận diện thô của Scanner tĩnh (AST/Regex query).
2. **Grounded Verification Checklist:**
   - Soạn thảo danh sách 4 câu hỏi kiểm chứng phân cấp:
     - *Câu 1 (Trigger):* Lệnh nguy hiểm có thực sự xuất hiện không?
     - *Câu 2 (Guard/Defense):* Có cơ chế phòng vệ nào đang bảo vệ đoạn mã này không?
     - *Câu 3 (Exploitability):* Điều kiện tiền đề (precondition) có thể đạt được bởi attacker không?
     - *Câu 4 (Context Boundary):* Ngữ cảnh hiện tại có đầy đủ hay cần escalate sang `Uncertain`?
3. **Context Signals Extraction:**
   - Bổ sung hàm trích xuất chuyên biệt trong `src/services/context_assembler.py`.
   - Thu thập đầy đủ các modifiers, interfaces, inheritance chain, và state variables liên quan.
4. **Benchmark Dataset độc lập:**
   - Tối thiểu 12 Dev cases + 4 Hard Test cases.
   - Tỉ lệ cân bằng 3 nhãn: True Positive (TP), False Positive (FP), Uncertain.
   - Bao gồm cả synthetic fixtures (đơn giản, cô lập) và real-world Code4rena/Solodit findings.
5. **Đạt chỉ số Regression Suite:**
   - Chạy qua `scripts/run_regression_suite.py`.
   - Baseline 4 và Baseline 5 phải đạt: **Precision >= 95%**, **Recall >= 95%**, **FP Rate <= 5%**.
   - Không gây suy giảm bất kỳ kết quả nào của các pattern đã có trước đó.

---

## 3. Danh Mục Chi Tiết 5 Pattern Mở Rộng Tiếp Theo (Đợt 4)

### 3.1. `SOL-DELEGATECALL-001`: Arbitrary Target in Delegatecall
- **Mô tả:** Hàm thực hiện `delegatecall` tới một địa chỉ do người dùng kiểm soát hoặc một proxy implementation chưa được xác thực.
- **Rủi ro:** Kẻ tấn công có thể ghi đè toàn bộ storage của contract (bao gồm slot owner/admin) và rút cạn quỹ.
- **Checklist sơ bộ:**
  1. Địa chỉ target của `delegatecall` đến từ tham số hàm hay storage bất biến?
  2. Target có được kiểm tra qua whitelist hoặc modifier `onlyOwner`/`onlyAdmin` không?
  3. Hàm gọi `delegatecall` có phải là hàm nội bộ của implementation logic hợp lệ?
  4. Địa chỉ implementation có được cấu hình tại constructor/deployment script mà không thể thay đổi?
- **Ngữ cảnh cần bóc tách:** Storage layout (ERC-1967 slots), modifier quyền hạn, whitelist mapping.

### 3.2. `SOL-ARBITRARY-FROM-001`: Arbitrary `from` in `transferFrom`
- **Mô tả:** Lệnh gọi `IERC20(token).transferFrom(from, to, amount)` sử dụng tham số `from` tùy ý do caller chỉ định thay vì ràng buộc `from == msg.sender`.
- **Rủi ro:** Nếu nạn nhân đã `approve` allowance cho contract này, bất kỳ ai cũng có thể gọi hàm để rút token của nạn nhân.
- **Checklist sơ bộ:**
  1. Tham số `from` trong `transferFrom` có nhận trực tiếp từ user input không?
  2. Có lệnh kiểm tra `msg.sender == from` hoặc kiểm tra allowance nội bộ của contract không?
  3. Hàm có nằm trong flow đã xác thực qua chữ ký EIP-712 / Permit hay không?
  4. Contract có vai trò là vault/router được ủy quyền quản lý theo thiết kế không?
- **Ngữ cảnh cần bóc tách:** Các lệnh `require(from == msg.sender)`, hàm bọc `SafeERC20`, chữ ký EIP-712.

### 3.3. `SOL-ORACLE-MANIP-001`: Spot Price Oracle Manipulation
- **Mô tả:** Giao thức định giá tài sản hoặc tính toán thế chấp dựa trên số dư reserves tức thời của pool AMM (e.g., Uniswap v2 `reserves0 / reserves1`) thay vì TWAP hoặc Chainlink feeds.
- **Rủi ro:** Kẻ tấn công dùng Flash Loan thay đổi tỉ giá pool trong 1 transaction rồi thanh lý hoặc mint tài sản sai giá.
- **Checklist sơ bộ:**
  1. Hàm định giá có đọc trực tiếp từ `balanceOf()` hoặc `getReserves()` của pool không?
  2. Giao thức có sử dụng TWAP (Time-Weighted Average Price) hoặc Chainlink Data Feed không?
  3. Giá trị tính toán có được dùng cho quyết định tài chính quan trọng (borrow, mint, liquidate)?
  4. Window lấy mẫu TWAP có đủ dài (>= 30 phút) để kháng Flash Loan không?
- **Ngữ cảnh cần bóc tách:** Import Chainlink `AggregatorV3Interface`, Uniswap TWAP Oracle library, window duration.

### 3.4. `SOL-UNCHECKED-RETURN-001`: Unchecked Low-level Call / Transfer Return
- **Mô tả:** Lệnh gọi `.call()`, `.send()`, hoặc `IERC20.transfer()` không kiểm tra giá trị trả về (`bool success`).
- **Rủi ro:** Chuyển token thất bại nhưng giao dịch vẫn tiếp tục, dẫn đến việc người dùng nhận được hàng/credit mà không phải trả tiền.
- **Checklist sơ bộ:**
  1. Lệnh gọi low-level `.call` hoặc token call có bỏ qua giá trị trả về `(bool ok, )` không?
  2. Có lệnh `require(ok, ...)` hoặc `if (!ok) revert(...)` ngay sau lệnh gọi không?
  3. Thư viện `SafeERC20` của OpenZeppelin có được sử dụng (`using SafeERC20 for IERC20`) không?
  4. Token được chuyển có phải là non-standard ERC20 (e.g., USDT không trả boolean) không?
- **Ngữ cảnh cần bóc tách:** `using SafeERC20 for IERC20`, `safeTransfer()`, `SafeTransferLib`.

### 3.5. `SOL-SIG-REPLAY-001`: Signature Malleability & Replay
- **Mô tả:** Hàm xác thực chữ ký cryptographic bằng `ecrecover` mà không có `nonce`, `deadline`, hoặc `DOMAIN_SEPARATOR` theo chuẩn EIP-712.
- **Rủi ro:** Chữ ký đã dùng có thể bị gửi lại nhiều lần (replay attack) hoặc dùng lại trên chain khác.
- **Checklist sơ bộ:**
  1. Hàm có sử dụng chữ ký để cấp quyền hoặc thực hiện hành động tài chính không?
  2. Có biến `nonces[signer]++` được cập nhật sau khi xác thực chữ ký thành công không?
  3. Hash của message có chứa `block.chainid` và contract address (EIP-712 `DOMAIN_SEPARATOR`) không?
  4. Thư viện `ECDSA` của OpenZeppelin có được dùng để chống malleable `s` value không?
- **Ngữ cảnh cần bóc tách:** OpenZeppelin `ECDSA`, `EIP712`, mapping `nonces`, expiry timestamp checks.

---

## 4. Kế Hoạch Thực Hiện & Phân Công Giai Đoạn 4 (02/11 – 15/11/2026)

| Giai Đoạn | Mục Tiêu | Deliverables | Thời Hạn |
| :--- | :--- | :--- | :---: |
| **Tuần 1 (02–08/11)** | Triển khai Đợt 4A: 2 pattern tương tác ngoại (`DELEGATECALL` & `ARBITRARY-FROM`) | - 2 bộ checklist mới.<br>- 30 test cases mới (15 cases/pattern).<br>- Cập nhật `context_assembler.py`. | 08/11/2026 |
| **Tuần 2 (09–15/11)** | Triển khai Đợt 4B: 2 pattern kinh tế DeFi (`ORACLE-MANIP` & `UNCHECKED-RETURN`) | - 2 bộ checklist mới.<br>- 31 test cases mới.<br>- Đóng gói Dataset v3 (70+ cases toàn bộ).<br>- Chạy `run_regression_suite.py` hoàn chỉnh. | 15/11/2026 |

---

## 5. Hướng Dẫn Kích Hoạt Regression Suite Trước Khi Merge Pattern Mới

Mỗi khi bổ sung pattern mới vào hệ thống, lập trình viên bắt buộc phải chạy lệnh sau:

```bash
# Chạy bộ hồi quy tự động hoàn chỉnh
python scripts/run_regression_suite.py
```

Nếu tất cả 13+ Invariants hiển thị `[✓ PASS]` và kết luận là `TẤT CẢ INVARIANTS ĐẠT YÊU CẦU ✅`, pattern mới được phép merge vào pipeline chính.
