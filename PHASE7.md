# Phase 7 — knowledge cho finding/evidence

Pilot thứ hai: [PATTERN_ACCESS_CONTROL.md](PATTERN_ACCESS_CONTROL.md), mẫu thiếu
kiểm soát quyền trên setter cấu hình. Có ba loại case và 24 giao dịch EVM local.
Nguồn Sherlock bổ sung được giữ riêng, chưa nhập database/corpus 34 findings.

Phạm vi đã được người dùng điều chỉnh: **chỉ tạo kiến thức cho finding/evidence**.
Không triển khai embedding, vector database, chunking hoặc retrieval trong đợt này.
Không gọi model API trả phí. Phase 8/WQL cũng chưa bắt đầu.

Bổ sung pilot phục vụ audit pipeline: [PATTERN_UINT128.md](PATTERN_UINT128.md).
Một pattern có đủ tám nhóm kiến thức, ba nhãn case (có lỗi, loại trừ theo pattern,
thiếu ngữ cảnh), và 156 giao dịch kiểm chứng trên EVM local. Gói pattern liên kết
revision/evidence hiện có, giữ trạng thái candidate và phân biệt fixture synthetic
với evidence đã cào. Chưa tích hợp LLM hoặc thay đổi engine.

## Dữ liệu và kết quả

Mỗi bản knowledge có tám nhóm: root cause, preconditions, exploit conditions,
observed behavior, impact, detection signals, remediation và limitations.
Mỗi claim chứa nội dung, snapshot nguồn, khoảng dòng và quote nguyên văn để
kiểm tra lại. Claim có thể trỏ trực tiếp tới finding-evidence link.

Knowledge liên kết tới `finding_evidence_links` và `code_evidence` hiện có.
Lưu binding link → evidence ID lúc tạo revision. Nếu retry sau đó làm link
trỏ tới evidence khác, export/review yêu cầu rebuild thay vì gắn tri thức cũ
âm thầm vào code mới. Evidence ID, code, parser annotation và finding gốc
không bị chỉnh sửa bởi phase này.

- `knowledge_revisions`: nội dung có hash, version, dẫn chứng và review status.
- `knowledge_heads`: revision mới nhất của một native source finding.
- `knowledge_builds`: fingerprint đầu vào để chạy lại không nhân đôi revision.
- `knowledge_review_events`: lịch sử quyết định, người review, lý do, thời gian.

Schema v1 `knowledge_candidates` cũ được giữ nguyên. Bốn bảng bổ sung hỗ trợ
exact citations, hành vi lỗi và review history mà schema cũ chưa biểu diễn đủ.
Không tự gộp tri thức giữa hai nguồn chỉ vì phase 6 nhận diện finding trùng;
những khác biệt/nhận định trái nhau giữa báo cáo vẫn cần review.

## Tạo candidate

Extractor `report-extractive-v1` lấy paragraph theo Markdown AST và phân loại
bằng heading của báo cáo. Claim tự động là đoạn trích, không phải kết luận
ngữ nghĩa do model tạo ra. Phần thiếu được ghi trong `missing_information`;
mọi bản tự động có cờ `semantic_review_required`. Giới hạn 80 paragraph mỗi
finding, vượt giới hạn được báo rõ. Code block không tự biến thành rule.

```powershell
# Từ E:\dacn\w3goaudit_crawler
.\.venv\Scripts\python.exe scripts/knowledge_base.py --db data/checkpoints/phase4-replay.sqlite3 build --pipeline-version evidence-resolver-v1 --config config/knowledge_phase4_recorded.json --limit 100
```

Chỉ xử lý state thuộc pipeline/config đã chọn và có inventory evidence được
lưu. Finding partial vẫn tạo candidate từ báo cáo; state chưa có outputs sẽ
được ghi `waiting_for_evidence_inventory`. `next_after` dùng để đi trang tiếp;
chạy lại cùng đầu vào sẽ skipped. Không tự nâng syntax status hoặc gọi lại
engine trong lúc tạo knowledge.

## Bổ sung, sửa và review

```powershell
.\.venv\Scripts\python.exe scripts/knowledge_base.py --db data/checkpoints/phase4-replay.sqlite3 show <revision_id>
.\.venv\Scripts\python.exe scripts/knowledge_base.py --db data/checkpoints/phase4-replay.sqlite3 revise --input data/processed/phase7-overflow-draft.json
```

Manifest sửa gồm `expected_revision_id`, `title`, `claims` (category, text,
citations) và `missing_information`. Xem ví dụ overflow trong file trên.
Nội dung mới tạo version mới với `needs_review`; không ghi đè nội dung version
cũ và không tự approve. Cùng manifest/kết quả là no-op. Version mới trở thành
head; old approved revision không được âm thầm dùng thay draft mới.

