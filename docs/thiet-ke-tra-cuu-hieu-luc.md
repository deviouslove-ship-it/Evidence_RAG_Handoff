# Thiết kế tra cứu toàn diện, hiệu lực và tổng hợp căn cứ (bản chốt)

Cập nhật 06/11/2026. Bản này thay các bản đề xuất v1, v2 trong hội thoại và là căn cứ triển khai
G0 → G5. Các quyết định của chủ sở hữu được ghi ở mục 1; phần còn lại là thiết kế kỹ thuật
đã rà soát nhất quán.

Tiến độ (07/11/2026): G0, G1.0, G1, G2, G3, G4, G5 đã triển khai (ADR-007, ADR-008, ADR-009);
trạng thái chi tiết và phần chưa kiểm chứng ở [implementation-status.md](implementation-status.md).

## 0. Mục tiêu và giới hạn

Hệ thống hỗ trợ cán bộ **tìm kiếm, tra cứu, hỏi đáp, tổng hợp, phân tích và gợi ý căn cứ** từ
kho văn bản, nhanh, đầy đủ, chính xác, minh bạch và kiểm chứng được. Hệ thống **không** đưa ra
quyết định nghiệp vụ; đánh giá và quyết định cuối cùng thuộc cán bộ chuyên môn.

| Tiêu chí | Ưu tiên |
|---|---|
| Tìm đủ văn bản liên quan, không bỏ sót căn cứ quan trọng | Rất cao |
| Xác định đúng hiệu lực | Rất cao |
| Trích dẫn đúng Điều/Khoản/Điểm, mở đúng PDF gốc | Rất cao |
| Tổng hợp, phân loại quy định | Rất cao |
| Giải thích nội dung | Trung bình |
| Phân tích, gợi ý | Bổ trợ |
| Suy luận tình huống phức tạp | Không là trọng tâm |
| Tự kết luận nghiệp vụ | Không thực hiện |

Không thiết kế quá mức: tận dụng mã, CSDL, phân quyền, giao diện hiện có; không quy trình phê
duyệt phức tạp; không bắt cán bộ xác nhận thủ công từng điều khoản; không thêm phụ thuộc AI
không cần thiết.

## 1. Quyết định đã chốt

