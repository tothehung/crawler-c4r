# Pilot 2 — SOL-MISSING-ACCESS-CONTROL-001

Đã xây một mẫu kiến thức về thay đổi cấu hình trái phép, có nguồn tham chiếu,
ba loại case và kiểm chứng trên EVM local. Đây là phần bổ sung phase 7;
chưa sinh rule hoặc tích hợp LLM verifier.

## Phạm vi và yêu cầu

Ví dụ synthetic có biến `feeRecipient`. Sau deployment, chỉ tài khoản deployer
(owner cố định) được thay đổi biến này. Không có payout, proxy, chuyển quyền
owner hoặc cơ chế role phức tạp trong fixture.

Điều kiện để xác nhận lỗi: một người không được phép thực hiện có đường gọi
đến thao tác ghi state, giao dịch thành công và thay đổi cấu hình trái chính sách.
Hàm external/public hoặc thiếu tên modifier `onlyOwner` không tự chứng minh lỗi.
Kiểm tra quyền có thể nằm trong thân hàm, modifier kế thừa hoặc caller.

Kiểm tra địa chỉ nhận khác zero là kiểm tra đầu vào, không thay thế kiểm tra quyền.
Case có guard dùng `require(msg.sender == owner, "unauthorized")` trước khi ghi.
Cần chứng minh owner vẫn thao tác được để tránh coi một hàm luôn revert là bản sửa đúng.

## Nguồn thực tế và giới hạn

