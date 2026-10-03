# Evidence benchmark v1 — giai đoạn 2

## Kết quả bàn giao

- 35 findings thật: 20 Solodit có sẵn ở local, 15 Code4rena từ ba báo cáo công khai.
- Một mẫu `solodit-66925` được quarantine vì body chứa nhiều findings khác.
  Giữ nguyên đầu vào để kiểm tra chất lượng; không tính vào điểm resolver.
- 34 mẫu có nhãn **selected targets**: code/URL cần tìm, vai trò theo báo cáo,
  khoảng dòng khi URL có chỉ rõ, và offset của trích dẫn trong nội dung đã lưu.
- Bảy phản hồi HTTP thật được lưu: resolve commit, raw Solidity, Gist, PR diff,
  và một 404. Không suy từ 404 rằng repo private hay deleted.
- Hai finding giả lập cùng bốn tình huống HTTP lỗi và một nhóm duplicate giả lập
  được tách trong `controls.json`; không cộng vào số findings thật.
- Baseline offline và kiểm thử integrity/evaluator/replay. Đây là bộ phát triển,
  chưa phải tập đánh giá độc lập hoặc bộ ground truth do auditor duyệt.

## File và nguồn

| File | Vai trò |
|---|---|
| cases.json | Finding đầu vào cùng provenance; không sửa content để làm test qua |
| acquisitions.json | Nguồn, thời điểm HTTP và SHA-256 của artifacts |
| raw/ | JSONL local đóng băng và HTML Code4rena tải công khai |
| review_plan.json | Lựa chọn block và vai trò đã rà soát từ báo cáo, không lấy từ resolver |
| annotations.json | Nhãn materialized, gồm snippet/URL chính xác và vị trí trong report |
| http/index.json | Response metadata và hashes; không chứa credential |
| http/*.txt | Response body đã decode rồi lưu UTF-8 |
| controls.json | Tình huống giả lập để kiểm thử các nhánh còn thiếu trong dữ liệu thật |
| baseline.json / baseline.md | Kết quả baseline, lỗi, observations và hash implementation |

Nguồn Code4rena:

- [Caviar, 2023-04](https://code4rena.com/reports/2023-04-caviar): 7 finding High/Medium đầu.
- [Juicebox, 2023-05](https://code4rena.com/reports/2023-05-juicebox): 3 finding Medium đầu.
- [Astaria, 2023-01](https://code4rena.com/reports/2023-01-astaria): 5 finding High đầu.

File incremental local chỉ lặp 5 findings; không dùng để tăng giả số mẫu.
Các Solodit source payload đã qua chuẩn hóa được ghi đúng là
`legacy_normalized_json`; không gọi chúng là API response nguyên bản.
HTTP captured_at phản ánh lúc tải bổ sung, không phải ngày audit hoặc ngày
crawl ban đầu. Metadata local không có crawl-time đáng tin thì không tự điền.

## Quy ước gắn nhãn

Người rà soát: assistant, dựa trên nội dung báo cáo; cần auditor review trước
khi dùng làm benchmark bảo mật chính thức. `vulnerable` nghĩa là code được báo
cáo gắn với lỗi, không phải kết luận exploit đã được tái hiện.

Các labels trong review_plan được lựa chọn độc lập với output `scan()`:

- Chọn representative Solidity URL, commit/PR và những block nêu rõ code lỗi,
  fix, PoC hoặc context. Generator chỉ chép nội dung đúng offset và tính hash.
- Không mặc định mọi code block là vulnerable; code của dependency có thể là context.
- Không mặc định fenced `solidity` là source: console output/transaction trace
  là negative. Solidity bị gắn nhãn `js` vẫn có positive target.
- Inline diff là candidate riêng; chưa coi nó đã được tách before/after hoặc
  resolve commit. Commit/PR URL giữ role unknown nếu chưa đọc từng hunk.
- URL Markdown report và issue là negative **cho code-file resolver**, vẫn có
  thể đi vào report resolver ở giai đoạn sau.
- Report offset là chỉ số ký tự Unicode Python, end-exclusive. Source line
  ranges là 1-based inclusive; không đồng nhất hai hệ tọa độ.
- Vai trò fix không chứng minh fix đúng. `unknown` được giữ khi thiếu căn cứ.

## Độ phủ và giới hạn

Có mẫu thực tế cho Markdown code, GitHub line range, URL không có dòng, branch
và pinned SHA, commit/PR, Gist, PoC/fix, diff, line-numbered snippet, code gắn
nhãn sai và input lẫn nhiều findings. Gist/file/PR được tải bổ sung chỉ ở một
tập con nhỏ; không tuyên bố toàn bộ links trong 35 findings đã resolve.

Chưa có cặp trùng Solodit–Code4rena được xác minh trong bộ thật. Cùng repo,
cùng fix commit hoặc cùng Gist **không** chứng minh cùng một finding.
Nhiều mẫu không có fenced snippet nhưng có link fix commit; không được gọi là
hoàn toàn không có code reference. Các khoảng trống này được kiểm tra bằng
controls giả lập và cần bổ sung mẫu thật khi có dữ liệu phù hợp.

Các HTTP errors giả lập có kỳ vọng contract cho retry/unavailable. Test ở giai
đoạn 2 kiểm tra replay fixture; policy production tương ứng chưa triển khai.
Không có điểm đánh giá engine hoặc knowledge extraction ở bước này.

## Chạy offline

Từ thư mục crawler:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_evidence_benchmark.py -q
.\.venv\Scripts\python.exe scripts/benchmark_evidence.py --output data/processed/evidence-current.json
```

Benchmark chỉ gọi `scan()` và probe fetcher qua `httpx.MockTransport`; URL lạ
bị từ chối. Unit tests chặn socket. Không dùng API key, .env hay BigQuery.
Không ghi đè baseline đã bàn giao khi so sánh phiên bản resolver mới; truyền
`--output` như trên. Các lỗi resolver được ghi thành baseline, không sửa nhãn
để hợp thức hóa hành vi hiện tại.

`selected_target_recall` = số positive targets khớp / số positive targets đã
gắn nhãn, trên các mẫu không quarantine. `forbidden_matches` chỉ đếm negatives
đã gắn nhãn bị phát hiện nhầm. Candidate chưa gắn nhãn không được tính là sai.
Vì labels không exhaustive, không báo global precision/F1 hoặc full recall.
Role/parse/resolution/dedup chưa được chấm bởi baseline candidate này.

Tái tạo corpus từ artifacts đã có và materialize nhãn đã review:

```powershell
.\.venv\Scripts\python.exe scripts/collect_evidence_benchmark.py
.\.venv\Scripts\python.exe scripts/build_evidence_annotations.py
```

Chỉ khi chủ động bổ sung snapshot mới mới dùng `--fetch-reports` hoặc
`capture_evidence_responses.py --fetch`; các script giữ cache hiện có.
Thay corpus cần review lại nhãn, version corpus và baseline. Code4rena parser
thay đổi cũng có thể đổi corpus, nên tests phải kiểm tra provenance và offsets.

## Việc chuyển sang giai đoạn 3–5

1. Dùng contract v1 để persist nguồn/evidence và processing state.
2. Dùng positive/negative targets này để sửa resolver theo từng nhánh.
3. Fix GitHubFetcher transport trước khi đánh giá remote resolution.
4. Bổ sung parser Solidity, field role và policy retry rồi mở rộng evaluator.
5. Xin auditor review labels và bổ sung nguồn/dự án khác trước khi công bố số đo.

## Kiểm chứng ngày 2026-09-29

- 12 test benchmark mới qua; chạy chung với 41 test contract v1: 53 passed.
- Toàn bộ suite: 119 passed, 8 failed; cùng tám lỗi legacy đã ghi ở giai đoạn 1.
- Baseline: 93/105 positive targets khớp (88,6%), 20/36 negative targets bị
  nhận nhầm. Không phải điểm precision hoặc độ chính xác phát hiện lỗ hổng.
- GitHub file targets: 19/20; inline snippets: 55/57; commit/PR URLs: 19/19;
  inline diff: 0/7; Gist: 0/2. Đây là nhận diện candidate, chưa phải tải source.
- Replay HTTP bộc lộ `GitHubFetcher._headers()` bị gọi bằng positional argument
  trong khi tham số được khai báo keyword-only. Cả hai probe resolve ref lỗi
  trước HTTP. Không sửa implementation để thay đổi baseline trong giai đoạn 2.
- `.gitattributes` giữ nguyên byte của raw/HTTP bodies khi checkout trên Windows
  hoặc Linux để các SHA-256 kiểm tra provenance không bị đổi do line endings.