| # | Chủ đề | Quyết định |
|---|---|---|
| D1 | Thể hiện hiệu lực | Hai trục riêng: **trạng thái hiệu lực** và **trạng thái xác minh** (Đã xác minh · Chưa xác minh · Không tìm thấy thông tin trong kho). "Đã xác minh" luôn kèm kết quả, nguồn, người và thời điểm. Không suy "còn hiệu lực" từ việc chưa thấy văn bản bãi bỏ |
| D2 | Thứ tự hiệu lực | Cấp văn bản trước, rồi Điều/Khoản/Điểm; mô hình dữ liệu hỗ trợ cấp điều khoản ngay từ đầu |
| D3 | Nhóm văn bản | Gom gốc, sửa đổi, bổ sung, thay thế, hợp nhất; mỗi văn bản vẫn xem độc lập, có nội dung sửa đổi nguyên văn và PDF gốc. Không tạo văn bản hợp nhất bằng AI |
| D4 | Nhóm nội dung | Danh mục mở rộng được, lưu trong CSDL; một khoản nhiều nhóm; khoản chưa có nhóm vẫn hiện; quy tắc gán khi đủ rõ, AI đề xuất, người được phân quyền rà soát |
| D5 | Dùng model | Local trước; LLM chỉ khi cần; mọi model qua Model Registry; bỏ số lượt cố định, thay bằng giới hạn cấu hình và kiểm soát chi phí; không gọi API vì thiếu dữ liệu |
| D6 | Xếp hạng | Không dùng Top-K để loại vĩnh viễn kết quả; rerank theo lô có trần; toàn bộ kết quả xem được qua phân trang, bộ lọc; đánh dấu đã/chưa rerank; không đưa hàng nghìn khoản vào một lượt LLM |
| D7 | Người xác nhận | Cán bộ được phân quyền; AI chỉ đề xuất; lưu người, thời gian, nội dung, căn cứ, lịch sử; duyệt theo nhóm nhưng từng quan hệ có bản ghi riêng |
| D8 | Nâng cấp Local → API | **Hybrid Auto**: tự chuyển API khi kết quả local không qua bộ kiểm tra chất lượng, hoặc khi người dùng chọn "phân tích sâu". Chỉ khi đã có căn cứ phù hợp. Tuân thủ quyền, trần chi phí, chính sách API. Chế độ Local Only tuyệt đối không gọi API |
| D9 | Văn bản hết hiệu lực | Mặc định ưu tiên văn bản còn hiệu lực đã xác minh và văn bản chưa xác minh (có nhãn); văn bản hết hiệu lực, bị thay thế vẫn tìm được qua bộ lọc hoặc nhóm riêng; tìm toàn bộ, đối chiếu lịch sử, tra theo thời điểm thì đưa cả vào kết quả. Không loại văn bản vì chưa xác minh |
| D10 | Quyền xác nhận hiệu lực | Dùng vai trò `REVIEWER` hiện có, thêm phạm vi theo danh mục; không thêm vai trò |
| D11 | Trần tổng hợp | Quản trị viên cấu hình số căn cứ và ngân sách token; danh sách kết quả luôn đầy đủ qua phân trang; tổng hợp theo nhóm hoặc đợt rồi ghép có kiểm chứng; báo "đã dùng N trong M căn cứ"; người dùng yêu cầu mở rộng được |
| D12 | Hỏi đáp khi chưa xác minh hiệu lực | Không chặn. Căn cứ đã kiểm nguồn (đúng tệp, đúng chữ, đúng trang) được giải thích, tóm tắt, tổng hợp kèm cảnh báo hiệu lực |
| D13 | Tìm toàn diện ≠ tổng hợp toàn diện | Tìm ưu tiên độ bao phủ; tổng hợp xử lý lần lượt các nhóm trong phạm vi, không lấy vài kết quả đại diện rồi coi là toàn bộ |
| D14 | Thời điểm | Phân biệt ngày tra cứu (`as_of_date`), ngày xác minh, ngày dữ liệu của kho |
| D15 | Bỏ sót | Danh sách căn cứ bắt buộc tìm thấy theo chủ đề kiểm thử, không xây Gold QA lớn |

## 2. Hai lớp kiểm chứng (giải D12)

| Lớp | Nghĩa | Điều kiện để dùng trong tra cứu, hỏi đáp | Hiện có |
|---|---|---|---|
| **Kiểm nguồn** | Văn bản được duyệt nguồn: đúng tệp (SHA-256), chữ khớp trang PDF, cây Điều/Khoản/Điểm neo được | **Bắt buộc** (bất biến hồ sơ bàn giao: chỉ văn bản đã duyệt vào kho chính thức) | Có (duyệt văn bản, duyệt hàng loạt cho dữ liệu thử) |
| **Xác minh hiệu lực** | Biết văn bản/khoản còn hay hết hiệu lực tại ngày tra cứu | **Không bắt buộc**; thiếu thì kèm cảnh báo | Chưa (G1, G3) |

Bản nháp chưa duyệt nguồn không vào tra cứu. Duyệt nguồn nhẹ: kiểm tự động bằng mã, người duyệt
xác nhận theo lô; không phải xác minh hiệu lực.

## 3. Mô hình dữ liệu

Tận dụng bảng sẵn có (`document_nodes.parent_id`, `page_end`, `node_amendments`,
`node_references`, `effectivity_snapshot_revisions`, `node_effective_intervals`, nhật ký kiểm
toán chuỗi băm); chỉ thêm cột và bảng nhỏ.

