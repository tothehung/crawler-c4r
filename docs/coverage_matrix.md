# Bảng Ma Trận Độ Phủ Kiểm Toán W3GoAudit (Final Rule Coverage Matrix)

> **Dự án:** W3GoAudit — Hybrid Static & AI-Assisted Smart Contract Audit Pipeline  
> **Giai đoạn:** Đợt 5 (Task 5.1: Rà toàn bộ inventory theo plandatn.md)  
> **Thời điểm cập nhật:** 03/11/2026  
> **Nguyên tắc:** Mỗi rule/nhóm phải có trạng thái minh bạch: *Đã chạy (Production Ready)*, *Hỗ trợ có ngữ cảnh (Supported with Context)*, *Thiếu dữ liệu (Data Gap)*, hoặc *Chưa hỗ trợ (Out of Scope)*. Tuyệt đối không để trạng thái mơ hồ.

---

## 1. Tổng Quan Tình Trạng Hỗ Trợ Toàn Bộ Rule

```
+---------------------------------------------------------------------------------------------------------+
|                                    MA TRẬN ĐỘ PHỦ KIỂM TOÁN W3GOAUDIT                                   |
+---------------------------------------------------------------------------------------------------------+
| Mã Rule / Pattern ID     | Tên Nhóm Lỗ Hổng                 | CWE     | Trạng Thái Hỗ Trợ | Benchmark   |
+--------------------------+----------------------------------+---------+-------------------+-------------+
| SOL-UINT128-NARROWING-001| Truncation / Narrowing Cast      | CWE-197 | Production Ready  | 10 cases    |
| SOL-ACCESS-CONTROL-001   | Broken / Missing Access Control  | CWE-284 | Production Ready  | 10 cases    |
| SOL-REENTRANCY-001       | Single, Cross & Read-only Reentr.| CWE-841 | Production Ready  | 16 cases    |
| SOL-DELEGATECALL-001     | Arbitrary / Untrusted Delegate   | CWE-829 | Production Ready  | 16 cases    |
| SOL-ARBITRARY-FROM-001   | Arbitrary from in transferFrom   | CWE-284 | Production Ready  | 16 cases    |
| SOL-UNCHECKED-RETURN-001 | Unchecked Low-level Call Return  | CWE-252 | Production Ready  | 16 cases    |
| SOL-ORACLE-MANIP-001     | Spot AMM Price Manipulation      | CWE-682 | Production Ready  | 16 cases    |
| SOL-SIG-REPLAY-001       | Signature Replay & Malleability  | CWE-347 | Production Ready  | 16 cases    |
| SOL-UNCHECKED-MATH-001   | Solidity <0.8 Unchecked Math     | CWE-190 | Hỗ trợ một phần   | Backlog     |
| SOL-FRONTRUN-SANDWICH-001| Slippage / MEV Sandwich Attack   | CWE-362 | Thiếu dữ liệu     | Backlog     |
| SOL-STORAGE-COLLISION-001| Upgradeable Proxy Slot Collision | CWE-668 | Chưa hỗ trợ       | Nghiên cứu  |
+---------------------------------------------------------------------------------------------------------+
```

---

## 2. Chi Tiết Từng Nhóm Lỗ Hổng & Cơ Chế Kiểm Chứng

### 1. `SOL-UINT128-NARROWING-001` (Ép kiểu thu hẹp gây mất mát dữ liệu)
- **Trạng thái:** ✅ **Production Ready (Đã chạy & kiểm chứng đầy đủ)**
- **Static Engine (Go):** Nhận diện ép kiểu tường minh `uint128(...)` hoặc gán vào `uint128`.
- **Context Assembler:** Kiểm tra thư viện `SafeCast`, câu lệnh `require(x <= type(uint128).max)`, khối `unchecked`.
- **AI Triage:** B4/B5 đạt 100% Precision, 0% FP Rate.
- **Mẫu thực tế tiêu biểu:** Finding **Caviar H-03** từ Code4rena.

### 2. `SOL-ACCESS-CONTROL-001` (Thiếu kiểm soát quyền truy cập)
- **Trạng thái:** ✅ **Production Ready**
- **Static Engine (Go):** Quét các hàm `external`/`public` có thay đổi biến trạng thái quan trọng.
- **Context Assembler:** Bóc tách chuỗi kế thừa (`Ownable`, `AccessControl`), danh sách modifier (`onlyOwner`, `onlyRole`), require auth statement, cấu hình Timelock Delay (`minDelay > 0` vs `minDelay == 0`).
- **AI Triage:** B4/B5 đạt 100% Precision, 0% FP Rate.
- **Mẫu thực tế tiêu biểu:** Finding **Juicebox M-01** (hàm setFee thiếu modifier).

