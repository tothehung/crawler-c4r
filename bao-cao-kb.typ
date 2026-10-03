#import "@preview/sci-brain-slides:0.1.0": *

// Giữ theme và các layout của template gốc.
// Sửa author/institution ở đây hoặc truyền qua --input khi compile.
#let deck = setup(
  theme: sys.inputs.at("theme", default: "academic"),
  text-size: float(sys.inputs.at("text-size", default: "20")) * 1pt,
)
#let sizes = deck.sizes
#let pal = deck.palette
#let (spread, twocol, hero, cards) = deck.layouts
#let (figbox,) = deck.gadgets
#let source(body) = {
  v(12pt)
  text(sizes.caption, fill: pal.text_soft, body)
}

#show: deck.theme.with(
  lang: "vi",
  font: "Arial",
  config-info(
    title: [Knowledge Base cho audit Solidity],
    subtitle: [Crawler · Finding–Evidence · Knowledge],
    author: sys.inputs.at("author", default: "Tên sinh viên"),
    institution: sys.inputs.at("institution", default: "Tên trường / khoa"),
    date: [Báo cáo tiến độ · 30/09/2026],
  ),
)

#title-slide()

== Mục tiêu và phạm vi
#twocol([
  *Mục tiêu*
  #v(12pt)
  Chuyển báo cáo audit thành kiến thức có thể truy ngược về finding và code nguồn.
  #v(14pt)
  Hỗ trợ auditor kiểm tra nguyên nhân, điều kiện phát sinh và trường hợp báo nhầm.
], [
  *Phạm vi đã thực hiện*
  #v(12pt)
  - Crawler và pipeline evidence.
  - Knowledge có trích dẫn, phiên bản và trạng thái review.
  - Một pattern được kiểm chứng bằng ví dụ chạy trên EVM local.
])
#source[Chưa triển khai embedding hoặc tích hợp LLM verifier vào luồng audit tự động.]

== Pipeline đã triển khai
#twocol([
  *Thu thập và chuẩn hóa*
  #v(12pt)
  + Cào findings từ Solodit và Code4rena.
  + Lưu snapshot, định danh và fingerprint.
  + Trích xuất code block và URL trong báo cáo.
], [
  *Resolve và lưu evidence*
  #v(12pt)
  #enum(start: 4,
    [Resolve Markdown, GitHub và Gist.],
    [Kiểm tra code, ghi nhận lỗi hoặc thiếu ngữ cảnh.],
    [Lưu evidence, liên kết finding và trạng thái retry/resume.],
  )
])
#source[Luồng đã được kiểm chứng trên bộ mẫu đóng băng; không bảo đảm mọi finding đều lấy được code.]

== Bộ dữ liệu thực nghiệm
#cards([
  #text(sizes.xlarge, fill: pal.accent_deep)[35]
  #v(10pt)
  *Findings thực tế ban đầu*
  #v(10pt)
  20 Solodit và 15 Code4rena.
], [
  #text(sizes.xlarge, fill: pal.accent_deep)[34]
  #v(10pt)
  *Findings được đánh giá*
  #v(10pt)
  19 Solodit và 15 Code4rena.
])
#v(14pt)
Một mẫu bị quarantine vì nội dung lẫn nhiều findings.
#source[Nguồn: tests/fixtures/evidence_benchmark_v1/README.md. Đây là bộ phát triển, chưa phải tập đánh giá độc lập.]

== 26/34 findings có code evidence
#spread(
  figbox([Độ phủ evidence theo nguồn], [
    #grid(
      columns: (auto, 1fr, auto),
      column-gutter: 12pt, row-gutter: 24pt, align: horizon,
      [Solodit], rect(width: 57.9%, height: 25pt, fill: pal.primary, stroke: none), [11/19],
      [Code4rena], rect(width: 100%, height: 25pt, fill: pal.primary, stroke: none), [15/15],
      [Tổng], rect(width: 76.5%, height: 25pt, fill: pal.primary, stroke: none), [26/34],
    )
  ], caption: [Độ dài thanh biểu diễn tỷ lệ findings có evidence.]),
  [
    #text(sizes.xlarge, fill: pal.accent_deep)[76,5%]
    #v(14pt)
    8 findings chưa thu được code evidence.
    #v(14pt)
    Có evidence chưa đồng nghĩa đã xác nhận lỗ hổng.
  ],
)
#source[Nguồn: data/processed/phase6-quality.json.]

== Kết quả resolve evidence
#twocol([
  *100 evidence không trùng*
  #v(12pt)
  - 77 đoạn code inline.
  - 22 evidence từ GitHub file.
  - 1 evidence từ Gist.
  #v(12pt)
  Một evidence có thể được nhiều finding tham chiếu.
], [
  *154 bản ghi liên kết/ứng viên*
  #v(12pt)
  - 101 đã resolve được evidence.
  - 53 còn lỗi `fixture_missing`.
  #v(12pt)
  Thiếu phản hồi HTTP trong bộ replay; chưa thể kết luận link chết.
])
#source[Nguồn: phase4-resolution.json và phase6-quality.json; chạy bằng phản hồi HTTP đã ghi lại.]

== Kiểm tra code bằng parser
#spread(
  figbox([Trạng thái của 100 evidence], [
    #grid(
      columns: (1fr, auto), row-gutter: 18pt, column-gutter: 18pt,
      [Parse thành công], [*12*],
      [Thiếu ngữ cảnh], [*87*],
      [Parser đánh dấu invalid], [*1*],
    )
  ], caption: [Kết quả theo parser và phiên bản đã lưu.]),
  [
    Code trích từ báo cáo thường là fragment.
    #v(14pt)
    Cần thêm caller, khai báo hoặc dependency để đánh giá đầy đủ.
  ],
)
#source[Nguồn: phase5-validation.json. Parse thành công không chứng minh compile thành công hoặc có lỗ hổng.]

