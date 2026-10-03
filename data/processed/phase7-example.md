# Ví dụ knowledge cho finding/evidence

[H-03] Risk of silent overflow in reserves update

**Trạng thái: needs_review — chưa duyệt, chưa chạy lại PoC.**

Revision: `krv_9da3e09fbf40cf2ca95d51610641e75346673ea4c340f88e774086f1606d71ac`

## Nguyên nhân gốc

Theo báo cáo, buy/sell ép giá trị uint256 xuống uint128 để cập nhật virtual reserves mà chưa kiểm tra giá trị có nằm trong miền uint128.

- Căn cứ: report snapshot `snp_2cfec3126f75b89ff0439e183970a01fa40893f4ad069b4d575bce708f648b1c`, dòng 9–9.

## Điều kiện ban đầu

Kịch bản minh họa của báo cáo sử dụng base token có 30 decimals; đây là cấu hình PoC, không phải kết luận rằng chỉ token 30 decimals mới gặp lỗi.

- Căn cứ: report snapshot `snp_2cfec3126f75b89ff0439e183970a01fa40893f4ad069b4d575bce708f648b1c`, dòng 41–41.

## Điều kiện khai thác cần kiểm chứng

Điều kiện cần xem xét là giá trị tại phép ép kiểu vượt type(uint128).max mà không bị kiểm tra trước đó; cần xác minh khả năng đạt giá trị này trong luồng giao dịch đầy đủ.

- Căn cứ: report snapshot `snp_2cfec3126f75b89ff0439e183970a01fa40893f4ad069b4d575bce708f648b1c`, dòng 9–9.
- Căn cứ: report snapshot `snp_2cfec3126f75b89ff0439e183970a01fa40893f4ad069b4d575bce708f648b1c`, dòng 93–93.

## Hành vi lỗi

Báo cáo mô tả giá trị có thể bị cắt khi ép xuống uint128 trước khi cập nhật virtualBaseTokenReserves hoặc virtualNftReserves.

- Căn cứ: report snapshot `snp_2cfec3126f75b89ff0439e183970a01fa40893f4ad069b4d575bce708f648b1c`, dòng 9–9.

## Tác động

Virtual reserves sai có thể phá vỡ quan hệ định giá xy=k, làm giá tính toán không chính xác và gây tổn thất tiềm năng cho người dùng hoặc chủ pool.

- Căn cứ: report snapshot `snp_2cfec3126f75b89ff0439e183970a01fa40893f4ad069b4d575bce708f648b1c`, dòng 33–33.

## Dấu hiệu trên code

Dấu hiệu cần review là phép ép uint128(...) trong cập nhật virtual reserves, kết hợp thiếu kiểm tra miền giá trị trước phép ép. Sự xuất hiện của cast đơn thuần chưa đủ kết luận có lỗi.

- Căn cứ: report snapshot `snp_2cfec3126f75b89ff0439e183970a01fa40893f4ad069b4d575bce708f648b1c`, dòng 26–26. Evidence link: `lnk_e24d882f337f0b5a6007b1f9a6ae0d7c2a24e84d1cd82c3a4284673f1d88b65a`.
- Căn cứ: report snapshot `snp_2cfec3126f75b89ff0439e183970a01fa40893f4ad069b4d575bce708f648b1c`, dòng 9–9.

## Cách sửa

Theo đề xuất trong báo cáo, kiểm tra giá trị không vượt type(uint128).max và revert trước khi ép kiểu; áp dụng cho cả đường buy và sell.

- Căn cứ: report snapshot `snp_2cfec3126f75b89ff0439e183970a01fa40893f4ad069b4d575bce708f648b1c`, dòng 93–93.

## Còn thiếu / cần kiểm tra

- Cần reviewer xác minh điều kiện khai thác và giới hạn áp dụng từ repo đầy đủ.
- PoC chưa được chạy lại trong phase 7.
- missing_category:limitations

Quote nguyên văn và liên kết evidence đầy đủ nằm trong phase7-overflow-draft.json và phase7-knowledge.json.
