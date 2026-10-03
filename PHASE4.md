# Phase 4 — resolver thật nối với điều phối

Pipeline hiện có thể chạy `finding → snapshot → resolver → evidence + links + state`
bằng lệnh `run`; không cần chuẩn bị manifest kết quả thủ công. Dùng contract v1,
pipeline version `evidence-resolver-v1`. Chưa chạy engine hay sinh knowledge/rule.

## Đã thực hiện

- Markdown được duyệt bằng AST CommonMark: fence backtick/tilde, code thụt dòng,
  reference link, autolink và URL trong văn bản. Nhận diện Solidity bị gắn nhãn
  `js`, tách inline diff, loại các trace/log đã nhận diện và link tới report `.md`.
- GitHub file: resolve ref sang SHA 40 ký tự, đọc raw tại SHA đó, hỗ trợ branch
  có `/`, path URL-encoded và anchor dòng có cột như `#LL640C9-L650C15`.
  Giữ riêng reported range và cửa sổ source đã lấy. Range sai được ghi lỗi.
- Commit diff: lấy parent và commit đích; PR diff: lấy merge base và head,
  tải diff ở cặp SHA bất biến. Giữ hai phía, file rename/add/delete và context.
  Đối chiếu từng đoạn với file raw ở đúng SHA trước khi gán nguồn gốc.
- Gist: giữ revision, path và từng file `.sol`; content truncated được đọc lại
  từ raw URL tại revision đã xác định, không tải từ URL tùy ý trong payload.
- Inline diff: raw giữ patch, normalized tách before/after và ghi transformations.
  Inline thường giữ code đã giải mã từ Markdown AST; toàn bộ report nguyên bản
  vẫn nằm trong snapshot. Không tự strip số dòng, sửa code, hoặc bọc contract.
- Role chỉ gán theo câu/heading rõ trong report, có `role_basis`. Phía trước của
  diff không tự bị gán vulnerable. `unknown` được giữ khi thiếu căn cứ.
- Mọi evidence mới có `syntax_status=not_checked`; balanced braces không được
  coi là kiểm chứng Solidity. Xác thực bằng engine thuộc phase 5.

