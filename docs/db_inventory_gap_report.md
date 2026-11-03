# Báo Cáo Kiểm Kê Dữ Liệu & Phân Tích Khoảng Trống (DB Inventory & Gap Report)

> **Dự án:** W3GoAudit — AI-Assisted Smart Contract Triage  
> **Giai đoạn:** Đợt 4 (Task 4.3: Mở rộng mẫu từ DB và review) & Chuẩn bị Đợt 5 (Task 5.1: Coverage Matrix)  
> **Thời điểm lập:** 03/11/2026  
> **Trạng thái:** Hoàn thành kiểm kê toàn diện  

---

## 1. Mục Đích & Nguyên Tắc Theo Kế Hoạch DATN

Theo quy định trong bản kế hoạch [`plandatn.md`](file:///c:/Users/ADM/DATN/plandatn.md):
- **Tái sử dụng DB hiện hữu làm trọng tâm:** Ưu tiên kho dữ liệu raw audit findings đã thu thập từ Code4rena và Solodit; không áp đặt chỉ tiêu crawl mới nếu DB hiện tại đã đủ đa dạng.
- **Tách biệt minh bạch giữa Real Findings và Synthetic Fixtures:** Các ca kiểm thử tổng hợp (synthetic) được gắn nhãn độc lập để kiểm chứng các điều kiện biên (edge cases) và phân biệt khả năng giữa các mô hình AI; tuyệt đối không tính gộp synthetic làm thay cho finding thực tế.
- **Không ép nhãn (No Forced Binary Labeling):** Mẫu thiếu bằng chứng ngữ cảnh bắt buộc phải được gắn nhãn `Uncertain`. Nhãn `Uncertain` của ground truth phản ánh giới hạn tri thức khách quan, phân biệt rõ với trạng thái lỗi vận hành hệ thống (`ERROR`).

---

## 2. Kiểm Kê Kho Dữ Liệu Hiện Hữu (Raw Findings DB Inventory)

Hệ thống W3GoAudit hiện lưu trữ và quản lý các nguồn dữ liệu kiểm toán sau:

| Tên File / Kho Dữ Liệu | Định Dạng | Số Bản Ghi | Nội Dung Cốt Lõi |
| :--- | :---: | :---: | :--- |
| [`data/findings_code4rena.jsonl`](file:///c:/Users/ADM/DATN/crawler/data/findings_code4rena.jsonl) | JSONL (1.17 MB) | **117** | Raw audit findings thu thập từ các cuộc thi Code4rena hàng đầu (Juicebox V2/V3, Uniswap V3 Buyback Delegate, Caviar AMM, v.v.). |
| [`data/processed/ai_grounded_knowledge_all.json`](file:///c:/Users/ADM/DATN/crawler/data/processed/ai_grounded_knowledge_all.json) | JSON (276 KB) | **35** | Tri thức kiểm toán đã phân rã thành **Schema 8-facet** (Pattern, Necessary, Sufficient, Trigger, Checklist, Remediation, Missing Signals). |
| [`data/findings.db`](file:///c:/Users/ADM/DATN/crawler/data/findings.db) | SQLite (61 KB) | — | Cơ sở dữ liệu quan hệ lưu trữ findings, evidence links và audit report hashes. |
| [`data/checkpoints/phase4-replay.sqlite3`](file:///c:/Users/ADM/DATN/crawler/data/checkpoints/phase4-replay.sqlite3) | SQLite (1.46 MB) | — | Trace lưu trữ toàn bộ các phiên replay kiểm tra tính tất định của engine và LLM outputs. |

### Phân Bố 117 Real Raw Findings trong `findings_code4rena.jsonl`:
- **Logic & Protocol Constraint Violations:** 63 findings (53.8%)
- **Missing / Broken Access Control:** 22 findings (18.8%)
- **Unchecked Call & Return Values:** 22 findings (18.8%)
- **Arithmetic & Narrowing Typecast:** 5 findings (4.3%)
- **Signature Security & Replay:** 4 findings (3.4%)
- **Reentrancy:** 1 finding (0.9%)

---

## 3. Phân Tích Khoảng Trống Dữ Liệu Theo Từng Nhóm Lỗ Hổng (Gap Analysis)

Dựa trên đối chiếu giữa **Năng lực bóc tách của Static Scanner (W3GoAudit Go Engine)** và **Dữ liệu thực tế trong DB**:

```
+---------------------------------------------------------------------------------------+
|                            MA TRẬN KHOẢNG TRỐNG DỮ LIỆU                              |
+---------------------------------------------------------------------------------------+
| Nhóm Lỗ Hổng             | Độ Sẵn Sàng DB | Dữ Liệu Thực Tế | Nhu Cầu Fixture Bổ Trợ  |
+--------------------------+----------------+-----------------+-------------------------+
| SOL-ACCESS-CONTROL-001   | Rất dồi dào    | 22 findings     | 6 dev + 4 hard test     |
| SOL-UNCHECKED-RETURN-001 | Rất dồi dào    | 22 findings     | 12 dev + 4 hard test    |
| SOL-UINT128-NARROWING-001| Trung bình     | 5 findings      | 6 dev + 4 hard test     |
| SOL-SIG-REPLAY-001       | Trung bình     | 4 findings      | 12 dev + 4 hard test    |
| SOL-REENTRANCY-001       | Hạn chế trong DB| 1 finding       | 12 dev + 4 hard test    |
| SOL-DELEGATECALL-001     | Hạn chế trong DB| 0 finding       | 12 dev + 4 hard test    |
| SOL-ORACLE-MANIP-001     | Hạn chế trong DB| 0 finding       | 12 dev + 4 hard test    |
+---------------------------------------------------------------------------------------+
```

### Chi tiết đánh giá khoảng trống:

1. **Nhóm Access Control & Unchecked Return (Đã đủ dữ liệu):**
   - Kho DB có sẵn 22 findings thực tế cho mỗi nhóm.
   - Các finding này cung cấp đầy đủ các mẫu code thực tế trong Juicebox (hàm set fee thiếu onlyOwner, transfer return không kiểm tra).

2. **Nhóm Narrowing Cast & Signature (Đủ cho Pilot, cần theo dõi):**
   - Đã có finding thực tế như **Caviar H-03** (Narrowing cast `uint256 -> uint128` gây kẹt token).
   - Đã có finding về permit signature trong Juicebox.

3. **Nhóm Reentrancy, Delegatecall và Oracle Manipulation (Xác định Khoảng Trống Cụ Thể):**
   - *Lý do thiếu trong tập Code4rena hiện tại:* Các cuộc thi crawl ban đầu tập trung vào giao thức quản trị và delegate (Juicebox). Các giao thức lending và AMM phức tạp (Euler, Mango, Cream) không nằm trong tập contest nhỏ ban đầu.
   - *Biện pháp giải quyết theo đúng nguyên tắc mục 4.3 trong kế hoạch:*
     - **Không crawl ồ ạt:** Tận dụng tri thức từ các vụ exploit post-mortem thực tế trong lịch sử Web3 (Euler $197M, Mango $114M, Sentiment $1M, Wintermute $160M) để xây dựng bộ kiểm thử có căn cứ thực tế vững chắc.
     - Tách riêng nhãn `fixture_kind: "synthetic"` trong [`benchmark_manifest.json`](file:///c:/Users/ADM/DATN/crawler/data/pilot/benchmark_manifest.json).
     - Ghi rõ giới hạn này trong báo cáo tốt nghiệp: *Bộ test cases của nhóm DeFi nâng cao được mô phỏng theo cấu trúc mã nguồn thực tế của các vụ khai thác lớn thay vì crawl ngẫu nhiên.*

---

## 4. Thống Kê Phân Bố Nhãn Benchmark Toàn Diện (116 Cases)

File Manifest chính thức: [`data/pilot/benchmark_manifest.json`](file:///c:/Users/ADM/DATN/crawler/data/pilot/benchmark_manifest.json)

- **Tổng số ca kiểm thử:** **116 cases**
- **Phân bố nhãn Ground Truth:**
  - **True Positive (TP):** 43 cases (37.1%) — Lỗ hổng có thể khai thác được.
  - **False Positive (FP):** 37 cases (31.9%) — Báo động giả của scanner đã được bảo vệ bởi guard, thư viện, hoặc thiết kế an toàn.
  - **Uncertain:** 36 cases (31.0%) — Thiếu thông tin ngoài phạm vi hàm (hàm internal, abstract interface, thiếu cấu hình delay timelock).
- **Phân bố Split:**
  - **Development Split (`dev`):** 84 cases (72.4%) — Dùng để hoàn thiện checklist 4 câu hỏi và trích xuất ngữ cảnh.
  - **Held-out Test Split (`test`):** 32 hard cases (27.6%) — Tuyệt đối độc lập, không dùng để tune prompt/rule, dùng để đối chuẩn năng lực thực tế.

---

## 5. Kết Luận & Định Hướng Đợt 5

1. Kho dữ liệu hiện tại **hoàn toàn đáp ứng đủ yêu cầu nghiên cứu** của toàn bộ Đề án Tốt nghiệp mà không cần mở rộng thêm API crawl bên ngoài.
2. Việc phân định rạch ròi giữa 3 nhãn $\{ \text{TP}, \text{FP}, \text{Uncertain} \}$ bảo đảm tính liêm chính học thuật (academic integrity) theo đúng tiêu chuẩn công bố khoa học.