```powershell
# Người review thực hiện sau khi kiểm tra nội dung và dẫn chứng.
.\.venv\Scripts\python.exe scripts/knowledge_base.py --db data/checkpoints/phase4-replay.sqlite3 review <revision_id> --status approved --reviewer <reviewer> --note "Lý do quyết định" --expected-sequence 0
```

Review kiểm tra revision mới nhất và sequence để chặn cập nhật từ bản cũ.
Approval yêu cầu đủ nhóm kiến thức, không còn missing information, reviewer,
lý do và timestamp. Cần sửa draft trước khi approve nếu dữ liệu còn thiếu;
không điền nhận định không có căn cứ chỉ để vượt kiểm tra. Có thể rejected
hoặc chuyển lại needs_review; mỗi quyết định ghi event atomic cùng trạng thái.
Tên reviewer là metadata do CLI nhận, **chưa phải cơ chế xác thực người dùng**.

Quote đúng chứng minh nguồn gốc, không chứng minh câu diễn giải được quote hỗ
trợ về mặt ngữ nghĩa. Reviewer vẫn phải kiểm tra nguyên nhân/điều kiện/phạm vi.
Code parse được hoặc resolver resolved không tự chứng minh finding đúng.

## Xuất knowledge cho evidence

```powershell
.\.venv\Scripts\python.exe scripts/knowledge_base.py --db data/checkpoints/phase4-replay.sqlite3 export --include-candidates --output data/processed/phase7-knowledge.json
```

Output nhóm tám trường knowledge với citations, đồng thời chứa
`finding_evidence` (link ID, evidence ID, role, resolution/syntax status,
provenance và direct_claim_ids). Có thể lọc một link bằng `--link-id <id>`.
Nhận định cấp báo cáo không mặc nhiên là nhận định đúng cho mọi đoạn code;
chỉ direct_claim_ids là claim có citation trỏ rõ vào link đó.

Mặc định export chỉ lấy head approved; cần `--include-candidates` để đọc
draft. Rejected không được xuất. Export kiểm tra lại citations/bindings; không
âm thầm xuất dữ liệu mất nguồn. Đọc nhiều heads không là một database snapshot
toàn cục; dừng writers khi cần một export hoàn toàn nhất quán tại một thời điểm.

## Kết quả đã chạy

- Toàn bộ **221 tests đạt**, gồm engine binary thật, CLI, grounding, review,
  versioning, rollback và serialization BigQuery. Lint và cả ba bộ schema đạt.
- 34 latest knowledge candidate; 26 có evidence, 8 chỉ dựa trên report.
- 360 claims có quote và vị trí dòng kiểm tra được.
- Một bản nháp biên soạn cho **[H-03] Risk of silent overflow in reserves update**,
  có 7 nhóm kiến thức; giới hạn áp dụng và kiểm chứng PoC vẫn cần review.
- Cả 34 bản là `needs_review`, **0 approved**. Export mặc định sẽ rỗng, đây là
  điều kiện review chủ động, không phải mất dữ liệu.
- Chạy lại extraction: 34 skipped. Finding, evidence, links và processing
  states gốc được kiểm tra hash trước/sau và không đổi.

Artifacts:
`data/processed/phase7-knowledge.json`, `phase7-overflow-draft.json`,
`phase7-verification.json`. Ví dụ dễ đọc: [phase7-example.md](data/processed/phase7-example.md).
Script `scripts/verify_phase7.py` kiểm chứng offline
nguồn và idempotence; không có bước embedding/retrieval hoặc sinh WQL.

## Schema, cloud và giới hạn

Schema trong `schemas/knowledge-base-v1`; migration bổ sung
`sql/migrations/004_grounded_knowledge.sql`. SQLite đã chạy thực tế; BigQuery
adapter được kiểm tra serialization claims/citations bằng mock, chưa chạy
cloud. Trước khi dùng BigQuery, dừng workers và áp dụng 001–004; lệnh init
hiện có đã thêm migration 004. Không migration nào được tự áp dụng trong đợt này.

```powershell
.\.venv\Scripts\python.exe scripts/export_knowledge_base.py --check
```

Thành phẩm hiện là nền tảng knowledge có dẫn chứng và hàng đợi candidate cho
review. Extractor dựa heading còn đơn giản; nhiều finding chưa có root cause,
điều kiện hoặc limitations được diễn giải đầy đủ. Không gọi đây là bộ tri thức
đã duyệt hay cam kết mọi finding được tổng hợp hoàn chỉnh tự động.
