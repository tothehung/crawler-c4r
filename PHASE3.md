# Giai đoạn 3 — lưu trữ và điều phối

Đã có lớp xử lý độc lập với crawler cũ. Finding đi qua:
`snapshot → pending → running → succeeded / partial / failed`.
Resolver thật sẽ nối ở giai đoạn 4 bằng `KnowledgeProcessingService.run_batch`.
**Cập nhật:** resolver đã được nối ở [phase 4](PHASE4.md); phần dưới mô tả API
manifest và các đảm bảo lưu trữ đã xây ở phase 3.
Hiện CLI nhận manifest kết quả đầy đủ; không gọi resolver cũ và không tự coi
finding chưa phân tích là `no_candidates`.

## Chạy local, không gọi mạng

```powershell
.\.venv\Scripts\python.exe scripts/process_knowledge.py init
.\.venv\Scripts\python.exe scripts/process_knowledge.py ingest --input data/findings.jsonl --format legacy --source solodit --pipeline-version phase3-manifest-v1 --config config/knowledge_phase3.json --limit 100
.\.venv\Scripts\python.exe scripts/process_knowledge.py status --limit 100
```

Database mặc định: `data/checkpoints/knowledge.sqlite3`, có thể đổi bằng `--db`
trước tên lệnh. Import lại cùng file không thêm snapshot/job trùng. Kết quả có
`next_offset` để tiếp tục bằng `--offset`; chạy lại cả batch cũng an toàn.
`status --after <processing_key>` phân trang theo key, không phải thứ tự thời gian.
Input `--format contract` nhận JSONL SourceFindingSnapshot v1 để giữ nguyên
API JSON hoặc HTML gốc. Legacy giữ toàn bộ dòng JSON dưới nhãn
`legacy_normalized_json`, không tuyên bố đó là phản hồi HTTP gốc.
Hash bao gồm toàn bộ raw payload; thay đổi cả metadata trong export cũng tạo
snapshot mới. Đây là nhận dạng snapshot, chưa phải semantic dedup giữa hai nguồn.
Không đoán nguồn từ ID; legacy phải khai báo `--source`.

Fingerprint = snapshot ID + pipeline version + hash config. Config phải chứa
mọi thiết lập ảnh hưởng output (phiên bản resolver/parser, normalization, context
lines…), không chứa token. Đổi nội dung/pipeline/config tạo job mới. Enqueue lại
không reset attempts và không ghi đè snapshot. Capture time đầu tiên được giữ.

## Kết quả resolver

`apply-results --input results.jsonl --limit 100` nhận một JSON object mỗi dòng:

```json
{
  "processing_key": "prc_...",
  "inventory_complete": true,
  "candidate_count": 0,
  "evidence": [],
  "links": [],
  "retry_after": 0
}
```

Ví dụ trên chỉ hợp lệ khi resolver đã xác định thật sự không có candidate.
Với candidate có code, `evidence` chứa CodeEvidence v1; `links` chứa
FindingEvidenceLink v1 của đúng snapshot/key, gồm cả lỗi không lấy được code.
Một locator có đúng một link; evidence được chia sẻ giữa các finding.
Manifest thiếu `inventory_complete` bị từ chối. CLI tin tuyên bố inventory của
producer; đo recall/chất lượng nhận diện thuộc benchmark và giai đoạn 4.
Manifest là dữ liệu đầu vào, không phải lệnh để thực thi.

## Quy tắc phục hồi

- Claim tăng attempts và cấp token riêng cho từng lần nhận việc; lease mặc định
  300 giây. Resolver lâu phải gọi `heartbeat` hoặc tăng lease phù hợp.
- Lease chưa hết hạn không thể bị worker khác nhận. Lease hết hạn được nhận lại
  trong giới hạn attempts; worker cũ không được ghi evidence hay trạng thái.
- Evidence, links và trạng thái cuối ghi trong cùng transaction. Lỗi giữa chừng
  rollback toàn bộ. Mất process sau claim để lại lease, có thể phục hồi khi hết hạn.
