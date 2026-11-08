# Grouped evidence và claims

Evidence group tổ chức các nguồn theo vai trò: quy định chính, đối tượng, điều kiện, ngoại lệ, chuyển tiếp, thẩm quyền. Auto-merge chỉ là tổ chức UI, không làm mất identity của từng nguồn.

Mỗi claim phải có evidence IDs hợp lệ. Validator kiểm số/ngày/thời hạn, phủ định, modality và ngoại lệ. Validator trả `supported` hoặc `conditional`; không tuyên bố chứng minh ngữ nghĩa tuyệt đối.

Bộ nhớ, gợi ý, phân tích và câu hỏi tiếp theo không phải evidence.

## Quy tắc khử trùng lặp gợi ý (Suggestions Deduplication)

Trong bước tạo câu trả lời và gợi ý tham khảo:
- Căn cứ đã trích dẫn trong nhận định chính (`claims`) sẽ tự động được loại trừ khỏi tập căn cứ của gợi ý tham khảo (`suggestions`).
- Gợi ý chỉ đề xuất các căn cứ pháp lý liên quan bổ sung mà chưa xuất hiện trong các mệnh đề nhận định chính, bảo đảm người dùng nhận được các hướng tra cứu mới mà không bị lặp lại thông tin dư thừa.
