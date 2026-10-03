Tôi đề xuất chia thành **8 giai đoạn**, ưu tiên hoàn thành một luồng nhỏ chạy xuyên suốt trước, rồi mới xử lý toàn bộ findings. Kế hoạch bao gồm cả pipeline evidence vừa thống nhất và phần xây knowledge base phía sau.

**Pilot thứ hai:** [Missing access control](PATTERN_ACCESS_CONTROL.md) đã có mẫu
kiến thức, ba nhãn case và kiểm thử local; nguồn tham chiếu bổ sung lưu riêng.

**Cập nhật pilot audit KB:** đã thực hiện bước chọn pattern uint256 → uint128,
biên soạn kiến thức có nguồn và kiểm chứng ba loại case trên EVM local.
Xem [PATTERN_UINT128.md](PATTERN_UINT128.md). Đây là phần bổ sung phase 7;
chưa thực hiện tích hợp LLM verifier hoặc sinh WQL trong phase 8.

**1. Chốt schema và quy ước dữ liệu**

Đây là bước đầu tiên cần làm để crawler, resolver và engine dùng chung cách định danh.

- Định nghĩa các đối tượng: finding nguồn, evidence, liên kết finding–evidence, processing state và knowledge candidate.
- Thống nhất `source`, `source_id`, repo, commit SHA, đường dẫn tương đối, khoảng dòng và chữ ký hàm.
- Tách riêng severity, chất lượng finding, độ tin cậy evidence và độ tin cậy rule.
- Quy định fingerprint, versioning, trạng thái xử lý và điều kiện retry.
- Phân biệt code lỗi, code sửa, PoC và code ngữ cảnh.

**Đầu ra:** tài liệu data contract, schema mẫu và migration bổ sung.  
**Hoàn thành khi:** biểu diễn được một finding có nhiều evidence, evidence dùng chung và trường hợp thiếu source code.

**2. Chuẩn bị bộ dữ liệu mẫu và baseline**

Chọn khoảng **30–50 findings** từ dữ liệu đã cào, có đủ:

- Markdown chứa code block.
- GitHub file URL có hoặc không có khoảng dòng.
- Commit/PR diff và Gist.
- Link không truy cập được.
- Finding trùng giữa Solodit và Code4rena.
- Finding không có code, hoặc có cả code lỗi và code sửa.

Gắn nhãn thủ công những thông tin cần kiểm chứng: candidate cần trích, vai trò code và vị trí nguồn nếu xác định được.

**Đầu ra:** fixtures và kết quả kỳ vọng.  
**Hoàn thành khi:** có thể đo chất lượng từng bước mà không phụ thuộc hoàn toàn vào HTTP trực tiếp.

**3. Hoàn thiện lớp lưu trữ và điều phối**

Tận dụng crawler và BigQuery hiện có:

- Giữ finding nguồn và nội dung gốc để truy xuất lại.
- Bổ sung bảng evidence, bảng liên kết và processing state.
- Tính processing fingerprint theo nội dung và phiên bản pipeline.
- Ghi trạng thái `pending`, `running`, `succeeded`, `partial`, `failed`.
- Chỉ xác nhận hoàn tất sau khi dữ liệu đầu ra đã được lưu.
- Hỗ trợ chạy lại finding lỗi, nội dung thay đổi hoặc resolver được nâng cấp.

**Đầu ra:** một batch có thể lấy findings, xử lý, lưu và tiếp tục sau gián đoạn.  
**Hoàn thành khi:** chạy lại không nhân đôi dữ liệu và không bỏ qua batch chưa lưu thành công.

**4. Triển khai resolver theo thứ tự đơn giản đến phức tạp**

| Thứ tự | Thành phần | Công việc chính |
|---|---|---|
| 4.1 | Candidate extraction | Parse Markdown AST; lấy code block, URL và đoạn mô tả xung quanh |
| 4.2 | Inline code | Giữ code gốc, tạo bản chuẩn hóa riêng, lưu vị trí trong báo cáo |
| 4.3 | GitHub file | Resolve commit, tải file, lấy vùng code và context |
| 4.4 | Gist | Lấy nội dung từng file và revision |
| 4.5 | Commit/PR diff | Tách phía trước/sau sửa, gắn đúng revision và vị trí |
| 4.6 | Lỗi và cache | Timeout, retry, cache, trạng thái unavailable và lỗi từng candidate |

Trong bước này cần sửa các điểm đã thấy: `source` đang gán cứng, cách lưu `fixed_snippet` và provenance của code lấy từ diff.

**Đầu ra:** danh sách evidence có nguồn và trạng thái rõ ràng.  
**Hoàn thành khi:** một resolver lỗi không làm mất evidence từ các nhánh còn lại.

**5. Nối validation với engine**

Trước khi dùng engine làm giàu evidence:

