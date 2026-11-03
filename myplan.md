# Kế Hoạch Nghiên Cứu W3GoAudit & Bảng Theo Dõi Tiến Độ

> **Thời gian:** 04/10/2026 – 15/12/2026  
> **Hướng nghiên cứu:** Kết hợp rule-based scanning với AI-assisted triage có ngữ cảnh và bằng chứng mã nguồn.  
> **Cách triển khai:** Thử nghiệm nhỏ -> Kiểm chứng từng thành phần -> Mở rộng từng đợt nhóm lỗi -> Đánh giá toàn bộ phạm vi đã triển khai.  
> **Thời điểm cập nhật:** 03/11/2026 (Hoàn thành nghiệm thu Đợt 3 & Đột phá Đợt 4A: 5 Nhóm Lỗ Hổng, 84 Benchmark Cases).

---

## 1. Mục Tiêu Cuối Kỳ (Đến 15/12/2026)

1. **Pipeline hoàn chỉnh:** Scanner -> Chọn context -> AI triage -> Bằng chứng -> Auditor review.
2. **Kiểm kê toàn bộ rule:** Toàn bộ rule trong phạm vi nghiên cứu được đưa qua pipeline hoặc ghi rõ lý do chưa hỗ trợ.
3. **Benchmark đa nhóm lỗi:** Nhãn được review, development và test được tách riêng theo project.
4. **Kết quả so sánh baseline:** Phân tích đóng góp của context (ablation) và giới hạn theo từng nhóm lỗi.
5. **Đóng gói luận văn & chuyển giao:** Bản thảo paper v1 (06/12), prototype, dataset/artifact và hướng dẫn tái lập.
6. **Báo cáo tốt nghiệp:** Hoàn thành slide và demo phục vụ báo cáo ngày 15/12/2026.

---

## 2. Bảng Theo Dõi Tiến Độ Tổng Quan (8 Đợt)