Nguồn API: [GitHub commits/compare](https://docs.github.com/en/rest/commits/commits),
[Gists](https://docs.github.com/en/rest/gists/gists),
[Markdown token API](https://markdown-it-py.readthedocs.io/en/latest/api/markdown_it.token.html).

## Chạy trên dữ liệu mới

```powershell
.\.venv\Scripts\python.exe scripts/process_knowledge.py ingest --input data/findings.jsonl --format legacy --source solodit --pipeline-version evidence-resolver-v1 --config config/knowledge_phase4.json --limit 20
.\.venv\Scripts\python.exe scripts/process_knowledge.py run --config config/knowledge_phase4.json --limit 100
.\.venv\Scripts\python.exe scripts/process_knowledge.py status --limit 100
```

`ingest` với version/config mới tạo job phase 4 cho snapshot có sẵn. Jobs phase 3
giữ lịch sử cũ; `run` chỉ nhận job khớp version và config. File Code4rena dùng
`--source code4rena`; input contract v1 dùng `--format contract`.

`--limit` của `run` giới hạn số hàng trạng thái đọc mỗi trang. Theo `next_after`
bằng `--after <key>` để quét tiếp; trang có jobs của pipeline khác có thể không
xử lý finding nào. Một lượt retry sau thời gian chờ bắt đầu lại từ đầu pagination.
Kết quả in ra counters/status, không in nội dung source hoặc token.

`GITHUB_TOKEN` tùy chọn đọc từ `.env`; chỉ gửi Authorization tới API GitHub.
HTTP timeout 30 giây; lease mặc định 300 giây; CLI gia hạn lease khi chạy lâu.
Config chứa giới hạn candidates, requests, response bytes và evidence mỗi URL.
Chạm giới hạn được ghi lỗi, không bỏ im lặng. Muốn đổi giới hạn, enqueue bằng
config mới để có fingerprint mới. Token không được đưa vào config hoặc hash.

Có thể thêm `--backend bigquery` trước tên lệnh sau khi áp dụng migration phase 3.
BigQuery chưa được triển khai/kiểm chứng cloud live trong công việc này.

## Retry và liên kết

404 là `not_found_or_inaccessible`, không suy ra repo private hay đã xóa.
429, 5xx, lỗi transport và 403 có dấu hiệu rate limit được retry, tôn trọng
Retry-After. Các lỗi khác được giữ để xem xét. Kết quả inline vẫn được lưu khi
URL khác thất bại. Không có retry vòng lặp ngủ trong resolver; scheduler phase 3
quản lý thời gian chờ và attempts.

Locator gốc ổn định theo node trong report. Diff/Gist có nhiều phần sinh thêm
link con, trỏ về link gốc qua related_link_id. Root gắn evidence đầu tiên; các
link còn lại giữ toàn bộ phần khác. Đây là quan hệ nhóm, không khẳng định mọi
link con là bản sửa của evidence gốc.

Resolver giữ kết quả thành công/vĩnh viễn từ lần trước, chỉ thử lại root có lỗi
retryable. Nếu lần đầu chưa đọc được diff/Gist, lần sau được phép bổ sung links.
Repository kiểm tra mọi link cũ vẫn được giữ; không được đạt success bằng cách
bỏ candidate lỗi. Manifest phase 3 mặc định vẫn yêu cầu inventory không đổi.
Các URL chưa từng resolve thành công được đọc lại tại thời điểm retry; sau khi
resolve thành công, evidence đã pin SHA/revision và không tự đổi theo branch mới.

## Kiểm chứng và kết quả

Kiểm tra cuối ngày 2026-09-29: **173 tests passed**, lint các file đã sửa đạt.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/benchmark_evidence.py --output data/processed/evidence-phase4.json
.\.venv\Scripts\python.exe scripts/verify_phase4.py
```

Baseline phase 2 được giữ nguyên. Benchmark trên 34 findings đã review:

| Chỉ số | Phase 2 | Phase 4 |
|---|---:|---:|
| Selected targets tìm thấy | 93/105 | 105/105 |
| Forbidden targets bị lấy nhầm | 20/36 | 0/36 |

Đây là đo nhận diện candidate trên tập đã gán nhãn, không phải độ chính xác
phát hiện lỗ hổng hay precision/recall toàn bộ dữ liệu. Role accuracy chưa được
đánh giá độc lập. Finding `solodit-66925` vẫn bị loại khỏi corpus kiểm chứng do
lẫn nội dung findings khác; CLI chung không có hardcode ID để che lỗi nguồn.

Chạy toàn corpus bằng 7 HTTP responses đã ghi lại tạo **100 evidence**, **154 links**:
101 resolved, 53 fixture_missing; 2 findings succeeded, 32 partial.
Thiếu fixture được báo riêng, không giả lập thành 404 và không fallback ra mạng.
Lưu trong `data/checkpoints/phase4-replay.sqlite3` và báo cáo
`data/processed/phase4-resolution.json`. Replay và live dùng config/fingerprint
khác nhau để không reuse nhầm kết quả thiếu fixture khi chạy thật.

Smoke test qua mạng thật trên một file Astaria tại commit cố định và một Gist
đã thành công: 2 resolved, 0 unresolved. Đây là synthetic control ghép URL công
khai, không phải một finding thật. Kết quả ở `data/processed/phase4-live-smoke.json`;
chưa chạy toàn bộ corpus qua mạng thật. Diff được kiểm thử bằng response tổng hợp
và đối chiếu source; bộ HTTP cũ thiếu metadata bất biến để replay end-to-end diff.

Tests bao gồm rollback/lease phase 3, retry mở rộng inventory, đọc lại CLI không
ghi trùng, hai nguồn dùng chung evidence, Markdown AST, diff rename/add/delete,
range sai, Gist truncated, rate limit, timeout, giới hạn tải và redirect.

Các tests cũ sai được sửa có căn cứ: dấu trừ phải được giữ; symbol hints nằm ở
ScanResult kể cả khi không có candidate; fixture SHA ngắn cần ít nhất 7 ký tự;
đoạn thiếu contract header không được khẳng định có contract hoặc parse thành công.
Legacy validator vẫn chỉ là heuristic; đường chạy phase 4 không dùng nó.

## Giới hạn chủ động

Chỉ HTTPS trên GitHub/Gist, code file `.sol`. Chưa có GitLab, explorer verified
source hay lấy code từ PDF/ảnh. Gist hỗ trợ chọn file bằng anchor, chưa hỗ trợ
anchor dòng của Gist. Commit gốc/merge commit, quoted diff paths, binary diff
không được suy diễn source; được giữ dạng lỗi/không có Solidity evidence.
URL file không có dòng lấy cả file, chưa cắt theo AST function (phase 5).
Bounded worker và BigQuery revision guard hiện dành cho batch nhỏ.