== Knowledge cho finding và evidence
#twocol([
  *Nội dung cần có*
  #v(10pt)
  - Nguyên nhân gốc.
  - Tiền điều kiện và điều kiện khai thác.
  - Hành vi và ảnh hưởng.
  - Dấu hiệu nhận diện, cách sửa.
  - Giới hạn và trường hợp báo nhầm.
], [
  *Khả năng truy vết*
  #v(10pt)
  Mỗi claim gắn với snapshot, dòng và quote nguồn; có thể tham chiếu evidence link.
  #v(14pt)
  Lưu revision và binding link → evidence để phát hiện thay đổi nguồn.
])
#source[Nhóm thông tin chưa trích xuất được được ghi nhận là thiếu; không tự điền thành kết luận.]

== 34 knowledge candidates đang chờ review
#hero[
  #text(sizes.xlarge, fill: pal.accent_deep)[34 candidates · 360 claims]
  #v(20pt)
  Đã kiểm tra trích dẫn khớp nội dung và dòng trong snapshot.
  #v(16pt)
  *0 bản đã duyệt chuyên môn.*
  #v(14pt)
  Đúng nguồn trích dẫn chưa chứng minh nhận định đúng về bảo mật.
]
#source[Nguồn: phase7-verification.json. Các draft chưa đầy đủ đồng đều tám nhóm kiến thức.]

== Case study: ép uint256 xuống uint128
#twocol([
  *Finding tham chiếu*
  #v(12pt)
  Caviar H-03: Risk of silent overflow in reserves update.
  #v(14pt)
  Pattern xét trường hợp nghiệp vụ cần giữ chính xác giá trị khi cập nhật state.
], [
  *Điều kiện cần xác minh*
  #v(12pt)
  Giá trị thực tế có thể vượt $2^128 - 1$ mà không bị kiểm tra trước cast.
  #v(14pt)
  Với giá trị runtime $"amount" = 2^128$, phép `uint128(amount)` cho kết quả 0.
])
#source[
  Nguồn: #link("https://github.com/code-423n4/2023-04-caviar-findings/issues/167")[Caviar H-03];
  #link("https://docs.soliditylang.org/en/v0.8.24/types.html#explicit-conversions")[Solidity 0.8.24 — chuyển kiểu].
]

== Ba tình huống cần phân biệt
#grid(
  columns: (1fr, 1.2fr), column-gutter: 24pt, row-gutter: 20pt,
  [*Không có guard*], [Đầu vào vượt miền vẫn được chấp nhận; giá trị lưu bị cắt → xác nhận lỗi trong fixture.],
  [*Có guard trước cast*], [Kiểm tra đúng giá trị gốc; vượt miền thì revert → loại trừ pattern này.],
  [*Chỉ có hàm internal*], [Chưa biết caller và ràng buộc đầu vào → giữ trạng thái thiếu ngữ cảnh.],
)
#source[Nguồn: tools/cast-pattern/pattern.json. Ví dụ synthetic; nhãn chỉ áp dụng cho pattern đang xét.]

== Kiểm chứng trên EVM local
#hero[
  #text(sizes.xlarge, fill: pal.accent_deep)[4 contracts × 39 đầu vào = 156]
  #v(18pt)
  Biên dịch bằng Solidity 0.8.24; chạy 156 giao dịch trên EVM local.
  #v(16pt)
  Kiểm tra receipt, giá trị lưu và state sau revert.
  #v(14pt)
  Cùng fragment được thử với hai caller có và không có guard.
]
#source[Nguồn: uint128-pattern-validation.json. Chưa tái hiện PoC Caviar gốc hoặc chứng minh thiệt hại tài chính.]

== Dữ liệu bàn giao và truy xuất
#twocol([
  *Số liệu và ví dụ*
  #v(12pt)
  - `phase6-quality.json`: chất lượng evidence.
  - `phase7-verification.json`: knowledge.
  - `phase7-example.md`: case study dễ đọc.
  #v(12pt)
  Các file nằm trong `data/processed/`.
], [
  *Dữ liệu đầy đủ*
  #v(12pt)
  SQLite: `phase4-replay.sqlite3` trong `data/checkpoints/`.
  #v(14pt)
  Lưu snapshot, code evidence, liên kết, processing state và knowledge revisions.
])
#source[Dữ liệu đầu vào và provenance: tests/fixtures/evidence_benchmark_v1/.]

== Giới hạn và bước tiếp theo
#cards([
  *Giới hạn hiện tại*
  #v(12pt)
  - Bộ phát triển có quy mô nhỏ.
  - Replay chưa phủ mọi URL.
  - Knowledge chưa được duyệt.
  - Chưa tích hợp LLM verifier.
], [
  *Thử nghiệm tiếp theo*
  #v(12pt)
  - Chọn project nhỏ có pattern phù hợp.
  - Đọc caller, guard và invariant.
  - Viết test trên project thực tế.
  - Review và mở rộng pattern.
])
#source[Hiện có thể hỗ trợ kiểm tra một pattern; chưa phải quy trình audit bảo mật toàn diện.]

#focus-slide[
  Đã có luồng crawler → evidence → knowledge candidate.
  #v(20pt)
  #text(sizes.normal)[Bước tiếp theo: kiểm chứng trên project thực tế và review kiến thức.]
]
