# Phase 6 — chống trùng và vận hành batch

Đã triển khai đúng phạm vi phase 6 trong `ROADMAP.md`: processing dedup,
finding dedup, evidence reuse và báo cáo vận hành. Chưa bắt đầu knowledge
extraction/embedding/retrieval của phase 7.

## Ba cơ chế riêng

| Cơ chế | Khóa và hành vi |
|---|---|
| Processing dedup | Snapshot nội dung + pipeline version + config hash. Enqueue lại không tạo state mới; succeeded không xử lý lại. Partial/failed chỉ retry khi đủ điều kiện, còn lượt và đến thời điểm retry. |
| Finding dedup | Nhóm có version, liên kết snapshot và source key; không xóa hoặc viết lại finding gốc. Native source identity và URL xác định một finding là căn cứ confirmed. |
| Evidence dedup | Giữ cơ chế evidence ID contract v1; nhiều finding/run cùng ID dùng chung evidence. Lưu đủ links của mỗi processing key, giữ annotation engine có sẵn. |

Evidence identity chứa provenance, code, normalization/extractor version và
transformations. Nâng pipeline nhưng đầu ra không đổi có thể dùng lại evidence;
thay revision/source/transformations/extractor có thể tạo evidence ID mới đúng
theo contract. Không gộp code giống nhau nhưng nguồn khác rồi mất provenance.

Finding groups được lưu trong `finding_dedup_memberships`; nhóm chung là liên
kết duplicate. Không viết `canonical_finding_id` ngược vào snapshot bất biến.
Báo cáo hợp nhất các nhóm confirmed thành components để không đếm trùng khi
nhiều căn cứ cùng nối một cặp nguồn. Components là view tại thời điểm báo cáo,
không phải canonical ID vĩnh viễn khi thêm dữ liệu mới.

## Quy tắc finding dedup

- Dùng `(source, source_id)` qua source key để nối các revision của cùng nguồn.
- URL được nhận diện: GitHub issue riêng lẻ, Code4rena report có anchor finding
  dạng H/M/L/G-number, Solodit issue page. Chuẩn hóa scheme/host, casing repo
  GitHub và tracking query; giữ anchor cần thiết của Code4rena.
- Chỉ lấy `source_url` và `raw_payload.source_link`; không dùng link code hay
  tham chiếu tùy ý trong nội dung để kết luận duplicate.
- URL chung của báo cáo, GitHub blob/code, query không nhận diện được không
  được dùng làm căn cứ tự liên kết. Findings cùng một báo cáo vẫn độc lập.
- Nội dung giống nhau sau chuẩn hóa Unicode/whitespace (từ 80 ký tự) hoặc tiêu
  đề giống nhau (từ 25 ký tự) chỉ tạo **candidate cần review**. Chưa có matcher
  semantic/fuzzy và chưa đo recall duplicate trên tập gắn nhãn thực độc lập.
- Membership được tạo trực tiếp theo group key, không so sánh từng cặp O(n²).
  Ghi toàn bộ membership và trạng thái hoàn tất trong cùng transaction.
  Nâng `DEDUP_VERSION` tạo lớp kết quả mới, giữ lớp cũ để đối chiếu.

## Chạy và resume

Từ `E:\dacn\w3goaudit_crawler`, với findings đã enqueue theo config tương ứng:

```powershell
.\.venv\Scripts\python.exe scripts/process_knowledge.py --db data/checkpoints/knowledge.sqlite3 run --config config/knowledge_phase4_recorded.json --replay-http tests/fixtures/evidence_benchmark_v1/http --checkpoint evidence-recorded --limit 20 --max-pages 10
```

Chạy lại đúng lệnh để tiếp tục checkpoint. Với live, dùng config live và bỏ
`--replay-http`. Checkpoint gắn với tên job + pipeline version + config hash;
không dùng chung với `--after`. Cursor chỉ ghi sau khi outputs của trang đã
được lưu. Nếu bị ngắt giữa trang, phần chưa lưu sẽ được chạy lại sau khi lease
hết hạn; phần succeeded không nhân đôi. Hai worker cập nhật cùng checkpoint
bị kiểm tra CAS; worker thua đọc checkpoint mới và tiếp tục, không ghi lùi cursor.

Kết thúc một sweep không có nghĩa mọi finding đã succeeded. Lần gọi kế tiếp
bắt đầu sweep mới từ đầu để tìm retry đến hạn hoặc input vừa thêm; đây cũng là
cách bắt findings mới có key nhỏ hơn cursor. Không tự sleep chờ retry, không
spin mãi trên retry chưa đến hạn. Dùng scheduler gọi lại khi cần.

```powershell
.\.venv\Scripts\python.exe scripts/knowledge_operations.py --db data/checkpoints/knowledge.sqlite3 dedup --limit 100 --max-pages 20
```

Dedup xuất `next_after`; truyền lại bằng `--after` để đi tiếp. Sau gián đoạn,
chạy lại từ đầu cũng an toàn vì mỗi snapshot/version có completion state.
`completed` chỉ là đã đi hết lượt scan hiện tại, không phải không còn input mới.

## Báo cáo chất lượng

