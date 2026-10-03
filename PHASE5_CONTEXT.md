# Phase 5 — bổ sung context repository

Đã triển khai `evidence-context` phía Go và `scripts/enrich_evidence_context.py`
phía crawler. Phạm vi là trích context khi có repo đủ dữ liệu; phase 6 vẫn là
chống trùng và vận hành batch lớn.

## Đầu vào và cách chạy

Cung cấp Git repo local chứa commit mà evidence tham chiếu, với remote `origin`
đúng repo GitHub. File JSON ánh xạ `owner/repo` tới đường dẫn local; xem
`config/context-repositories.example.json`. Đổi đường dẫn ví dụ thành checkout
thực tế. Checkout không cần đang đứng ở commit của evidence.

```powershell
# Từ E:\dacn\w3goaudit_research
go build -o ../w3goaudit_crawler/data/bin/w3goaudit-evidence.exe ./cmd/w3goaudit

# Từ E:\dacn\w3goaudit_crawler
.\.venv\Scripts\python.exe scripts/enrich_evidence_context.py --engine data/bin/w3goaudit-evidence.exe --db data/checkpoints/phase4-replay.sqlite3 --repo-map config/context-repositories.local.json --output data/processed/engine-context --limit 100
```

Hỗ trợ `--after`, `--limit`, `--timeout` và các tùy chọn backend BigQuery như
validation. Đọc evidence từ backend; context lưu ra artifact local, **chưa có
bảng context trong BigQuery**. Không thay đổi contract v1 âm thầm.

## Nguồn và lưu trữ

- Đọc Git blobs tại `commit_sha`, không đọc code working tree. File đang sửa,
  file untracked và Git replace refs không ảnh hưởng bundle.
- Đối chiếu snippet với đúng file/khoảng dòng tại commit trước khi gắn context.
  Inline/Gist, snippet biến đổi hoặc không khớp nguồn được báo unavailable;
  không suy đoán repo theo tên contract.
- `bundles/<hash>.json`: repo, commit và nội dung source để replay.
- `annotations/ctx_<hash>.json`: evidence ID, bundle ID, commit, source range,
  SHA256 binary engine và kết quả context. Không sửa syntax status/ID/code gốc.
- `reports/<hash>.json`: kết quả từng evidence, đường dẫn annotation, thống kê
  và cursor trang sau. Ghi atomic từng file; bundle được lưu trước annotation.
  Cùng đầu vào/kết quả dùng cùng ID, annotation cũ được giữ khi binary thay đổi.
- Lỗi engine/timeout là `error`, không phải source invalid. Batch tiếp tục các
  evidence khác và CLI trả exit code 1 nếu có error; chạy lại để thử lại.

## Đầu ra engine

Các hàm giao với range evidence có ID file + contract + chữ ký đầy đủ, caller,
callee, vị trí dòng và tên modifier áp dụng. Danh sách contract chứa direct
bases, linearized bases, modifier declarations và state variable declarations.
Dữ liệu inherited giữ tại contract khai báo gốc. State variables là declarations,
không phải kết luận hàm đọc/ghi biến nào.

| Context status | Ý nghĩa |
|---|---|
| available | Dựng được static context trong bundle được cung cấp |
| partial | Có context nhưng còn call chưa resolve, inheritance chưa tuyến tính hóa hoặc range không giao hàm nào |
| unavailable | Thiếu repo/import, parser từ chối hoặc gặp cấu trúc chưa hỗ trợ an toàn |
| error | Lỗi process, protocol hoặc lưu trữ; có thể thử lại |

`available` không đồng nghĩa biên dịch được hay đủ ngữ nghĩa để kết luận lỗ hổng.
Caller/callee là heuristic của engine, chỉ trong tập source được cung cấp.
Tập caller rỗng không chứng minh không có caller bên ngoài. Modifier bodies,
dynamic dispatch và mọi call expression chưa được mô hình hóa đầy đủ;
diagnostic này luôn đi kèm kết quả thành công.

## Giới hạn rõ ràng

Strict-parse mọi file trước khi dựng database. Thiếu import, import đổi tên,
free function, contract/struct trùng tên, inheritance vòng lặp hoặc type tham số
chưa resolve được sẽ không tạo graph có đích được đoán tùy ý. Overload có nhiều
chữ ký cùng tên được hạ về call chưa resolve, không chọn hàm đầu tiên.

Lấy các file `.sol` được track trong commit: tối đa 100 file, 2 MB/file, 4 MB
tổng source. Không tự clone/fetch, cài dependency, resolve remapping, đọc
submodule hay chạy compiler/build script. Hỗ trợ import tương đối hoặc đường
dẫn khớp trực tiếp bundle. Repo vượt giới hạn được báo unavailable, không cắt
bundle rồi coi như hoàn chỉnh. Những giới hạn này không kết luận source sai.

## Kiểm chứng và coverage

Toàn bộ crawler: **193 passed**, gồm tích hợp binary thật. Toàn bộ Go tests
đã đạt; các ca bổ sung về alias/type/overload cũng đạt. Ruff và Black đạt.

Tests Go kiểm tra inherited caller/callee, modifier, state variables, range,
overload và missing/ambiguous dependencies. Tests Python tạo Git repo hai file
có commit thật, gọi binary thật qua CLI; kiểm chứng dirty checkout, provenance
mismatch, ghi artifacts, chạy lại cùng ID và evidence gốc không đổi.

Corpus phase 4 có 77 inline, 1 Gist và 22 GitHub evidence thuộc hai repo
`code-423n4/2023-04-caviar` và `code-423n4/2023-01-astaria`. Chưa cấu hình checkout
hai repo này trong lần bổ sung: tích hợp sử dụng repo fixture, **không khẳng định
đã làm giàu context cho 100 evidence thực tế**. Cần chạy với repo-map thực tế để
đo coverage; thiếu dependency hoặc vượt giới hạn sẽ được ghi rõ trong report.