| Thay đổi | Giai đoạn | Mục đích |
|---|---|---|
| `node_source_spans(node_id, ordinal, source_span_id)` | G0 | Một khoản neo vào nhiều đoạn, mỗi trang một đoạn |
| Ghi `document_nodes.parent_id`, `page_end`, `path` có cấu trúc, thêm `citation_label` | G0 | Cây Điều → Khoản → Điểm; nhãn trích dẫn "Điểm a khoản 2 Điều 5" |
| Hàm `node_source_text_valid(node_id)` | G0 | Kiểm toàn bộ đoạn nguồn của một khoản (duyệt, mở trích dẫn) |
| `node_amendments`: thêm phạm vi (văn bản hay nút), đích cấp văn bản, đích chưa có trong kho (số hiệu chuẩn hóa, đường dẫn Điều/Khoản/Điểm), điều kiện, nguồn đề xuất (quy tắc, AI, người), độ tin cậy, phiên bản model, mã lô duyệt, `superseded_by` | G1 | Quan hệ hiệu lực cả hai cấp trong một bảng |
| `node_references.reference_kind` (căn cứ, hướng dẫn, hợp nhất, dẫn chiếu) | G1 | Quan hệ chỉ liên quan, không đổi hiệu lực |
| `document_effective_intervals` (theo snapshot) | G1 | Hiệu lực cấp văn bản; cấp nút chỉ lưu ngoại lệ, còn lại kế thừa |
| Cột `verification_state` trên hai bảng khoảng hiệu lực | G1 | Trục xác minh |
| `effectivity_attestations` | G1 | Bản xác nhận của người: đích, kết quả, khoảng thời gian áp dụng, nguồn, người, thời điểm, trạng thái (hiệu lực, cần xác minh lại, thu hồi) |
| `category_acl.can_review` | G1 | Phạm vi duyệt theo danh mục (D10) |
| `ai_usage_events`, chính sách giai đoạn trong Registry | G1.0 | Kiểm soát chi phí (D5) |
| Chỉ mục vector theo số chiều của model | G2 | Đổi model embedding không sửa lược đồ |
| `concept_terms` (từ điển khái niệm) | G2 | Mở rộng truy vấn có duyệt |
| `content_taxonomy`, `node_labels`, `labeling_rules` | G4 | Nhóm nội dung |

Lịch sử thay đổi quan hệ và bản xác nhận dùng nhật ký kiểm toán chuỗi băm hiện có cộng
`superseded_by` (không xóa bản cũ); không tạo thêm bảng sự kiện riêng.

## 4. Hiệu lực

**Trục A (hiệu lực):** Còn hiệu lực · Chưa có hiệu lực · Sửa đổi một phần · Tạm ngưng · Hết hiệu
lực · Bị thay thế · Chưa xác định.

**Trục B (xác minh):** Đã xác minh · Chưa xác minh · Không tìm thấy thông tin trong kho.