```powershell
.\.venv\Scripts\python.exe scripts/knowledge_operations.py --db data/checkpoints/phase4-replay.sqlite3 report --pipeline-version evidence-resolver-v1 --config config/knowledge_phase4_recorded.json --output data/processed/phase6-quality.json
```

Báo cáo lọc đúng pipeline/config để không cộng lịch sử phiên bản vào mẫu số.
Ghi rõ source findings riêng biệt với snapshot revisions. Theo từng nguồn:
findings có evidence, resolve success, parse coverage, parse success trên tập
đã kiểm tra, role coverage và mã lỗi. Mỗi tỷ lệ có numerator/denominator;
mẫu số rỗng cho `null`, không làm thành 0% hoặc 100% giả.

Thống kê chung gồm evidence được dùng lại, nhóm confirmed/candidate, retry
đến hạn/chưa đến hạn/hết lượt và thời gian resolver. Metric attempt được ghi
cùng transaction hoàn tất/fail. Các lần chạy cũ hoặc bị ngắt chưa ghi metric
được báo `untimed_attempts`, không bịa thời gian từ timestamps.

Thời gian resolver không gồm storage. Parse/role coverage không đo độ chính
xác phát hiện lỗ hổng hay độ đúng role. Parser annotation là bản mới nhất đã
lưu trên evidence. Nên dừng worker khi lấy báo cáo nhất quán: report đọc nhiều
trang, không giữ database snapshot xuyên toàn bộ lượt đọc. `--max-rows` mặc
định 100000 mỗi bảng, vượt ngưỡng báo lỗi thay vì xuất báo cáo bị cắt.

## Schema và BigQuery

Thêm bốn bảng, không đổi contract v1:
`finding_dedup_memberships`, `finding_dedup_state`, `knowledge_processing_attempts`,
`knowledge_batch_checkpoints`. SQLite dùng bảng records hiện có; BigQuery có
migration `003_knowledge_operations.sql`, schemas tại `schemas/knowledge-operations-v1`.
BigQuery writes vẫn dùng revision fence/lease guard của phase 3.

```powershell
.\.venv\Scripts\python.exe scripts/export_knowledge_operations.py --check
```

Trước khi chạy worker BigQuery sau nâng cấp, dừng workers và áp dụng migration
003 sau 001/002. Lệnh `process_knowledge.py --backend bigquery init` đã bao gồm
cả ba migration. **Chưa chạy migration hoặc thử batch trên cloud trong phase này**;
SQL adapter được kiểm thử bằng mock. Chưa khẳng định throughput cloud production.

## Kết quả kiểm chứng đã chạy

Toàn bộ **210 tests Python đạt**, bao gồm engine binary thật và CLI phase 6.
Ruff, kiểm tra contract v1 và schemas/migration phase 6 đều đạt.

`data/processed/phase6-quality.json` trên corpus đã được phase 5 annotate:

| Nguồn | Findings có evidence | Resolve thành công | Parse được / đã kiểm tra | Role xác định / evidence links |
|---|---:|---:|---:|---:|
| Solodit | 11/19 | 18/37 | 7/18 | 1/18 |
| Code4rena | 15/15 | 83/117 | 5/82 | 29/83 |

Tổng 34 findings, 154 links, 100 evidence; 101 links có evidence và một evidence
được dùng giữa nhiều findings. 32 partial, 2 succeeded; 53 candidate thiếu HTTP
fixture (`fixture_missing`), không phải 53 lỗi của website. 34 snapshot được
index; chạy lại skipped 34. Không có cặp đủ căn cứ confirmed/candidate theo
matcher hiện tại trong corpus này; không gộp ép để có số liệu duplicate.

`data/processed/phase6-verification.json` được tạo bằng:

```powershell
.\.venv\Scripts\python.exe scripts/verify_phase6.py --synthetic-size 1000
```

- Replay 34 findings thực bằng batch 5 → 10 → 20: vẫn 100 evidence, 154 links.
  Chạy lại ngay trong cửa sổ backoff: 0 attempted, 34 skipped, IDs không đổi.
- Batch tổng hợp 1000 findings, tăng cỡ trang 5 → 10 → 100 → 1000: đã ngắt
  worker sau khi một phần outputs được lưu, hết lease rồi resume đủ 1000.
- 500 nhóm confirmed giữa Solodit/Code4rena tổng hợp; 1000 links dùng chung
  một evidence. Đây là dữ liệu tổng hợp, không dùng làm chỉ số crawl accuracy.
- Rerun succeeded: 0 attempted. Nâng pipeline synthetic-v2: thêm 1000 links
  lịch sử, vẫn một evidence, giữ outputs phiên bản trước.
- Database kiểm chứng tách biệt nằm dưới `data/checkpoints/phase6-runs/`; đường
  dẫn lần chạy có trong báo cáo. Không reset database phase 4 hoặc xóa lịch sử.

Các tests còn kiểm chứng rollback membership, lỗi ghi checkpoint sau khi outputs
đã lưu, bảo toàn annotation engine khi dùng lại evidence, scope báo cáo, URL
âm tính, SQL có tham số và CLI thật. Phase 7 chưa được triển khai.
