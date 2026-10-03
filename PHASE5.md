# Phase 5 — kiểm chứng evidence bằng engine

Đã nối crawler với CLI Go thông qua protocol JSON `validate-evidence` v1.
Engine dùng `solast-go v0.1.4` với `Tolerant: false`, kiểm tra đúng
`normalized_snippet` đã lưu. Không sửa raw code, snippet, ID, source range hoặc
liên kết của phase 4. Không dùng validator kiểm tra ngoặc cũ làm kết quả parser.

## Kết quả trên dữ liệu hiện có

Đã chạy 100 evidence trong `data/checkpoints/phase4-replay.sqlite3`:

| Kết quả | Số evidence |
|---|---:|
| parsed | 12 |
| insufficient_context | 87 |
| invalid | 1 |
| Lỗi gọi engine | 0 |

Chạy lại cùng binary: **100 skipped**, không ghi lại kết quả. Báo cáo chi tiết:
`data/processed/phase5-validation.json`; kiểm tra chạy lại:
`data/processed/phase5-rerun.json`.

87 đoạn thiếu ngữ cảnh là kết quả được giữ để xem xét, không phải bị loại bỏ.
Nhiều đoạn là thân hàm, function thiếu contract, hoặc cửa sổ source bị cắt giữa
chừng. Validation snippet không tự tải repository/imports. Phần bổ sung
[repository context](PHASE5_CONTEXT.md) đã nối trích caller/callee, modifier,
state variables và inheritance khi có repo local tại đúng commit.

Một Gist bị parser từ chối tại dòng 209: `expected ';', got 'memory'`. Đây là
diagnostic của phiên bản parser đang dùng, **không phải kết luận Solidity gốc
chắc chắn sai**. Cần xem xét giới hạn grammar/parser trước khi loại evidence.

## Ý nghĩa các trạng thái

- `parsed`: parser strict chấp nhận source unit; không chứng minh compile,
  resolve dependencies, có thể khai thác, hay được WQL hỗ trợ.
- `insufficient_context`: đoạn bị cắt/thiếu contract; hoặc chỉ parse được khi
  thử đặt trong wrapper tạm. Wrapper không được lưu, không trở thành contract
  hay hàm thật trong metadata, không nâng trạng thái lên parsed.
- `invalid`: parser từ chối đầu vào được xem là source đầy đủ (hiện là file Gist).
  Xem diagnostics và parser version để phân biệt source sai với parser chưa hỗ trợ.
- Timeout, process crash, exit khác 0, sai JSON/protocol/hash: lỗi hạ tầng;
  giữ nguyên evidence để lần chạy sau thử lại, không gán `invalid`.

GitHub ranges và inline được coi là fragment vì không thể khẳng định đã có toàn
source unit. Gist là nội dung file đầy đủ đã qua resolver kiểm tra truncation.

## Build và chạy

Từ `E:\dacn\w3goaudit_research`:

```powershell
go build -o ../w3goaudit_crawler/data/bin/w3goaudit-evidence.exe ./cmd/w3goaudit
go test ./...
```

Từ `E:\dacn\w3goaudit_crawler`:

```powershell
.\.venv\Scripts\python.exe scripts/validate_evidence.py --engine data/bin/w3goaudit-evidence.exe --db data/checkpoints/phase4-replay.sqlite3 --limit 100 --report data/processed/phase5-validation.json
```

Sau khi chạy resolver live cho findings mới, đổi `--db` sang database đó.
`--limit` từ 1 đến 1000; dùng `--after <next_after>` để xử lý trang kế tiếp.
`--timeout` mặc định 30 giây cho mỗi evidence. Nếu một evidence lỗi hạ tầng,
CLI tiếp tục các evidence khác, báo tổng errors và trả exit code 1; bắt đầu lại
pagination để thử lại những ID lỗi. Không tự coi batch lỗi là thành công.

`--backend bigquery` sử dụng cùng bảng code_evidence và revision guard phase 3.
Không cần migration mới. BigQuery adapter đã có code đọc/ghi nhưng chưa chạy
validation trên cloud trong đợt này.

## Đồng bộ metadata với engine

| Contract v1 | Engine |
|---|---|
| function_signature | Function.Selector: chữ ký đầy đủ |
| selector_4byte | `0x` + Function.Signature |
| contract_name / function_name | Tên declaration parser tìm được |
| source offset | source_range.start_line + snippet line − 1 |

Không chọn tùy ý một overload: nếu evidence chứa nhiều hàm thì các trường hàm
đơn trị để null, danh sách đầy đủ có trong báo cáo JSON. Type chưa resolve được
(custom type bên ngoài/inherited…) không được hash thành selector giả.
Constructor/receive/fallback không được gán selector 4 byte.
Pragma chỉ là ràng buộc khai báo trong source, không phải compiler thực tế đã dùng.

Chỉ ánh xạ dòng source khi raw = normalized, không có transformations và số
dòng khớp source_range. Inline diff hoặc snippet biến đổi giữ tọa độ snippet,
không giả làm dòng thật trong repository.

Parser version lưu cả tên/version adapter và SHA256 binary. Build engine khác
sẽ được kiểm chứng lại. Metadata annotation được cập nhật bằng transaction và
so sánh bản ghi đã đọc; worker cũ không ghi đè annotation mới của worker khác.
V1 giữ annotation mới nhất trên evidence; chưa có bảng lịch sử từng lần parse.

## Các sửa chữa trong engine

- Tra function ID theo file + contract + chữ ký, không bỏ qua file.
- Context call graph dùng chữ ký đầy đủ thay vì tên hàm.
- Tra source của đúng function declaration khi hai file có contract cùng tên.
- CLI từ chối lựa chọn hàm mơ hồ; có thể dùng chữ ký đầy đủ và contract ID
  dạng `path#Contract` để chỉ định chính xác.
- Chuẩn hóa ABI aliases (`uint`, `int`, `byte`, `address payable`…) trước khi hash;
  sửa việc resolve struct bị lặp lại nhầm thành vòng lặp.

Database engine cũ chứa selectors trước các sửa chữa cần build lại để các key
và call graph đồng bộ. Sửa này không biến engine thành bộ kiểm chứng semantic
toàn diện; một số đường resolve inheritance/WQL cũ vẫn cần review riêng.

## Kiểm thử

Đã chạy toàn bộ crawler: **187 passed**, bao gồm tích hợp binary thật.
Engine đã qua `go test ./... -timeout 60s`; lint các file Python phase 5 cũng đạt.

```powershell
$env:W3GOAUDIT_ENGINE = (Resolve-Path data/bin/w3goaudit-evidence.exe).Path
.\.venv\Scripts\python.exe -m pytest -q
```

Nếu không đặt biến môi trường, test tích hợp binary thật sẽ được báo skipped;
các tests adapter giả lập vẫn chạy. Test bao gồm parser strict, fragment/wrapper,
selector ERC-20 `0xa9059cbb`, overload, contract trùng tên khác file, tọa độ dòng,
timeout, protocol sai, bảo toàn ID/code, ghi đồng thời và chạy CLI hai lần.

Phase này chưa gọi templates để kết luận có/không có lỗ hổng, chưa sinh knowledge
hay rule tự động, chưa sửa mọi vấn đề WQL đã ghi nhận. Chất lượng evidence và
khả năng biểu đạt rule là hai bước đánh giá độc lập.