**Quy tắc cứng (trong mã, không cấu hình):**
1. "Còn hiệu lực + Đã xác minh" chỉ sinh từ bản xác nhận của người có nguồn và thời điểm.
2. Không có quan hệ chấm dứt → trục A "Chưa xác định" (kèm sự kiện đã biết, ví dụ "có hiệu lực
   từ D1"), trục B "Không tìm thấy thông tin trong kho".
3. Quan hệ do AI hoặc quy tắc đề xuất mà chưa duyệt không đổi trục A; chỉ thêm cảnh báo "có đề
   xuất chưa xác nhận".
4. Quan hệ có điều kiện, chuyển tiếp, hết thời hạn: không tự tính; trục A "Chưa xác định", nêu điều kiện.
5. Bản xác nhận tự chuyển "cần xác minh lại" khi kho có quan hệ mới chạm đích sau thời điểm xác minh.

**Thời điểm (D14).**
- `as_of_date`: ngày người dùng tra cứu; mọi trạng thái tính **tại ngày đó**, không lấy trạng
  thái hôm nay áp cho quá khứ hay tương lai.
- Ngày xác minh: bản xác nhận ghi khoảng thời gian nó khẳng định (`valid_for_from`,
  `valid_for_to` = ngày xác minh nếu là "còn hiệu lực"). Ngày tra cứu nằm ngoài khoảng đó → trục
  B "Chưa xác minh tại ngày tra cứu" kèm "đã xác minh tại D2".
- Ngày dữ liệu của kho: ngày xuất bản snapshot và ngày nạp văn bản mới nhất; luôn hiện "kho đến ngày D".
- Ngày tra cứu sau ngày dữ liệu: trục B tối đa "Chưa xác minh".

**Cấp văn bản và cấp điều khoản.** Hiệu lực của một khoản = dòng ngoại lệ cấp nút nếu có, nếu
không kế thừa cấp văn bản. Một văn bản bị bãi bỏ chỉ cần một dòng. Văn bản có nhiều ngày hiệu
lực (ví dụ Điều 2 Thông tư 28/2024 từ 01/8/2024, phần còn lại 01/7/2024) ghi ngoại lệ cấp Điều.

**Cho tới khi xong G3:** thanh cảnh báo cố định "Hiệu lực đến cấp Điều, Khoản, Điểm chưa được
xác minh; kết quả phản ánh hiệu lực cấp văn bản". Khoản thuộc văn bản đã được sửa đổi một phần
mà chưa ghép đích: "Văn bản đã được sửa đổi một phần; chưa xác định khoản này có bị ảnh hưởng".
Mức rà soát cấp điều khoản được **tính tự động** (mọi quan hệ đã biết nhắm vào văn bản đều đã
ghép nút và đã duyệt), không bắt người xác nhận thêm.

## 5. Quan hệ và nhóm văn bản

- Ảnh hưởng hiệu lực: sửa đổi, bổ sung, thay thế, bãi bỏ (toàn bộ, một phần), ngưng hiệu lực.
- Chỉ liên quan: hướng dẫn thi hành, căn cứ ban hành, dẫn chiếu, hợp nhất. Hướng dẫn và căn cứ
  không tạo nhóm, chỉ hiện ở "Văn bản liên quan".
- Nhóm theo văn bản gốc, tính khi truy vấn từ bảng quan hệ. Văn bản sửa nhiều gốc (Thông tư
  66/2023 sửa 55, 56, 57/2021) thuộc nhiều nhóm; danh sách phẳng chỉ hiện một thẻ "thuộc nhóm của…".
- Nội dung sửa đổi hiện nguyên văn từ văn bản sửa đổi (Điều, Khoản, trang, PDF). Có Văn bản hợp
  nhất trong kho thì dẫn tới nó như văn bản riêng; Văn bản hợp nhất dùng để đối chiếu, không là
  căn cứ duy nhất làm đổi hiệu lực.
- Nhận diện văn bản: số hiệu chuẩn hóa + loại + ngày ban hành + cơ quan (số Văn bản hợp nhất bị tái
  sử dụng). Khớp mơ hồ vào hàng đợi người.
- Lọc theo quyền: không lộ văn bản ngoài danh mục được cấp; chỉ ghi "có văn bản liên quan ngoài
  phạm vi được cấp quyền".
- Nạp văn bản mới thì tự thử khớp lại các đích "chưa có trong kho".

## 6. Tìm toàn diện, xếp hạng, phân trang

**Bốn kênh, hợp bằng RRF:** chính xác (số hiệu, Điều, cụm từ, từ khóa, không dấu, đã có) · theo
nghĩa (embedding local) · mở rộng khái niệm (từ điển duyệt + AI khi từ điển cho ít khái niệm hơn
ngưỡng; người dùng thấy và bỏ chọn được) · quan hệ văn bản (sửa đổi, hướng dẫn, hợp nhất của văn
bản đã khớp).

**Phạm vi trung thực.** Kênh chính xác đếm được đủ. Kênh theo nghĩa luôn trả láng giềng gần nhất,
nên có trần N và ngưỡng tương đối cấu hình, ghi rõ trong phạm vi tìm. Báo số khoản chỉ nhờ kênh
theo nghĩa hoặc quan hệ mà có. Kết quả luôn ghi danh mục đã tìm, số văn bản trong phạm vi, ngày dữ
liệu, và "chưa thấy trong kho", không "đã tìm hết mọi quy định".

**Bộ kết quả cố định theo lượt** (bộ nhớ phiên, có thời hạn; phiên ẩn danh không ghi bền); phân
trang đọc từ đó nên thứ tự ổn định; quyền kiểm lại khi mở từng trang.

**Rerank (D6):** theo lô trên N ứng viên đầu (cấu hình), phần sau giữ thứ tự RRF; không loại ứng
viên; trường `ranking` (đã/chưa rerank, số đã rerank, tổng); bộ lọc chạy trên toàn tập.

**Hiển thị theo hiệu lực (D9):** chế độ mặc định xếp nhóm "Còn hiệu lực (đã xác minh)" và "Chưa
xác minh hiệu lực" lên trước; "Hết hiệu lực, bị thay thế" là nhóm riêng thu gọn, vẫn được đếm. Chế
độ "Tìm toàn bộ", "Đối chiếu lịch sử", hoặc `as_of_date` khác hôm nay đưa tất cả vào cùng danh
sách. Bộ lọc trạng thái hiệu lực và trạng thái xác minh trên toàn tập.

Hỏi đáp (chat) giữ quy tắc phương án C (ADR-006): khoản hết hiệu lực không làm nhận định chính
trừ khi người dùng hỏi đích danh; vẫn hiện thành thẻ căn cứ kèm trạng thái.

## 7. Tổng hợp, giải thích, gợi ý

Ba lớp tách bạch trên giao diện: **Nguyên văn** (từ CSDL) · **Diễn giải** (AI, mỗi ý gắn mã căn
cứ) · **Gợi ý tham khảo** (việc nên xem tiếp, không phải khẳng định).

**Kiểm tra bằng mã cho mọi ý AI viết:** mã căn cứ phải thuộc tập đã cấp; số, ngày, số hiệu, tên
Điều/Khoản phải xuất hiện trong căn cứ gắn kèm; không chứa từ kết luận nghiệp vụ ("phải xử lý",
"đủ điều kiện", "quyết định") ngoài trích dẫn. Ý không qua thì bỏ hoặc gắn "chưa kiểm chứng".

**Tổng hợp toàn diện (D11, D13):** chia nhóm (theo nhóm nội dung nếu có, nếu không theo văn bản),
chia đợt theo ngân sách token; tóm tắt từng nhóm, ghép bằng mã. Hết ngân sách thì dừng và báo
"đã tổng hợp N trong M căn cứ, K nhóm còn lại"; nút "Tổng hợp tiếp" chạy đợt sau. Danh sách đầy đủ
luôn độc lập với ngân sách tóm tắt.

**Điều kiện chạy:** có ít nhất một căn cứ đã kiểm nguồn (D12). Không có căn cứ → "không tìm thấy
trong kho", không gọi model.

## 8. Chính sách model, Hybrid Auto (D5, D8)

| Việc | Xử lý |
|---|---|
| Tìm chính xác, cấu trúc, quan hệ, trích dẫn, bộ giải hiệu lực, kiểm tra ý AI | Mã nguồn |
| Embedding, rerank | Model local (Registry) |
| Mở rộng truy vấn | Từ điển, quy tắc; AI khi cần |
| Đề xuất quan hệ, gán nhãn | Tác vụ nền, local trước |
| Tóm tắt, giải thích, phân tích, gợi ý | Local trước; nâng cấp API theo D8 |

**Chế độ.** Giữ hai giá trị cấu hình `LOCAL` và `API` (không phá cấu hình đã triển khai):
- `LOCAL` = **Local Only**: chỉ endpoint loopback/LAN đã duyệt; không có đường ra API.
- `API` = **Hybrid Auto**: tuyến chính của mỗi giai đoạn được là hồ sơ local; thêm **hồ sơ nâng cấp**
  (public) cho giai đoạn tóm tắt/giải thích. Nâng cấp khi: (a) kết quả local không qua bộ kiểm tra
  ở mục 7, hoặc (b) người dùng bấm "Phân tích sâu". Không nâng cấp vì thiếu căn cứ, không tìm thấy,
  hay chưa xác minh hiệu lực. Áp đủ điều kiện egress hiện có (tên miền cho phép, người dùng có
  quyền AI ngoài, mọi danh mục nguồn cho phép xử lý ngoài) và trần chi phí. Giao diện ghi "đã dùng
  API ngoài"; nhật ký ghi lại.

**Giới hạn cấu hình theo giai đoạn** (thay số 2 lượt cố định): số lượt mỗi yêu cầu, token vào/ra,
thời gian chờ, số yêu cầu đồng thời, trần chi phí ngày/tháng theo hồ sơ. Vượt trần → hạ xuống
đường không dùng model (nguyên văn, nhóm theo quy tắc) và báo rõ. Mỗi lần gọi ghi
`ai_usage_events`.

**Giai đoạn trong Registry:** `answer` (đã có), `embedding`, `rerank`, `expand`, `relation`,
`label`, `summarize`. Đổi model chỉ đổi cấu hình; kết quả nền (nhãn, đề xuất quan hệ, vector) ghi
phiên bản model để tính lại.

## 9. Xác nhận quan hệ hiệu lực (D7, D10)

- Quyền: `REVIEWER` có `can_review` trên danh mục của văn bản đích hoặc nguồn.
- Người hoặc tác vụ đề xuất không tự xác nhận; AI không có quyền duyệt.
- Màn hình theo văn bản sửa đổi: liệt kê đề xuất (câu gốc kèm trang, đích đã khớp, hành động, ngày,
  nguồn đề xuất, độ tin cậy). Duyệt cả lô được; mỗi quan hệ một bản ghi kiểm toán, chung mã lô.
- Lưu người, thời gian, nội dung, căn cứ (nút chứa câu gốc), lịch sử (`superseded_by` + kiểm toán).
- Duyệt văn bản (kiểm nguồn) hiện thêm ngày ban hành, ngày hiệu lực đọc được để người duyệt xác
  nhận cùng lúc; không tạo bước riêng.

## 10. Phân vai

| Việc | Mã tự động | AI hỗ trợ | Người xác nhận |
|---|---|---|---|
| Chuyển Word/TXT, dựng cây, neo trang, cờ chất lượng chữ | Có | | Duyệt nguồn (đã có) |
| Ngày ban hành, ngày hiệu lực | Quy tắc | Câu bất thường | Khi duyệt nguồn |
| Quan hệ theo mẫu câu | Quy tắc | Câu phức | **Có** |
| Khớp số hiệu | Có | | Khi mơ hồ |
| Tính khoảng hiệu lực, xuất bản snapshot | Có | | |
| "Còn hiệu lực, đã xác minh" | | | **Có**, kèm nguồn, thời điểm |
| Nhóm văn bản, phạm vi tìm, kiểm trích dẫn | Có | | |
| Mở rộng khái niệm | Từ điển | Bổ sung | Duyệt từ điển; người dùng bỏ chọn |
| Embedding, RRF | Có | | |
| Rerank | | Model local | |
| Nhóm nội dung | Quy tắc đủ rõ | Phần còn lại | Rà soát theo lô |
| Tóm tắt, giải thích, gợi ý | Kiểm tra bằng mã | Có | Cán bộ đọc và quyết định |
| Kết luận nghiệp vụ | **Không thực hiện** | | |

## 11. Giai đoạn và rà soát nhất quán

| GĐ | Nội dung | Phụ thuộc | Kiểm tra kỹ thuật khi xong |
|---|---|---|---|
| **G0 Nền** | Neo nhiều trang (đoạn theo thứ tự đọc); `parent_id`, `page_end`, `path`, `citation_label`; dựng lại cây cho bản nháp cũ (chạy thử rồi áp dụng); cờ chất lượng lớp chữ | — | Bộ test hiện có; nạp và duyệt thử bộ dữ liệu thử trên DB tạm: tỷ lệ khoản neo được, tỷ lệ văn bản duyệt được; mở trích dẫn khoản vắt trang |
| **G1.0 Registry** | Giai đoạn mới; chính sách giới hạn cấu hình (bỏ 2 lượt cố định); `ai_usage_events`; hồ sơ nâng cấp (Hybrid Auto); API mode cho phép tuyến chính local | G0 | Local Only không gọi API; vượt trần hạ đường không model; không căn cứ thì 0 lượt gọi |
| **G1 Hiệu lực cấp văn bản** | Bảng và cột mục 3; đọc ngày, đọc quan hệ cấp văn bản (thay thế, bãi bỏ, danh mục hết hiệu lực, phần đầu Văn bản hợp nhất); khớp số hiệu; hàng đợi duyệt theo lô; bản xác nhận; snapshot; hiển thị hai trục và cảnh báo cấp điều khoản; `can_review` | G0, G1.0 | Chuỗi thật trong dữ liệu thử; hai trục không sinh "đã xác minh" khi thiếu bản xác nhận; bản xác nhận tự hạ |
| **G2 Tìm toàn diện** | Embedding local (qwen3-embedding qua Ollama); RRF; từ điển và mở rộng; kênh quan hệ; nhóm văn bản; bộ kết quả cố định; rerank theo lô; phạm vi tìm; hiển thị theo D9 | G0, G1 (nhóm, lọc hiệu lực) | Danh sách bắt buộc tìm thấy (D15); phân trang không trùng không sót; tắt từng kênh đo đóng góp |
| **G3 Hiệu lực cấp Điều/Khoản/Điểm** | Đọc "sửa đổi khoản X Điều Y như sau"; ghép đích theo cây (cần G0); ngày hiệu lực cấp Điều; mức rà soát tự tính; gỡ cảnh báo chung khi đủ | G0, G1 | Đo độ chính xác, độ phủ trên khoảng 30 quan hệ do người xác minh |
| **G4 Nhóm nội dung, tổng hợp** | Danh mục, quy tắc, nhãn AI và gán lười; rà soát theo lô; tổng hợp theo nhóm/đợt có kiểm tra; Hybrid Auto cho tóm tắt | G1.0, G2 | Không ý nào thiếu căn cứ; báo N/M đúng; khoản chưa có nhãn vẫn hiện |
| **G5 Chất lượng** | Rerank chuyên dụng khi có máy chủ; kiểm thử bao phủ liên tục; công cụ đổi model và tính lại; báo cáo xuất tệp | G2–G4 | — |

**Điểm nhất quán đã rà soát**

| # | Điểm | Cách giải |
|---|---|---|
| 1 | Enum `effective_status` trộn "chưa biết" vào trạng thái | Giữ enum cho trục A; thêm cột trục B; API thêm trường (cộng thêm) |
| 2 | Hồ sơ bàn giao ghi "tối đa 2 lượt LLM" là bất biến | ADR mới ở G1.0 thay bằng chính sách cấu hình |
| 3 | Dự phòng chỉ cùng vùng dữ liệu | Hồ sơ nâng cấp riêng, chỉ ở chế độ `API` |
| 4 | Chế độ `API` hiện bắt hồ sơ vùng `public` | G1.0 cho tuyến chính dùng hồ sơ local trong chế độ `API` |
| 5 | "Chỉ chạy tóm tắt khi có căn cứ đã xác minh" (v2) mâu thuẫn D12 | Sửa thành "đã kiểm nguồn" |
| 6 | "Chọn đại diện để tóm tắt" (v2) mâu thuẫn D13 | Tổng hợp theo nhóm/đợt, báo N/M |
| 7 | "Mức rà soát cần người xác nhận" (v2) mâu thuẫn 5.5 | Tự tính |
| 8 | Bảng `relation_events` riêng (v2) trùng nhật ký kiểm toán | Bỏ; dùng kiểm toán + `superseded_by` |
| 9 | Tìm theo nghĩa không có "toàn bộ" | Trần cấu hình, ghi trong phạm vi |
| 10 | Rerank không tất định làm lệch trang | Bộ kết quả cố định theo lượt |
| 11 | Ghép đích cấp Điều/Khoản cần cây đúng | G0 trước G3 |
| 12 | Nhóm văn bản có thể lộ văn bản ngoài quyền | Lọc theo quyền |
| 13 | Cột vector cố định 768 chiều | G2: chỉ mục theo chiều model |
| 14 | Kiểm khoản vắt trang ở đường tìm kiếm nóng tốn chi phí | Đường tìm kiếm kiểm đoạn đầu (khoản một trang vẫn kiểm đủ); duyệt và mở trích dẫn kiểm toàn bộ đoạn |

## 12. Kiểm thử (không dựa Gold QA)

- **Bao phủ (D15):** `evaluation/coverage/` gồm 5–8 chủ đề, mỗi chủ đề vài cách hỏi và danh sách
  căn cứ bắt buộc tìm thấy (số hiệu + Điều/Khoản). Đo tỷ lệ tìm thấy theo từng kênh.
- **Trích dẫn:** kiểm tự động mọi kết quả: chữ khớp trang, mã băm, đường dẫn Điều/Khoản/Điểm, mở đúng trang.
- **Hiệu lực:** chuỗi thật trong dữ liệu thử (55/2021 → 66/2023 → VBHN 43/2025; 29/2016 bị
  110/2021 bãi bỏ; 58/2026 và 96/2026 thay thông tư cũ; 28/2024 hai ngày hiệu lực).
- **Chống bịa:** số, ngày, số hiệu trong phần AI phải có trong căn cứ; hỏi văn bản ngoài kho trả
  "không tìm thấy trong kho"; không căn cứ thì 0 lượt gọi model.
- **Chi phí, chế độ:** Local Only không gọi API; vượt trần hạ đường không model.