- Sửa cách `extract context` tra function ID.
- Xử lý việc nhận diện hàm overload và contract trùng tên.
- Bổ sung kiểm thử cho các trường hợp trên.
- Thiết kế đầu ra validation dùng được từ Python: parse status, diagnostics, contract/function và khoảng dòng.
- Phân biệt file đầy đủ với fragment; ghi rõ mọi thao tác bọc hoặc biến đổi snippet.
- Với repo đủ context, trích thêm caller/callee, modifier, state variables và inheritance.

**Đầu ra:** evidence được kiểm tra bằng parser và có engine context khi khả thi.  
**Hoàn thành khi:** phân biệt được “có đoạn code”, “parse được” và “đủ context để phân tích”; không đánh đồng chúng.

**6. Chống trùng và vận hành trên dữ liệu lớn**

Triển khai riêng ba cơ chế:

- **Processing dedup:** tránh xử lý lại cùng phiên bản đầu vào.
- **Finding dedup:** liên kết cùng finding giữa các nguồn, giữ provenance.
- **Evidence dedup:** tái sử dụng evidence, giữ đủ quan hệ với findings.

Ưu tiên đối chiếu bằng định danh nguồn và URL chuẩn hóa; trường hợp chỉ giống nội dung nên ghi nhận là ứng viên trùng để kiểm tra.

Sau đó chạy batch lớn dần, theo dõi:

- Tỷ lệ findings có evidence.
- Tỷ lệ resolve/parse thành công theo nguồn.
- Lỗi, retry và thời gian xử lý.
- Số trường hợp trùng được liên kết.
- Tỷ lệ evidence xác định được vai trò.

**Đầu ra:** pipeline evidence có báo cáo chất lượng và khả năng resume.  
**Hoàn thành khi:** chạy thử có gián đoạn, chạy lại và nâng phiên bản đều cho kết quả nhất quán.

**7. Xây knowledge base từ findings và evidence**

> Cập nhật phạm vi theo yêu cầu ngày 2026-09-30: chỉ cần kiến thức cho finding/evidence;
> bỏ embedding, chunking và retrieval khỏi phần triển khai hiện tại. Nội dung kế hoạch
> gốc dưới đây được giữ để tham chiếu; phần retrieval không còn là điều kiện hoàn thành
> của đợt này. Kết quả và giới hạn thực tế nằm trong PHASE7.md.

Khi chất lượng evidence đã đo được, triển khai trích xuất:

- Nguyên nhân gốc.
- Điều kiện phát sinh và điều kiện khai thác.
- Hành vi lỗi và tác động.
- Dấu hiệu nhận diện trên code.
- Cách sửa.
- Giới hạn áp dụng và trường hợp dễ báo nhầm.

Mỗi nhận định phải liên kết tới finding hoặc evidence hỗ trợ. Tách knowledge candidate khỏi knowledge đã duyệt; lưu phiên bản và trạng thái review.

Sau đó mới xây chunking, embedding và retrieval, giữ liên kết về bản tri thức và nguồn gốc.

**Đầu ra:** knowledge có cấu trúc và khả năng truy xuất evidence.  
**Hoàn thành khi:** có bộ câu hỏi kiểm thử retrieval và kiểm tra được nguồn hỗ trợ cho kết quả trả về.

**8. Kết nối knowledge với WQL và vòng phản hồi**

- Phân loại pattern nào engine hiện có thể biểu diễn.
- Sửa parser `arg.N` và siết validation template trước khi sinh rule tự động.
- Sinh rule candidate kèm liên kết knowledge/evidence.
- Kiểm thử bằng ví dụ có lỗi và ví dụ an toàn.
- Review trước khi đưa vào rule registry có phiên bản.
- Giữ quan hệ giữa rule, scan finding và phản hồi của auditor.

**Đầu ra:** một số rule được xây từ findings thực tế, có bằng chứng và kiểm thử.  
**Hoàn thành khi:** truy ngược được từ kết quả scan về rule, knowledge và báo cáo nguồn.

Mốc triển khai nên chia như sau:

| Mốc | Phạm vi | Kết quả |
|---|---|---|
| **M1 — Luồng tối thiểu** | Giai đoạn 1–3 và resolver Markdown/GitHub file | Findings → evidence → lưu trữ → chạy lại an toàn |
| **M2 — Evidence hoàn chỉnh** | Phần còn lại của giai đoạn 4–6 | Nhiều resolver, engine validation, dedup và đo chất lượng |
| **M3 — Knowledge base** | Giai đoạn 7 | Tri thức có cấu trúc, review và retrieval |
| **M4 — Tích hợp rule** | Giai đoạn 8 | Knowledge → WQL → kiểm thử → phản hồi |

**Bước thực hiện đầu tiên là chốt data contract và bộ fixtures.** Hai phần này sẽ làm chuẩn cho mọi thay đổi sau đó; chưa cần bắt đầu bằng embedding hoặc sinh rule tự động.