Đã rà bộ mẫu 35 findings (34 mẫu được đánh giá) và dữ liệu local trong `data/findings.jsonl`;
chưa có finding khớp trực tiếp với setter cấu hình thiếu quyền như ví dụ này.
Nguồn bổ sung là [Sherlock Gitcoin issue 458](https://github.com/sherlock-audit/2023-09-Gitcoin-judging/issues/458).
Báo cáo mô tả `setPoolActive` thiếu quyền pool manager. Cơ chế tương tự với fixture,
nhưng protocol gốc đổi trạng thái pool, không phải `feeRecipient`.

Đã lưu API response, body báo cáo, commit response và code tại commit
`6430c8004017e96ae2f5aac365bdefd0b6eeea72` trong
[source](tests/fixtures/patterns/missing-access-control/source/manifest.json), kèm SHA-256,
URL và thời điểm capture. Commit này được resolve từ `main` tại thời điểm capture;
không khẳng định đây chính là commit của audit ban đầu.

Các đoạn dẫn chứng: báo cáo dòng 11 và 55; code dòng 216–222. Gói xuất chứa quote
và hash nguồn để truy ngược. Chưa thực thi PoC hoặc biên dịch toàn bộ protocol gốc.
Nhãn High/Sponsor Confirmed được lưu như metadata của nguồn, không áp dụng cho fixture.

Nguồn Sherlock được lưu **riêng như tài liệu tham chiếu bổ sung**, không nhập vào
database hoặc cộng vào corpus 34 findings. Schema hiện tại chỉ hỗ trợ source
Solodit/Code4rena. `database_binding` được giữ `null`, không tạo revision hoặc
finding-evidence ID giả. Vì vậy đây chưa phải một finding mới đã đi qua crawler
và resolver của hệ thống.

Cơ sở ngôn ngữ: [Solidity 0.8.24 — Restricting Access](https://docs.soliditylang.org/en/v0.8.24/common-patterns.html#restricting-access).

## Ba case

| Fixture | Ngữ cảnh | Nhãn |
|---|---|---|
| [UnsafeFeeConfig.sol](tests/fixtures/patterns/missing-access-control/UnsafeFeeConfig.sol) | External setter chỉ kiểm tra địa chỉ khác zero | `confirmed` |
| [GuardedFeeConfig.sol](tests/fixtures/patterns/missing-access-control/GuardedFeeConfig.sol) | Kiểm tra owner cố định trước ghi; chỉ có một setter | `false_positive_for_this_pattern` |
| [UnknownFragment.sol](tests/fixtures/patterns/missing-access-control/UnknownFragment.sol) | Chỉ có internal function, không biết caller và chính sách quyền | `insufficient_context` |

Runner đặt nguyên văn fragment vào hai contract giả định: `GuardedCaller` và
`UnguardedCaller`. Hai kết quả trái nhau minh họa rằng cần caller trước khi kết luận.
Các wrapper không được trình bày như code gốc đã cào.

## Thực nghiệm

Compiler `0.8.24`, EVM Shanghai, Ganache `7.9.2`, không dùng public RPC.
Tái sử dụng dependencies đã pin và lockfile từ `tools/cast-pattern`.

Ba tài khoản: owner, outsider A, outsider B. Mỗi contract chạy sáu giao dịch theo
cùng thứ tự; bốn contract tổng cộng **24 giao dịch** (không tính deployment và static call).

| Contract | Giao dịch của outsider | Giao dịch của owner |
|---|---|---|
| UnsafeFeeConfig | 3/3 thành công và thay đổi state trái phép | 3/3 thành công |
| GuardedFeeConfig | 3/3 revert, giữ nguyên state | 3/3 thành công |
| GuardedCaller | 3/3 revert, giữ nguyên state | 3/3 thành công |
| UnguardedCaller | 3/3 thành công và thay đổi state trái phép | 3/3 thành công |

Mọi recipient đều hợp lệ, khác zero và khác state trước giao dịch.
Trên đường có guard, static call xác nhận lý do `unauthorized`; sau đó vẫn gửi
giao dịch thật và kiểm tra receipt status 0 cùng state giữ nguyên. Lỗi transport
không được tính là kiểm tra quyền thành công. Runner còn kiểm tra owner không đổi.

Kết quả chỉ chứng minh thay đổi cấu hình trái phép. Chưa chứng minh chuyển hướng
phí, thiệt hại tài chính hoặc severity. Kết quả guarded chỉ áp dụng pattern và
đường gọi đã mô tả, không chứng minh toàn bộ contract an toàn.

## Kiến thức và dữ liệu bàn giao

- [Pattern JSON](tools/access-pattern/pattern.json): đủ tám nhóm kiến thức, mỗi claim có nguồn `basis`.
- [Execution report](data/processed/access-pattern-validation.json): actor, input, state, receipt, reason và hash.
- [Knowledge pack](data/processed/access-pattern-pack.json): pattern, source snapshot, trích dẫn, commit và kết quả kiểm chứng.
- [Validator](scripts/verify_access_pattern.py): kiểm tra offline và xuất pack; không ghi database.
- [Tests](tests/unit/test_access_pattern.py): từ chối caller giả, hash cũ, receipt/state/reason sai, owner bị chặn, thiếu case, nguồn không có và binding database giả.

Gói được đánh dấu `validated_candidate`, còn trạng thái tri thức là `needs_review`.
Kiểm tra tính nhất quán kỹ thuật không thay thế review chuyên môn của nội dung claim.
`basis` liên kết mức nguồn; riêng historical reference có trích dẫn theo dòng.

Kiểm thử hồi quy sau thay đổi: **239 passed, 2 skipped**; trong đó 13 test mới
kiểm tra pattern này. Hai test tích hợp Go engine được bỏ qua vì chưa cấu hình
`W3GOAUDIT_ENGINE` trong lần chạy; 24 giao dịch EVM nêu trên đã chạy độc lập thành công.

## Chạy lại

Nếu chưa cài dependencies, chạy trong `tools/cast-pattern`:

```powershell
pnpm install --ignore-scripts --frozen-lockfile
```

Tại root crawler:

```powershell
node tools/access-pattern/verify.cjs
.venv\Scripts\python.exe scripts/verify_access_pattern.py
.venv\Scripts\python.exe -m pytest tests/unit/test_access_pattern.py -q
```

Hai bước cuối dùng dữ liệu đã lưu, không cần mạng. Ganache có thể thông báo µWS
không khớp Node và chuyển sang JavaScript; lần chạy này thành công với fallback.

`scripts/capture_access_source.py` là bước acquisition công khai chỉ dùng khi chưa
có capture; nó từ chối ghi đè nguồn đã lưu. Không cần chạy lại để kiểm thử.