- Chỉ `succeeded` cùng fingerprint được skip hoàn tất. Partial giữ mọi link lỗi;
  chỉ partial/failed có retryable mới được nhận lại khi đến giờ và còn attempts.
- Backoff 30s nhân đôi, có jitter, tôn trọng `retry_after`, tối đa mặc định 3 attempts.
  Lỗi vĩnh viễn hoặc hết attempts cần xem xét; không tự reset bằng enqueue.
- Retry phải giữ đầy đủ inventory/locator cũ. Đổi thuật toán nhận diện cần version
  mới. Evidence immutable theo ID; metadata lần ghi đầu tiên được giữ.
- Lỗi storage/commit không bị biến thành lỗi resolver. Chạy lại sau khi kiểm tra
  trạng thái; job thành công được skip, lease đang chạy phải chờ hết hạn.

## BigQuery

BigQuery là backend độc lập, không phải bản sao của SQLite. Chọn backend từ đầu;
hai backend không tự đồng bộ. Dataset phải tồn tại. Chạy init khi workers đã dừng:

```powershell
.\.venv\Scripts\python.exe scripts/process_knowledge.py --backend bigquery init
.\.venv\Scripts\python.exe scripts/process_knowledge.py --backend bigquery ingest --input data/findings.jsonl --format legacy --source solodit --pipeline-version phase3-manifest-v1 --config config/knowledge_phase3.json --limit 20
.\.venv\Scripts\python.exe scripts/process_knowledge.py --backend bigquery status --limit 20
```

Đọc cấu hình `.env` như crawler hiện tại: BIGQUERY_PROJECT_ID, BIGQUERY_DATASET,
BIGQUERY_LOCATION và ADC/GOOGLE_APPLICATION_CREDENTIALS. Init áp dụng migration
001 và 002, không sửa/truncate bảng findings cũ. Không chạy hai init đồng thời.

Migration 002 tạo một revision guard. Mọi thao tác ghi kiểm tra revision đã đọc,
UPDATE guard rồi MERGE các bảng trong một transaction. BigQuery hủy các transaction
xung đột trên cùng bảng; repository trả lỗi để caller đọc lại, không replay mù
một quyết định cũ. Lease được kiểm tra lại bằng giờ server trong transaction.
Xem [BigQuery transactions](https://docs.cloud.google.com/bigquery/docs/transactions).

Tất cả writers của bốn bảng xử lý phải dùng repository này để duy trì đảm bảo
uniqueness. Không dùng streaming/direct INSERT bên ngoài. Guard serialize ghi
toàn dataset: phù hợp batch nhỏ giai đoạn 3, chưa tối ưu throughput/chi phí cho
fleet lớn. Mỗi snapshot/attempt là một transaction; limit CLI không phải một
transaction khổng lồ. Đây chưa phải distributed scheduler throughput cao.

## Kiểm chứng

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_knowledge_processing.py tests/unit/test_knowledge_processing_cli.py tests/unit/test_bigquery_knowledge_store.py tests/unit/test_knowledge_contract.py tests/unit/test_evidence_benchmark.py -q
```

Tests SQLite dùng database thật và hai thread tranh claim; kiểm tra reopen,
rollback khi lỗi sau ghi output, hết lease, retry và skip khi chạy lại.
Tests BigQuery dùng mocked client để kiểm tra transaction, parameters, revision
và lease fence; **chưa chứng minh tích hợp cloud live**. Migration không tự được
áp dụng khi import module. Chưa nối engine, sửa resolver hay tạo knowledge/rule.

Kết quả kiểm tra ngày 2026-09-29: 19 tests mới và 53 tests contract/benchmark đạt.
CLI được kiểm tra ingest → apply-results → chạy lại → phân trang status bằng
SQLite thật. Batch 20 findings local được nhập hai lần, vẫn chỉ có 20 snapshots
và 20 jobs pending. Toàn suite: 138 passed, 8 lỗi cũ ở resolver/cleaner/validator
đã ghi nhận từ giai đoạn 2; không có lỗi mới từ phần persistence.
