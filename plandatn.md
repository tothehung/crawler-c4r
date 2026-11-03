Kế hoạch nghiên cứu W3GoAudit
Thời gian: 04/10/2026–15/12/2026
Hướng nghiên cứu: Kết hợp rule-based scanning với AI-assisted triage có ngữ cảnh và bằng chứng mã nguồn.
Cách triển khai: Thử nghiệm nhỏ → kiểm chứng từng thành phần → mở rộng từng đợt nhóm lỗi → đánh giá toàn bộ phạm vi đã triển khai.
Các pattern ban đầu được dùng để kiểm chứng phương pháp; phạm vi tiếp tục mở rộng theo toàn bộ rule, dữ liệu và khả năng phân tích mà project có thể tiếp cận.
Các chỉ tiêu số lượng trong tài liệu là mục tiêu lập kế hoạch, cần rà lại theo phân bố dữ liệu, khả năng review và ngân sách thực tế. Đây không phải kết quả đã đạt hoặc ngưỡng bảo đảm đủ để công bố paper.
Nguồn dữ liệu chính là DB raw findings đã có. Công việc dữ liệu tập trung vào kiểm kê, chọn mẫu, liên kết evidence/source code đúng phiên bản và tạo benchmark từ nguồn hiện hữu. Chỉ bổ sung nguồn bên ngoài khi đã xác định khoảng trống cụ thể không thể giải quyết bằng DB hiện tại.
1. Mục tiêu cuối kỳ
Có pipeline hoàn chỉnh: scanner → chọn context → AI triage → bằng chứng → auditor review.
Kiểm kê toàn bộ rule trong phạm vi nghiên cứu; từng rule được đưa qua pipeline hoặc ghi rõ lý do chưa hỗ trợ.
Có benchmark đa nhóm lỗi, nhãn được review và development/test được tách theo project.
Có kết quả so sánh baseline, phân tích đóng góp của context và giới hạn theo từng nhóm.
Có bản thảo paper, prototype, dataset/artifact và hướng dẫn tái lập.
Hoàn thành slide và demo phục vụ báo cáo ngày 15/12/2026.
2. Nguyên tắc triển khai và đánh giá
Thử nghiệm trước khi mở rộng: mỗi nhóm mới phải đi qua các case phát triển trước khi đưa vào thực nghiệm chính.
Tách trạng thái triển khai và bằng chứng: đã có rule hoặc đã chạy AI không đồng nghĩa đã chứng minh hiệu quả trên nhóm lỗi đó.
Phân biệt cảnh báo và vulnerability: cảnh báo về thực hành lập trình cần được phân biệt với lỗ hổng có thể khai thác khi gán nhãn và báo cáo.
Bảo toàn dữ liệu gốc: lưu finding gốc, đề xuất AI và quyết định auditor thành các trường riêng.
Không ép nhãn: mẫu chưa đủ căn cứ được ghi rõ, không ép thành TP hoặc FP để đủ số lượng. Nhãn ground truth chưa xác định khác với quyết định uncertain của AI.
Tách dữ liệu phát triển và kiểm thử: không dùng tập test để chỉnh prompt, rule hoặc context policy; kiểm soát code gần trùng và audit report chứa đáp án.
Đánh giá trung thực: không đặt điều kiện AI phải cải thiện rồi mới báo cáo; giữ cả kết quả thất bại, uncertain và lỗi vận hành.
Phân biệt triage và phát hiện mới: nếu AI chỉ xử lý finding scanner đã sinh, kết quả không chứng minh khả năng tìm các lỗi scanner bỏ sót. Bước phát hiện mới, nếu bổ sung, cần đánh giá riêng.
Tái sử dụng DB hiện có: ưu tiên finding, snapshot, evidence, knowledge và source đã lưu. Số project được chọn phục vụ độ đa dạng và tách development/test, không phải chỉ tiêu crawl mới.
Chuẩn bị benchmark từ DB raw findings
Kiểm kê DB: số finding, nguồn, project, nhóm lỗi, mức trùng lặp, review status và khả năng liên kết source/commit. Chưa giả định DB đã đủ hoặc thiếu trước khi kiểm kê.
Chọn một tập con nhỏ cho pilot, lưu ID và phiên bản/snapshot để tái lập; không cần xử lý toàn bộ DB ngay từ đầu.
Tái sử dụng evidence/source đã có; chỉ resolve hoặc lấy thêm mã nguồn đúng phiên bản khi còn thiếu. Không coi việc bổ sung source là yêu cầu crawl lại audit findings.
Chạy scanner trên source được chọn hoặc tái sử dụng output có phiên bản phù hợp để tạo candidate pool cho bài toán triage. Nếu có chỉ snippet, ghi rõ giới hạn context và đánh giá riêng khi cần.
Đối chiếu cảnh báo scanner với raw findings, code và bản sửa, rồi review nhãn. Raw audit finding và cảnh báo scanner là hai loại bản ghi khác nhau; liên kết chúng bằng mapping có bằng chứng.
Không coi cảnh báo không xuất hiện trong audit report là FP. Nếu DB chủ yếu chứa lỗi đã được báo cáo, cần review thêm các cảnh báo scanner trên chính source hiện có để có tập TP/FP phù hợp. Fixture hoặc bản sửa dùng kiểm tra hành vi phải được đánh dấu riêng.
Chỉ lập task thu thập thêm khi có gap report: nhóm nào thiếu, thiếu source/commit hay nhãn/context, và vì sao DB hiện tại chưa đáp ứng.
3. Lịch tổng quan
Đợt	Thời gian	Trọng tâm	Mốc đầu ra
1	01–05/10	Xác định phạm vi và chuẩn bị pilot	Ma trận phạm vi, pilot specification, protocol v1
2	06–25/10	Chạy pilot từ đầu đến cuối	Pipeline nhỏ và pilot report
3	26/10–01/11	Sửa phương pháp và chuẩn hóa mở rộng	Pipeline v1, regression suite, expansion backlog
4	02–15/11	Mở rộng theo từng đợt nhóm lỗi	Pipeline đa nhóm và dataset v2
5	16–22/11	Hoàn thiện phạm vi và khóa thực nghiệm	Dataset, evaluator và cấu hình đóng băng
6	23–29/11	Thực nghiệm chính	Bảng kết quả, ablation và phân tích lỗi
7	30/11–06/12	Kiểm chứng và viết paper v1	Bản thảo đầy đủ và case study
8	07–15/12	Review, tái lập và bàn giao	Paper, artifact, slide và demo
4. Breakdown từng đợt
Đợt 1 — Xác định phạm vi và chuẩn bị pilot
Thời gian: 01–05/10/2026
Mục tiêu: Chọn được một thí nghiệm nhỏ có thể trả lời rõ AI và context giúp được gì.
ID	Task	Công việc cụ thể	Output cần đạt
1.1	Kiểm kê engine và DB raw findings	Liệt kê rule, nhóm lỗi và context engine lấy được. Kiểm kê DB theo nguồn, project, nhóm lỗi, duplicate, evidence/source/commit và review status. Phân biệt vulnerability với cảnh báo hỗ trợ review.	Ma trận phạm vi v1 và DB inventory: phần dùng được ngay, phần cần resolve/review và khoảng trống đã xác định.
1.2	Chọn pilot	Chọn 2–3 pattern có case lỗi, case loại trừ và case thiếu ngữ cảnh. Ưu tiên tận dụng pilot access control và narrowing cast hiện có.	Pilot specification: mô tả pattern, điều kiện áp dụng và kết quả mong đợi.
1.3	Thiết kế thí nghiệm	Chốt schema, baseline, cách gán nhãn, đo uncertain và xử lý lỗi vận hành. Khảo sát nghiên cứu gần nhất.	Protocol v1, schema triage và bảng related work.
Tiêu chí hoàn thành:
Mỗi pattern pilot có ít nhất một ví dụ cho cả ba tình huống: lỗi thật, cảnh báo sai và thiếu ngữ cảnh.
Fixture synthetic được đánh dấu riêng với dữ liệu thực tế.
Có quy tắc gán nhãn và bố trí người có chuyên môn hỗ trợ review.
Đợt 2 — Chạy pilot từ đầu đến cuối
Thời gian: 06–25/10/2026
Mục tiêu: Có pipeline nhỏ chạy được và xác định lỗi thiết kế trước khi mở rộng.
ID	Task	Công việc cụ thể	Output cần đạt
2.1	Tạo pilot từ DB hiện có	Chọn tập con raw findings phù hợp pattern pilot; tái sử dụng evidence/source và chỉ resolve phần thiếu. Chạy scanner hoặc dùng output có phiên bản phù hợp để chọn khoảng 20–30 cảnh báo pilot. Ưu tiên đa dạng project sẵn có; số lượng điều chỉnh theo inventory, không phải quota crawl mới. Review nhãn và bổ sung fixture riêng cho nhánh còn thiếu.	Pilot dataset v1, manifest ID/snapshot nguồn, mapping raw finding–scanner finding, source/commit và label sheet.
2.2	Xây bộ chạy AI	Gửi finding và function cho model; parse schema; xử lý timeout, retry, cache và lưu cấu hình.	CLI triage theo lô; raw response và log từng finding.
2.3	Bổ sung context ban đầu	Lấy caller/callee, modifier, guard, state và biểu thức liên quan tùy pattern. Ghi phần thiếu hoặc bị cắt.	Context bundle có file/dòng và thông tin độ đầy đủ.
2.4	So sánh pilot	So scanner gốc, bộ lọc tĩnh phù hợp, AI đọc function và AI đọc context. Review mọi trường hợp AI loại nhầm lỗi thật.	Pilot report: kết quả từng finding, lỗi pipeline và các thay đổi cần thực hiện.
Tiêu chí hoàn thành:
Tất cả mẫu pilot có kết quả hoặc lỗi được ghi rõ.
Có thể chạy lại và truy nguyên quyết định về input, prompt, model và context.
Phân biệt lỗi request/output với quyết định uncertain.
Không dùng kết quả pilot để tuyên bố hiệu quả tổng quát.
Đợt 3 — Sửa phương pháp và chuẩn hóa khả năng mở rộng
Thời gian: 26/10–01/11/2026
Mục tiêu: Thêm nhóm lỗi mới bằng cấu hình và bộ chọn context, tránh phải viết lại pipeline.
ID	Task	Công việc cụ thể	Output cần đạt
3.1	Phân tích lỗi pilot	Phân biệt lỗi rule, thiếu context, suy luận AI, citation và nhãn dữ liệu.	Taxonomy lỗi, mức ưu tiên sửa và ví dụ tái hiện.
3.2	Chuẩn hóa pipeline	Tách context chung và context theo nhóm; chuẩn hóa output, giới hạn token và cơ chế uncertain.	Pipeline v1 và giao diện bổ sung nhóm lỗi.
3.3	Tạo bộ kiểm tra hồi quy	Giữ các case từng gây lỗi; kiểm tra thay đổi mới không phá hành vi đã xác nhận.	Regression suite và báo cáo kiểm tra.
3.4	Lập các đợt mở rộng	Xếp nhóm theo dữ liệu và khả năng lấy context: nhóm sẵn sàng, nhóm cần bổ sung phân tích, nhóm phụ thuộc business context.	Expansion backlog; mỗi nhóm có task và tiêu chí hỗ trợ.
Tiêu chí hoàn thành:
Các lỗi kỹ thuật quan trọng của pilot đã được xử lý.
Các hạn chế suy luận còn lại được ghi rõ.
Có quy trình thêm nhóm mới và chạy lại bộ kiểm tra.
Không yêu cầu pilot đạt một tỷ lệ kết quả định trước mới được mở rộng.
Đợt 4 — Mở rộng theo từng đợt nhóm lỗi
Thời gian: 02–15/11/2026
Mục tiêu: Đưa các nhóm mới qua cùng quy trình kiểm chứng.
ID	Task	Công việc cụ thể	Output cần đạt
4.1	Mở rộng đợt A	Bổ sung các nhóm đã có rule và context tương đối sẵn: external call, delegatecall, reentrancy, token call, số học và các nhóm khác trong inventory.	Cấu hình nhóm, context selector và case kiểm tra tương ứng.
4.2	Mở rộng đợt B	Tiếp cận nhóm cần context rộng hơn: accounting, oracle, invariant, business flow. Xác định thông tin source code chưa cung cấp đủ.	Case study ban đầu; danh sách giả định và thông tin cần auditor bổ sung.
4.3	Mở rộng mẫu từ DB và review	Chọn thêm raw findings/evidence cho từng nhóm từ DB; tạo hoặc tái sử dụng cảnh báo scanner trên source tương ứng. Review cả TP và FP, đánh dấu mẫu chưa đủ căn cứ. Chỉ bổ sung nguồn ngoài DB khi có khoảng trống đã xác minh.	Dataset v2, manifest nguồn, thống kê phân bố/chất lượng nhãn và gap report nếu cần.
4.4	Tích hợp workspace	Hiển thị finding gốc, đề xuất AI, evidence và quyết định auditor riêng biệt.	Demo đa nhóm lỗi có thể thao tác và truy nguyên bằng chứng.
Tiêu chí hoàn thành:
Mỗi nhóm mới có mục tiêu 6–10 case phát triển được chọn từ dữ liệu hiện có nếu đủ; nhóm thiếu được ghi trong gap report, không mặc định phải crawl thêm.
Case synthetic được tách riêng; không tính thay cho finding thực tế.
Mỗi nhóm có ghi nhận context cần thiết, phần chưa resolve được và hành vi uncertain.
Số case phát triển chỉ dùng để kiểm tra chức năng, chưa được coi là đủ để kết luận nghiên cứu.
Đợt 5 — Hoàn thiện phạm vi và khóa thực nghiệm
Thời gian: 16–22/11/2026
Mục tiêu: Có phiên bản ổn định và tập test độc lập trước khi đo kết quả chính.
ID	Task	Công việc cụ thể	Output cần đạt
5.1	Rà toàn bộ inventory	Với từng rule/nhóm, xác nhận đã chạy, hỗ trợ một phần, thiếu dữ liệu hoặc chưa hỗ trợ.	Coverage matrix cuối, không để trạng thái mơ hồ.
5.2	Hoàn thiện benchmark từ dữ liệu đã chuẩn bị	Chốt số cảnh báo và phân bố project/nhóm lỗi dựa trên DB inventory, candidate pool và năng lực review; không áp quota project mới. Tách development/test theo project và code gần trùng; báo cáo số mẫu thực tế và các khoảng trống.	Dataset đóng băng, manifest truy về DB/source, split manifest và dataset card.
5.3	Kiểm tra evaluator	Xác nhận cách tính TP/FP, uncertain, finding trùng và lỗi request bằng ví dụ tính tay.	Evaluator có kiểm thử và định nghĩa chỉ số.
5.4	Khóa cấu hình	Cố định phiên bản scanner, rule, prompt, model, context policy và ngân sách chạy.	Experiment manifest và bản nháp Method.
Tiêu chí hoàn thành:
Không ép nhãn hoặc bổ sung mẫu dễ chỉ để đủ số lượng.
Nhóm thiếu dữ liệu vẫn nằm trong báo cáo phạm vi nhưng được giới hạn mức kết luận.
Không sử dụng tập test để điều chỉnh phương pháp.
Nếu có knowledge retrieval, kiểm soát báo cáo chứa đáp án và nguồn liên quan đến project test.
Đóng băng phương pháp ngày 22/11/2026.
Đợt 6 — Thực nghiệm chính
Thời gian: 23–29/11/2026
Mục tiêu: Đo hiệu quả và đánh đổi trên dữ liệu chưa dùng để chỉnh phương pháp.
ID	Task	Công việc cụ thể	Output cần đạt
6.1	Chạy baseline	Chạy scanner gốc, bộ lọc tĩnh phù hợp, AI đọc function và AI đọc context trên cùng candidate pool.	Raw output và bảng so sánh tổng thể/theo nhóm.
6.2	Chạy ablation	Bỏ từng thành phần context; đánh giá thêm knowledge nếu đã tích hợp và kiểm soát rò rỉ đáp án.	Bảng đóng góp của từng thành phần.
6.3	Chạy lặp	Mục tiêu 3 lần cho các cấu hình AI chính trong ngân sách đã chốt.	Độ biến động kết quả và tỷ lệ đổi nhãn.
6.4	Phân tích thất bại	Review TP bị loại, FP được giữ và uncertain; tách theo nguyên nhân.	Báo cáo thực nghiệm và danh sách case study.
Chỉ số bắt buộc:
Loại đúng FP: tỷ lệ cảnh báo sai được đề xuất loại trong tập cảnh báo sai có nhãn.
Loại nhầm TP: tỷ lệ cảnh báo đúng bị đề xuất loại trong tập cảnh báo đúng có nhãn.
Precision của nhóm AI xác nhận là lỗi thật.
Tỷ lệ uncertain và khối lượng còn cần review.
Tỷ lệ xử lý thành công; lỗi request/schema được báo cáo riêng.
Chi phí, độ trễ và độ ổn định qua các lần chạy.
Tiêu chí hoàn thành:
Có cả kết quả tổng thể và theo nhóm, kèm số mẫu và mẫu số của mỗi chỉ số.
Không loại uncertain hoặc lỗi vận hành khỏi báo cáo một cách âm thầm.
Phân biệt tỷ lệ cảnh báo sai FP/(TP+FP) với FPR FP/(FP+TN); chỉ báo cáo FPR khi xác định được tập âm và TN phù hợp.
Hiệu quả AI được báo cáo theo kết quả thực tế, không chỉ chọn lần chạy tốt nhất.
Thay đổi phương pháp sau khi xem test được ghi nhận và cần dữ liệu độc lập để đánh giá xác nhận.
Đợt 7 — Kiểm chứng và viết paper v1
Thời gian: 30/11–06/12/2026
Mục tiêu: Biến kết quả thực nghiệm thành lập luận nghiên cứu có bằng chứng.
ID	Task	Công việc cụ thể	Output cần đạt
7.1	Review kết quả quan trọng	Kiểm tra các quyết định sai ảnh hưởng kết luận; mọi sửa nhãn áp dụng nhất quán cho các baseline.	Review log và bảng kết quả đã kiểm tra.
7.2	Viết case study	Chọn 4–6 case thuộc nhiều nhóm: context có ích, AI sai, bộ lọc tĩnh đủ và thiếu thông tin.	Case study có source, evidence và giới hạn.
7.3	Đánh giá với người dùng nếu khả thi	Đo thời gian và độ đúng khi triage có/không AI; bố trí người tham gia từ sớm, tránh hiệu ứng nhớ đáp án.	Kết quả pilot với auditor; nếu không thực hiện thì không tuyên bố giảm thời gian auditor.
7.4	Hoàn thiện bản thảo	Ghép Introduction, Related Work, Method, Results, Discussion và Limitations.	Paper v1 đầy đủ ngày 06/12/2026.
Tiêu chí hoàn thành:
Các bảng và hình truy nguyên được về output benchmark.
Case study phản ánh cả thành công và thất bại.
Kết luận phân biệt rõ nhóm đủ bằng chứng và nhóm mới được khảo sát thăm dò.
Có bản thảo đọc được từ đầu đến cuối để nhận góp ý.
Đợt 8 — Review, tái lập và bàn giao
Thời gian: 07–15/12/2026
Mục tiêu: Có bộ kết quả người khác có thể đọc, kiểm tra và chạy lại.
ID	Task	Công việc cụ thể	Output cần đạt
8.1	Sửa theo góp ý	Xử lý vấn đề về claim, phương pháp, số liệu và diễn đạt.	Paper v2 và danh sách phản hồi.
8.2	Kiểm tra tái lập	Dựng môi trường sạch; chạy pipeline; tạo lại bảng từ raw output.	README, dependency/config cố định và báo cáo tái lập.
8.3	Đóng gói artifact	Rà dữ liệu chia sẻ, nguồn, commit, nhãn và giới hạn công bố.	Dataset/artifact package.
8.4	Chuẩn bị báo cáo	Làm slide, kịch bản demo và tổng hợp hạn chế còn tồn tại.	Paper, prototype, benchmark, slide và demo ngày 15/12/2026.
Tiêu chí hoàn thành:
Tính lại được các bảng kết quả từ raw output đã lưu.
Hướng dẫn chỉ rõ phần chạy offline và phần cần gọi model; không hứa tái tạo chính xác từng response AI.
Có phiên bản code, cấu hình và manifest tương ứng với paper.
Các giới hạn dữ liệu, triển khai và nghiên cứu được ghi rõ trong tài liệu bàn giao.
5. Baseline bắt buộc
Phương án	Vai trò
Scanner gốc	Xác định candidate pool và chất lượng cảnh báo ban đầu.
Scanner + bộ lọc tĩnh phù hợp	Kiểm tra phần cải thiện có thể đạt bằng các kiểm tra xác định; ghi rõ nhóm áp dụng được.
Scanner + AI đọc function	Baseline AI với context cục bộ.
Scanner + AI đọc context được chọn	Đánh giá phương pháp đề xuất.
Nếu tích hợp knowledge, thêm cấu hình có/không knowledge để đo riêng đóng góp. Các phương án triage cần xử lý cùng candidate pool; mọi khác biệt về phạm vi hỗ trợ phải được công khai.
6. Viết paper song song
Thời gian	Phần bản thảo
Tháng 10	Introduction, Related Work, bài toán và thiết kế đánh giá.
02–22/11	Method, kiến trúc pipeline, cách chọn context và dữ liệu.
23/11–06/12	Results, case study, Discussion và Threats to Validity.
07–15/12	Chỉnh sửa sau góp ý, rà claim, bảng, hình và tài liệu tham khảo.
7. Các mốc kiểm soát
11/10: Chốt pilot và protocol v1.
25/10: Có pilot report và danh sách lỗi phương pháp.
01/11: Pipeline đủ ổn định để thêm nhóm mới.
15/11: Có pipeline đa nhóm, dataset v2 và thống kê khoảng trống.
22/11: Khóa dataset và cấu hình thực nghiệm.
29/11: Hoàn thành kết quả chính và ablation.
06/12: Hoàn thành paper v1.
15/12: Bàn giao paper, prototype, artifact, slide và demo.
Một nhóm được thêm vào pipeline không tự động được xem là đã chứng minh hiệu quả. Trong toàn bộ kế hoạch, trạng thái triển khai, độ phủ dữ liệu và mức độ bằng chứng luôn được báo cáo riêng.

<ADDITIONAL_METADATA>
The current local time is: 2026-11-03T16:12:21+07:00.

The user's current state is as follows:
Active Document: c:\Users\ADM\DATN\crawler\ROADMAP.md (LANGUAGE_UNSPECIFIED)
Cursor is on line: 1
Other open documents:
- c:\Users\ADM\DATN\crawler\myplan.md (LANGUAGE_UNSPECIFIED)
- c:\Users\ADM\DATN\crawler\src\services\engine_bridge.py (LANGUAGE_UNSPECIFIED)
- c:\Users\ADM\DATN\crawler\src\clients\solodit_client.py (LANGUAGE_UNSPECIFIED)
- c:\Users\ADM\DATN\crawler\.env (LANGUAGE_UNSPECIFIED)
- c:\Users\ADM\DATN\crawler\src\models\ai_knowledge.py (LANGUAGE_UNSPECIFIED)
</ADDITIONAL_METADATA>
<USER_SETTINGS_CHANGE>
The user changed setting `Model Selection` from Gemini 3.8 Flash (High) to Claude Sonnet 4.6 (Thinking). No need to comment on this change if the user doesn't ask about it. If reporting what model you are, please use a human readable name instead of the exact string.
</USER_SETTINGS_CHANGE>