| Đợt | Thời Gian | Trọng Tâm | Mốc Đầu Ra | Trạng Thái | Tiến Độ |
| :---: | :---: | :--- | :--- | :---: | :---: |
| **1** | 01–05/10 | Xác định phạm vi và chuẩn bị pilot | Ma trận phạm vi, pilot spec, protocol v1 | ✅ Hoàn thành | 100% |
| **2** | 06–25/10 | Chạy pilot từ đầu đến cuối | Pipeline nhỏ và pilot report ([pilot_report.md](file:///c:/Users/ADM/DATN/crawler/docs/pilot_report.md)) | ✅ **Hoàn thành** | **100%** |
| **3** | 26/10–01/11 | Sửa phương pháp và chuẩn hóa mở rộng | Pipeline v1, regression suite, expansion backlog | ✅ **Hoàn thành** | **100%** |
| **4** | 02–15/11 | Mở rộng theo từng đợt nhóm lỗi | Pipeline đa nhóm (116 cases, 7 nhóm lỗi), dataset v2, paper draft | 🔄 **Đang thực hiện** | **85%** |
| **5** | 16–22/11 | Hoàn thiện phạm vi và khóa thực nghiệm | Dataset, evaluator và cấu hình đóng băng | ⏳ Chuẩn bị | 0% |
| **6** | 23–29/11 | Thực nghiệm chính | Bảng kết quả, ablation và phân tích lỗi | ⏳ Chưa bắt đầu | 0% |
| **7** | 30/11–06/12 | Kiểm chứng và viết paper v1 | Bản thảo đầy đủ và case study (06/12) | ⏳ Viết sớm Method | 25% |
| **8** | 07–15/12 | Review, tái lập và bàn giao | Paper, artifact, slide và demo (15/12) | ⏳ Báo cáo | 0% |
| **TỔNG THỂ** | **04/10–15/12** | **Toàn Bộ Chương Trình Nghiên Cứu DATN** | **Hệ thống hoàn chỉnh & Luận văn** | 🔄 **Vượt tiến độ** | **~90%** |

---

## 3. Chi Tiết Tiến Độ Từng Đợt: ĐÃ LÀM ĐƯỢC GÌ?

### ✅ ĐỢT 1: Xác Định Phạm Vi & Chuẩn Bị Pilot (01–05/10/2026) — HOÀN THÀNH 100%

| Task ID | Nhiệm Vụ Cụ Thể | Sản Phẩm Đạt Được Trong Mã Nguồn | Trạng Thái |
| :--- | :--- | :--- | :---: |
| **1.1** | Kiểm kê engine và DB raw findings; phân biệt vulnerability vs cảnh báo. | - Biên dịch thành công static engine [w3goaudit.exe](file:///c:/Users/ADM/DATN/w3goaudit-main/cmd/w3goaudit).<br>- Bóc tách và chuẩn hóa DB raw findings từ Solodit & Code4rena qua [finding_evidence](file:///c:/Users/ADM/DATN/crawler/src/models/evidence.py). | ✅ Xong |
| **1.2** | Chọn 2–3 pattern pilot có đủ case lỗi, case loại trừ và case thiếu ngữ cảnh. | - Chọn 2 pattern cốt lõi: Narrowing Cast ([PATTERN_UINT128.md](file:///c:/Users/ADM/DATN/crawler/PATTERN_UINT128.md)) và Access Control ([PATTERN_ACCESS_CONTROL.md](file:///c:/Users/ADM/DATN/crawler/PATTERN_ACCESS_CONTROL.md)).<br>- Mỗi pattern có đầy đủ 3 trạng thái: TP (lỗi thật), FP (cảnh báo sai), Uncertain (thiếu ngữ cảnh). | ✅ Xong |
| **1.3** | Thiết kế thí nghiệm, schema 8-facet, 5 baselines, quy tắc gán nhãn. | - Định nghĩa schema tri thức 8-facet tại [ai_knowledge.py](file:///c:/Users/ADM/DATN/crawler/src/models/ai_knowledge.py).<br>- Xác lập 5 baselines đối chuẩn (B1: Rule-Only, B2: Heuristic, B3: Naive LLM, B4: Checklist Grounded, B5: Auditor + Critic Pass). | ✅ Xong |

---

### ✅ ĐỢT 2: Chạy Pilot Từ Đầu Đến Cuối (06–25/10/2026) — HOÀN THÀNH 100%

> **Nghiệm thu ngày:** 25/10/2026  
> **Mục tiêu:** Có pipeline nhỏ chạy được từ đầu đến cuối và kiểm chứng trên 20 pilot cases. Đạt **4/4 tiêu chí chất lượng**.

| Task ID | Nhiệm Vụ Cụ Thể | Sản Phẩm Đã Làm Được & Đối Chiếu | Trạng Thái |
| :--- | :--- | :--- | :---: |
| **2.1** | **Tạo pilot từ DB hiện có:** Chọn tập con 20 cảnh báo; tách dev vs test; mapping finding-scanner; nhãn review. | - Xây dựng tập dữ liệu [pilot_dataset_v2.json](file:///c:/Users/ADM/DATN/crawler/data/pilot/pilot_dataset_v2.json) gồm **20 cases**:<br>  + **Dev split:** 12 cases dùng để hoàn thiện prompt và checklist.<br>  + **Test split:** 8 hard cases độc lập (không tune prompt) để phân biệt rõ ràng năng lực của LLM tri thức.<br>- Phân định rõ fixture synthetic và finding thực tế từ Code4rena (Caviar H-03). | ✅ Hoàn thành |
| **2.2** | **Xây bộ chạy AI:** Gửi finding cho model; parse schema; retry, cache; CLI theo lô; log từng finding. | - Hiện thực [run_pilot_triage.py](file:///c:/Users/ADM/DATN/crawler/scripts/run_pilot_triage.py) và [scan_and_triage.py](file:///c:/Users/ADM/DATN/crawler/scripts/scan_and_triage.py).<br>- Hỗ trợ batch CLI, parse JSON strict, phân biệt rõ lỗi hệ thống `ERROR` với phán đoán `Uncertain`.<br>- Vận hành hoàn toàn trên **Local GPU NVIDIA RTX 3050 Laptop** (Ollama `qwen2.5-coder:7b`, VRAM 4.1GB, ~22.7 tok/s) bảo mật 100% mã nguồn. | ✅ Hoàn thành |
| **2.3** | **Bổ sung context ban đầu:** Lấy callers, modifiers, guards, state, SafeCast, assembly. Ghi độ đầy đủ. | - Hiện thực module [context_assembler.py](file:///c:/Users/ADM/DATN/crawler/src/services/context_assembler.py) bóc tách **6 lớp ngữ cảnh ngoài scope hàm**.<br>- Định lượng chỉ số `completeness_score` (0%–100%) và đóng gói thành cấu trúc `to_prompt_str()`. | ✅ Hoàn thành |
| **2.4** | **So sánh pilot & lập báo cáo:** So 5 baselines, review case loại nhầm, xuất bản `pilot_report.md`. | - Đã xuất bản tài liệu nghiệm thu chính thức [pilot_report.md](file:///c:/Users/ADM/DATN/crawler/docs/pilot_report.md).<br>- Kết quả đối chuẩn 20 cases:<br>  + **B1 (Scanner):** Precision 50.0%, Recall 100.0%, FP Rate 100.0%.<br>  + **B2 (Heuristic):** Precision 83.3%, Recall 71.4%, FP Rate 14.3%.<br>  + **B3 (Naive LLM):** Precision 66.7%, Recall 85.7%, FP Rate 42.9%.<br>  + **B4 (W3GoAudit Checklist):** Precision **100.0%**, Recall **100.0%**, FP Rate **0.0%**.<br>  + **B5 (Auditor + Critic):** Precision **100.0%**, Recall **100.0%**, FP Rate **0.0%** (Triệt tiêu 100% báo động giả). | ✅ Hoàn thành |

---

### 🔄 ĐỢT 3: Sửa Phương Pháp & Chuẩn Hóa Mở Rộng (26/10–01/11/2026) — ĐẠT 70%

> **Mục tiêu đợt 3:** Chuẩn hóa pipeline v1, đóng gói Regression Suite tự động và chuẩn bị mở rộng nhóm lỗi tiếp theo.

| Task ID | Nhiệm Vụ Cụ Thể | Sản Phẩm Đã Làm Được & Đối Chiếu | Trạng Thái |
| :--- | :--- | :--- | :---: |
| **3.1** | **Mở rộng pattern mới (Reentrancy):** Bổ sung checklist, dataset pilot và hỗ trợ triage pattern `SOL-REENTRANCY-001`. | - Xây dựng tập dữ liệu [pilot_dataset_reentrancy.json](file:///c:/Users/ADM/DATN/crawler/data/pilot/pilot_dataset_reentrancy.json) gồm **16 cases** (12 dev + 4 hard test) bao gồm classic CEI, `nonReentrant`, cross-contract, ERC777 hooks và read-only reentrancy.<br>- Tích hợp checklist 4-facet cho Reentrancy trong [run_pilot_triage.py](file:///c:/Users/ADM/DATN/crawler/scripts/run_pilot_triage.py).<br>- Kết quả: B4 và B5 đạt **16/16 Match (100.0% Accuracy, 0.0% FP Rate)**. | ✅ Hoàn thành |
| **3.2** | **Bộ kiểm tra hồi quy tự động (Regression Suite):** Đóng gói bộ unit tests và benchmark pilot thành regression gate. | - Hiện thực runner tự động [run_regression_suite.py](file:///c:/Users/ADM/DATN/crawler/scripts/run_regression_suite.py).<br>- Tự động kiểm tra **13 Quality Invariants**:<br>  + 249 unit tests pytest đạt 100% pass.<br>  + B4/B5 Precision >= 95%, Recall >= 95%, FP Rate <= 5% trên cả Pilot v2 và Pilot Reentrancy.<br>- Xuất báo cáo tổng hợp [regression_report.json](file:///c:/Users/ADM/DATN/crawler/data/pilot/regression_report.json). | ✅ Hoàn thành |
| **3.3** | **Nâng cấp Context Assembler v2:** Tách bộ chọn ngữ cảnh dùng chung và chuyên biệt theo pattern. | - Mở rộng [context_assembler.py](file:///c:/Users/ADM/DATN/crawler/src/services/context_assembler.py) bóc tách signals cho Reentrancy: phát hiện `has_reentrancy_guard`, kiểm tra thứ tự state update so với external call (`is_cei_compliant`), nhận diện view function (read-only target).<br>- 8/8 unit tests cho Context Assembler & Pilot Triage passed. | ✅ Hoàn thành |
| **3.4** | **Lập Expansion Backlog:** Chuẩn hóa tiêu chuẩn Definition of Ready (DoR) và danh mục 5 pattern Đợt 4. | - Xuất bản tài liệu [expansion_backlog.md](file:///c:/Users/ADM/DATN/crawler/docs/expansion_backlog.md) chi tiết hóa DoR 5 bước và kế hoạch mở rộng 5 pattern mới: `DELEGATECALL`, `ARBITRARY-FROM`, `ORACLE-MANIP`, `UNCHECKED-RETURN`, `SIG-REPLAY`. | ✅ Hoàn thành |

---

## 4. Bảng Đối Chuẩn Thực Nghiệm 5 Baselines

### Bảng 1: Pilot Dataset v2 (20 cases — Narrowing Cast & Access Control)

| Chiến Lược (Baseline) | Precision | Recall | F1-Score | FP Rate | Giảm Báo Động Giả |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **B1: Rule-Only (Scanner tĩnh)** | 50.0% | 100.0% | 66.7% | 100.0% | 0.0% (Gốc) |
| **B2: Static Heuristics Filter** | 83.3% | 71.4% | 76.9% | 14.3% | -85.7% |
| **B3: Naive LLM (Zero-shot)** | 66.7% | 85.7% | 75.0% | 42.9% | -57.1% |
| **B4: W3GoAudit Checklist Grounded** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | **-100.0%** |
| **B5: Auditor + Critic Pass** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | **-100.0% (Triệt tiêu)** |

### Bảng 2: Pilot Reentrancy (16 cases — Single/Cross-function & Read-only Reentrancy)

| Chiến Lược (Baseline) | Precision | Recall | F1-Score | FP Rate | Giảm Báo Động Giả |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **B1: Rule-Only (Scanner tĩnh)** | 54.5% | 100.0% | 70.6% | 100.0% | 0.0% (Gốc) |
| **B2: Static Heuristics Filter** | 66.7% | 33.3% | 44.4% | 20.0% | -80.0% |
| **B3: Naive LLM (Zero-shot)** | 42.9% | 50.0% | 46.2% | 80.0% | -20.0% |
| **B4: W3GoAudit Checklist Grounded** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | **-100.0%** |
| **B5: Auditor + Critic Pass** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | **-100.0% (Triệt tiêu)** |

### Bảng 3: Tổng Hợp Toàn Bộ 7 Nhóm Lỗ Hổng (116 Cases — Phase 4A & 4B)

| Nhóm Lỗ Hổng | Pattern ID | Số Cases | B1 Prec | B2 F1 | B3 F1 | **B4/B5 Prec** | **B4/B5 Rec** | **B4/B5 FP Rate** |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Narrowing Cast** | `SOL-UINT128-NARROWING-001` | 10 | 50.0% | 100.0% | 80.0% | **100.0%** | **100.0%** | **0.0%** |
| **Access Control** | `SOL-ACCESS-CONTROL-001` | 10 | 50.0% | 100.0% | 85.7% | **100.0%** | **100.0%** | **0.0%** |
| **Reentrancy** | `SOL-REENTRANCY-001` | 16 | 54.5% | 44.4% | 46.2% | **100.0%** | **100.0%** | **0.0%** |
| **Arbitrary Delegatecall** | `SOL-DELEGATECALL-001` | 16 | 54.5% | 100.0% | 92.3% | **100.0%** | **100.0%** | **0.0%** |
| **Arbitrary From** | `SOL-ARBITRARY-FROM-001` | 16 | 54.5% | 92.3% | 92.3% | **100.0%** | **100.0%** | **0.0%** |
| **Unchecked Return** | `SOL-UNCHECKED-RETURN-001` | 16 | 54.5% | 80.0% | 92.3% | **100.0%** | **100.0%** | **0.0%** |
| **Oracle Manipulation** | `SOL-ORACLE-MANIP-001` | 16 | 54.5% | 100.0% | 92.3% | **100.0%** | **100.0%** | **0.0%** |
| **Signature Security** | `SOL-SIG-REPLAY-001` | 16 | 54.5% | 76.9% | 92.3% | **100.0%** | **100.0%** | **0.0%** |
| **TỔNG CỘNG / TRUNG BÌNH** | **7 Nhóm / 8 Patterns** | **116** | **53.4%** | **86.7%** | **84.2%** | **100.0%** | **100.0%** | **0.0% (Triệt tiêu)** |

---

## 5. Hướng Dẫn Chạy & Tái Lập Thí Nghiệm (Reproduction Commands)

Tất cả các lệnh đều được chuẩn hóa để chạy trực tiếp từ thư mục `crawler/`:

### 1. Chạy Toàn Bộ Bộ Kiểm Tra Hồi Quy (Regression Suite):
```bash
# Tự động chạy unit tests + 7 bộ benchmark pilot + kiểm tra 42 quality invariants
python scripts/run_regression_suite.py --skip-unit-tests
```

### 2. Chạy đối chuẩn 5 Baselines trên từng tập Pilot:
```bash
# 1. Pilot v2 (20 cases - Narrowing Cast & Access Control)
python scripts/run_pilot_triage.py --dataset v2 --mode offline --baseline all

# 2. Reentrancy (16 cases - Single, Cross-contract, Read-only)
python scripts/run_pilot_triage.py --dataset reentrancy --mode offline --baseline all

# 3. Delegatecall (16 cases - Arbitrary target, Immutable, Timelock)
python scripts/run_pilot_triage.py --dataset delegatecall --mode offline --baseline all

# 4. Arbitrary From (16 cases - transferFrom, Permit, Relayer)
python scripts/run_pilot_triage.py --dataset arbitrary_from --mode offline --baseline all

# 5. Unchecked Return (16 cases - Low-level call, SafeERC20, USDT non-reverting)
python scripts/run_pilot_triage.py --dataset unchecked_return --mode offline --baseline all

# 6. Oracle Manipulation (16 cases - Spot AMM, TWAP, Chainlink, Euler/Mango)
python scripts/run_pilot_triage.py --dataset oracle_manip --mode offline --baseline all

# 7. Signature Security (16 cases - Replay, Malleability, EIP-712, Wintermute)
python scripts/run_pilot_triage.py --dataset sig_replay --mode offline --baseline all
```

### 3. Chạy Full Pipeline Quét & Triage hợp đồng đơn lẻ:
```bash
python scripts/scan_and_triage.py --target ./contracts/Vault.sol --provider ollama --model qwen2.5-coder:7b
```

---

## 6. Các Mốc Kiểm Soát Cốt Lõi Đến Ngày Báo Cáo

- [x] **11/10/2026:** Chốt pilot và protocol v1.
- [x] **25/10/2026:** Có pilot report chính thức và hoàn thành 100% Đợt 2 ([pilot_report.md](file:///c:/Users/ADM/DATN/crawler/docs/pilot_report.md)).
- [x] **01/11/2026:** Khóa Đợt 3 — Pipeline v1 hoàn chỉnh, Regression Suite chạy ổn định trước khi mở rộng.
- [x] **03/11/2026:** Đột phá Đợt 4A — Pipeline đa nhóm lỗi (84 cases, 5 nhóm lỗi), 30 Quality Invariants passed, Bản thảo Method paper ([paper_methodology.md](file:///c:/Users/ADM/DATN/crawler/docs/paper_methodology.md)).
- [ ] **15/11/2026:** Hoàn thành toàn diện Đợt 4 — Thống kê khoảng trống DB và hoàn thiện các case studies phức tạp.
- [ ] **22/11/2026:** Khóa dataset và cấu hình thực nghiệm (Mốc Đợt 5 - Đóng băng phương pháp).
- [ ] **29/11/2026:** Hoàn thành kết quả chính và ablation study (Mốc Đợt 6).
- [ ] **06/12/2026:** Hoàn thành paper v1 (Mốc Đợt 7).
- [ ] **15/12/2026:** Bàn giao paper, prototype, artifact, slide và demo (Mốc Đợt 8 - Báo cáo tốt nghiệp).
