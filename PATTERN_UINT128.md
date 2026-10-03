# Pilot knowledge: uint256 → uint128

Đã thực hiện bước 1–3: chọn một pattern, biên soạn kiến thức có nguồn và kiểm chứng ba loại case. Đây là phần bổ sung cho phase 7, chưa tích hợp LLM verifier hoặc sinh rule cho engine.

## Kiến thức dùng để đánh giá finding

Pattern `SOL-UINT128-NARROWING-001` áp dụng khi hệ thống cần lưu chính xác giá trị nhưng ép `uint256` xuống `uint128`. Phép ép kiểu bỏ các bit cao; checked arithmetic không tự kiểm tra miền giá trị của phép chuyển đổi này. Căn cứ: [Solidity 0.8.24 — conversions](https://docs.soliditylang.org/en/v0.8.24/types.html#explicit-conversions) và [checked arithmetic](https://docs.soliditylang.org/en/v0.8.24/control-structures.html#checked-or-unchecked-arithmetic).

Muốn xác nhận lỗi phải chứng minh có đường thực thi cho **biểu thức thực tế được cast** vượt `2^128-1`, đồng thời việc cắt giá trị vi phạm yêu cầu của hệ thống. Chỉ thấy `uint128(...)` hoặc tham số `uint256` chưa đủ.

Điều kiện loại trừ: guard trên giá trị gốc trước cast trên mọi đường đi, hoặc invariant/caller bảo đảm miền giá trị. Đoạn internal function thiếu caller phải giữ trạng thái thiếu ngữ cảnh. Nếu thiết kế chủ động cần modulo thì phải kiểm tra ý định và invariant phía sau; không suy ra ý định chỉ từ comment hay `unchecked`.

Ảnh hưởng được chứng minh ở fixture là sai giá trị kế toán. Tổn thất tài chính và severity phải đánh giá riêng theo protocol. Cách sửa minh họa: kiểm tra `amount <= type(uint128).max` trước khi cast; kiểm tra sau khi giá trị đã bị cắt không đủ.

[Pattern JSON](tools/cast-pattern/pattern.json) chứa đủ tám nhóm: nguyên nhân, tiền điều kiện, điều kiện khai thác, hành vi, ảnh hưởng, dấu hiệu, cách sửa và giới hạn. Mỗi nhận định có `basis` tham chiếu nguồn.

## Ba case và kết quả

| Case | Kết quả mong đợi | Bằng chứng |
|---|---|---|
| [UnsafeReserve](tests/fixtures/patterns/uint128-narrowing/UnsafeReserve.sol) | `confirmed` | `record(2^128)` thành công nhưng lưu 0, trái yêu cầu lưu chính xác |
| [GuardedReserve](tests/fixtures/patterns/uint128-narrowing/GuardedReserve.sol) | `false_positive_for_this_pattern` | Guard kiểm tra đúng giá trị trước cast; quá miền thì revert và giữ nguyên state |
| [UnknownFragment](tests/fixtures/patterns/uint128-narrowing/UnknownFragment.sol) | `insufficient_context` | Cùng fragment trong hai caller giả định có/không có guard cho kết quả khác nhau |

Đã biên dịch bằng `solc 0.8.24` và chạy 156 giao dịch trên EVM local: 39 giá trị cho mỗi contract trong bốn contract (hai fixture đầy đủ và hai caller giả định). Có biên 0, max, max+1, max+2, max uint256 và giá trị bổ sung có seed cố định. Test kiểm tra receipt, state, truncation và revert. Không dùng public RPC.

Kết quả mẫu hữu hạn được bổ sung bằng lập luận miền giá trị của guard ngay trước cast. Nhãn an toàn chỉ áp dụng cho pattern này, không khẳng định toàn bộ contract an toàn.

## Liên kết finding/evidence hiện có

Nguồn thực tế: [Caviar H-03](https://github.com/code-423n4/2023-04-caviar-findings/issues/167), snapshot `snp_2cfec3126f75b89ff0439e183970a01fa40893f4ad069b4d575bce708f648b1c`.

Gói xuất [uint128-pattern-pack.json](data/processed/uint128-pattern-pack.json) liên kết revision, content hash và evidence bindings của finding trong SQLite. Script kiểm tra trích dẫn đúng dòng của snapshot và evidence vẫn đúng binding; database được mở read-only.

Pattern là kiến thức tổng hợp riêng, liên kết về case lịch sử. Các fixture được đánh dấu synthetic; không nhập chúng thành code evidence đã cào từ Caviar. Chưa tái hiện PoC của protocol gốc. Candidate vẫn là `needs_review`; `validated_candidate` chỉ nói kiểm tra kỹ thuật đã đạt, không thay thế review chuyên môn. Chưa có rule ID, embedding hoặc tích hợp LLM.

## Chạy lại

Từ thư mục `tools/cast-pattern`:

```powershell
pnpm install --ignore-scripts --frozen-lockfile
node verify.cjs
```

Từ thư mục crawler (cần database replay và draft phase 7 đã tạo):

```powershell
.venv\Scripts\python.exe scripts/verify_cast_pattern.py
.venv\Scripts\python.exe -m pytest tests/unit/test_cast_pattern.py -q
```

Compiler/runtime và dependency lock được cố định trong thư mục công cụ. Ganache có thể báo fallback sang JavaScript khi native µWS không khớp Node; lần kiểm chứng này chạy thành công bằng fallback. Bộ công cụ chỉ phục vụ fixture local.

Kết quả giao dịch: [uint128-pattern-validation.json](data/processed/uint128-pattern-validation.json). Validator từ chối hash fixture cũ, nhãn thiếu ngữ cảnh bị đổi thành confirmed, nguồn không tồn tại, thiếu input, receipt sai hoặc state thay đổi sau revert.