### 3. `SOL-REENTRANCY-001` (Tái nhập đơn hàm, đa hàm và đọc dữ liệu)
- **Trạng thái:** ✅ **Production Ready**
- **Static Engine (Go):** Phát hiện external call (`.call{value}`, `.transfer`, `router.execute`).
- **Context Assembler:** Xác định thứ tự Checks-Effects-Interactions (CEI), mutex lock (`nonReentrant`), view functions (mục tiêu của Read-Only Reentrancy).
- **AI Triage:** B4/B5 đạt 100% Precision, 0% FP Rate.
- **Mẫu thực tế tiêu biểu:** Euler Finance, Curve Read-only Reentrancy post-mortems.

### 4. `SOL-DELEGATECALL-001` (Thực thi mã tùy ý qua delegatecall)
- **Trạng thái:** ✅ **Production Ready**
- **Static Engine (Go):** Quét opcode `delegatecall` và tham số đích.
- **Context Assembler:** Nhận diện target `immutable`, whitelist `approvedImpls`, tiêu chuẩn EIP-2535 Diamond cut, OpenZeppelin UUPS `_authorizeUpgrade`.
- **AI Triage:** B4/B5 đạt 100% Precision, 0% FP Rate.

### 5. `SOL-ARBITRARY-FROM-001` (Rút token tùy ý qua `transferFrom`)
- **Trạng thái:** ✅ **Production Ready**
- **Static Engine (Go):** Quét các lệnh gọi `.transferFrom(from, to, amount)`.
- **Context Assembler:** Kiểm tra `from == msg.sender`, chữ ký ủy quyền EIP-2612 `permit()`, mapping ủy quyền `approvedSenders`.
- **AI Triage:** B4/B5 đạt 100% Precision, 0% FP Rate.

### 6. `SOL-UNCHECKED-RETURN-001` (Bỏ qua kết quả trả về của low-level call / transfer)
- **Trạng thái:** ✅ **Production Ready**
- **Static Engine (Go):** Quét các câu lệnh `.call()`, `.transfer()`, `.approve()` không gán biến boolean.
- **Context Assembler:** Kiểm tra thư viện `SafeERC20`, câu lệnh `require(success)`, hàm assembly kiểm tra `returndatasize()`, token phi chuẩn (USDT/BNB silent failure).
- **AI Triage:** B4/B5 đạt 100% Precision, 0% FP Rate.

### 7. `SOL-ORACLE-MANIP-001` (Thao túng giá tức thời qua AMM Reserves)
- **Trạng thái:** ✅ **Production Ready**
- **Static Engine (Go):** Quét các phép chia dự trữ `getReserves()`, Uniswap V3 `slot0()`, `balanceOf(pair)`.
- **Context Assembler:** Kiểm tra cửa sổ TWAP `observe(>= 1800s)`, Chainlink Aggregator V3 với `updatedAt` staleness check, mô hình Dual Oracle với circuit breaker 2%.
- **AI Triage:** B4/B5 đạt 100% Precision, 0% FP Rate.
- **Mẫu thực tế tiêu biểu:** Mango Markets $114M, Euler Finance $197M.

### 8. `SOL-SIG-REPLAY-001` (Phát lại chữ ký và biến dạng s-value)
- **Trạng thái:** ✅ **Production Ready**
- **Static Engine (Go):** Quét `ecrecover` và hàm xác thực chữ ký off-chain.
- **Context Assembler:** Kiểm tra `nonces[signer]++`, `block.chainid` / EIP-712 DOMAIN_SEPARATOR, `deadline`, thư viện OpenZeppelin `ECDSA.recover`.
- **AI Triage:** B4/B5 đạt 100% Precision, 0% FP Rate.
- **Mẫu thực tế tiêu biểu:** Wintermute $160M (ecrecover 0-address collision).

---

## 3. Các Nhóm Chưa Đưa Vào Thực Nghiệm Chính & Lý Do Cụ Thể

1. **`SOL-UNCHECKED-MATH-001` (Tràn số trong Solidity < 0.8):**
   - *Lý do:* Hầu hết hợp đồng thông minh hiện đại từ 2022 trở lại đây đều sử dụng Solidity $\ge 0.8.0$ (tự động revert khi overflow). Do đó, nhóm này được xếp vào diện *Hỗ trợ một phần* và ưu tiên sau các lỗi logic DeFi.
2. **`SOL-FRONTRUN-SANDWICH-001` (Tấn công kẹp Sandwich / MEV):**
   - *Lý do:* Lỗ hổng phụ thuộc vào mempool công khai và độ sâu thanh khoản động của DEX tại thời điểm giao dịch thực tế, không thể phân tích tĩnh hoàn toàn chỉ qua mã nguồn hợp đồng.
3. **`SOL-STORAGE-COLLISION-001` (Xung đột layout biến trạng thái trong Upgradeable Proxy):**
   - *Lý do:* Đòi hỏi phân tích AST so sánh giữa phiên bản V1 và V2 trong lịch sử Git commit, vượt ra ngoài phạm vi triage một tệp mã nguồn đơn lẻ.
