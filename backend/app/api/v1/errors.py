"""Consistent API error handling."""

from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_MESSAGES = {
    "SEARCH_BUSY": "Máy chủ đang xử lý nhiều lượt tìm kiếm. Hãy thử lại sau vài giây.",
    "DATABASE_UNAVAILABLE": "Cơ sở dữ liệu tạm thời không thể truy cập.",
    "REVIEW_TASK_ALREADY_RESOLVED": "Tác vụ đã được xử lý; hãy tải lại danh sách rà soát.",
    "ADAPTER_UNSUPPORTED": "Bộ kết nối AI này chưa được triển khai.",
    "MODEL_STAGE_UNSUPPORTED": (
        "Chức năng không được hỗ trợ; hồ sơ embedding chỉ có vai trò embedding, "
        "các hồ sơ khác gắn một hay nhiều chức năng sinh văn bản."
    ),
    "EMBEDDING_PREFLIGHT_FAILED": (
        "Model embedding chưa qua kiểm tra; xem các mục lỗi trong kết quả kiểm tra."
    ),
    "EMBEDDING_PREFLIGHT_TIMEOUT": "Kiểm tra model embedding quá thời gian; hãy thử lại.",
    "EMBEDDING_JOB_EXISTS": (
        "Đã có tác vụ tạo vector cho model này; hãy tiếp tục hoặc thử lại tác vụ đó."
    ),
    "EMBEDDING_JOB_NOT_FOUND": "Không tìm thấy tác vụ tạo vector.",
    "EMBEDDING_JOB_STATE": "Trạng thái hiện tại của tác vụ không cho phép thao tác này.",
    "EMBEDDING_UP_TO_DATE": "Chỉ mục đang dùng đã có vector cho mọi nút; không cần tạo thêm.",
    "EMBEDDING_CONFIRMATION_REQUIRED": "Cần xác nhận trước khi tạo lại vector.",
    "REMOTE_EMBEDDING_DENIED": (
        "Chính sách máy chủ chưa cho phép tạo embedding bằng API bên ngoài."
    ),
    "MODEL_CAPABILITY_UNAVAILABLE": "Hồ sơ model không hỗ trợ giai đoạn đã chọn.",
    "MODEL_SECRET_REF_INVALID": (
        "Tham chiếu khóa không hợp lệ: chỉ dùng env:TEN_BIEN hoặc nhập khóa vào ô API Key."
    ),
    "MODEL_SECRET_INVALID": "Khóa API không hợp lệ (rỗng, nhiều dòng hoặc quá dài).",
    "MODEL_SECRET_UNAVAILABLE": "Không đọc được khóa API đã lưu; hãy nhập lại khóa.",
    "SECRET_STORE_UNAVAILABLE": (
        "Máy chủ chưa có kho lưu khóa (EVIDENCE_SECRET_STORE_DIR) hoặc hệ điều hành không "
        "hỗ trợ mã hóa; dùng biến môi trường env:TEN_BIEN."
    ),
    "MODEL_FALLBACK_CYCLE": "Các hồ sơ dự phòng tạo thành vòng lặp.",
    "MODEL_FALLBACK_ZONE_MISMATCH": "Hồ sơ dự phòng phải thuộc cùng vùng dữ liệu.",
    "AI_ENDPOINT_INVALID": (
        "Địa chỉ dịch vụ phải là URL hợp lệ kết thúc bằng /v1 (OpenAI, Ollama, vLLM), "
        "/v1beta/openai (Google Gemini), /openai/v1 hoặc /api/v1."
    ),
    "AI_EGRESS_DENIED": "Dịch vụ API chưa được cho phép trong chính sách kết nối của máy chủ.",
    "AI_LOCAL_ENDPOINT_DENIED": (
        "Local chỉ cho phép IP loopback hoặc IP nội bộ trong danh sách đã duyệt."
    ),
    "AI_REMOTE_ZONE_DENIED": "Hồ sơ nội bộ hoặc hạn chế không được dùng cho API bên ngoài.",
    "REMOTE_AI_DENIED": "Cấu hình hiện tại không cho phép gửi dữ liệu đến AI bên ngoài.",
    "PDF_WORKER_BUSY": "Đang có nhiều tài liệu được xử lý. Vui lòng thử lại sau.",
    "PDF_PARSE_TIMEOUT": "Xử lý PDF quá thời gian cho phép; hãy thử tệp nhỏ hơn.",
    "PDF_RESOURCE_LIMIT_EXCEEDED": "PDF vượt giới hạn tài nguyên xử lý của hệ thống.",
    "QUERY_TIMEOUT": "Tra cứu quá thời gian cho phép. Vui lòng thu hẹp câu hỏi và thử lại.",
    "QUERY_BUSY": "Hệ thống đang xử lý nhiều yêu cầu. Vui lòng thử lại sau.",
    "AUTH_BUSY": "Hệ thống đăng nhập đang bận. Vui lòng thử lại sau.",
    "TURN_IN_PROGRESS": "Lượt tra cứu này vẫn đang được xử lý.",
    "TURN_CANCELLED": "Lượt tra cứu đã dừng.",
    "REQUEST_CANCELLED": "Yêu cầu đã được hủy.",
    "MEMORY_CAPACITY_EXCEEDED": "Bộ nhớ phiên đã đạt giới hạn. Hãy xóa hoặc tạo lại phiên.",
    "SOURCE_SPANS_REQUIRE_REVIEW": "Vị trí trích dẫn chưa khớp nguyên văn trang PDF; cần rà soát.",
    "SOURCE_REEXTRACTION_CONFLICT": (
        "Dữ liệu trang hoặc PDF đã thay đổi; không thể tự động trích xuất lại."
    ),
    "DOCUMENT_TEXT_NOT_READY": "Tài liệu còn trang chưa đọc/kiểm chứng được hoặc chưa có nội dung.",
    "INVALID_REVIEW_STATE": "Chỉ có thể duyệt tài liệu đã gửi và đang chờ rà soát.",
    "AUTH_REQUIRED": "Bạn cần đăng nhập để sử dụng chức năng này.",
    "INVALID_PRINCIPAL": "Thông tin đăng nhập không hợp lệ.",
    "AUTH_PROVIDER_NOT_CONFIGURED": "Hệ thống chưa được cấu hình dịch vụ đăng nhập.",
    "QUERY_REQUIRED": "Bạn chưa được cấp quyền tra cứu.",
    "ADMIN_REQUIRED": "Chức năng này yêu cầu quyền quản trị.",
    "CURATOR_REQUIRED": "Chức năng này yêu cầu quyền biên tập nguồn.",
    "CURATOR_OR_REVIEWER_REQUIRED": "Chức năng này yêu cầu quyền biên tập hoặc duyệt nguồn.",
    "DRAFT_STORE_NOT_CONFIGURED": "Kho tài liệu nháp chưa được cấu hình.",
    "DOCUMENT_NOT_FOUND": "Không tìm thấy văn bản hoặc phiên bản trong phạm vi của bạn.",
    "DOCUMENT_EDIT_DENIED": "Bạn chưa được giao quyền sửa phiên bản này.",
    "DOCUMENT_REVIEW_SCOPE_REQUIRED": "Bạn chưa được giao quyền duyệt các danh mục của văn bản.",
    "DOCUMENT_REVISION_CONFLICT": "Phiên bản đã thay đổi. Hãy tải lại trước khi thao tác.",
    "DOCUMENT_CATEGORIES_CHANGED": "Danh mục của văn bản đã thay đổi. Hãy tải lại để duyệt.",
    "DOCUMENT_REPROCESS_REQUIRED": "Hãy xử lý lại văn bản trong mục Quản lý văn bản.",
    "OCR_EDIT_DENIED": "Chỉ có thể sửa chữ OCR hoặc trang scan chưa đọc được.",
    "PAGE_OUT_OF_RANGE": "Số trang PDF không hợp lệ hoặc vượt quá tổng số trang của tài liệu.",
    "OCR_AI_IDEMPOTENCY_CONFLICT": "Mã yêu cầu OCR AI đã được dùng cho trang hoặc phiên bản khác.",
    "OCR_AI_QUEUE_FULL": "Hàng đợi OCR AI đang đầy (tối đa 20 tác vụ). Vui lòng thử lại sau.",
    "OCR_AI_PROPOSAL_NOT_FOUND": "Không tìm thấy đề xuất OCR AI.",
    "OCR_AI_PROPOSAL_NOT_READY": "Đề xuất OCR AI chưa sẵn sàng hoặc đã hết hiệu lực.",
    "OCR_AI_PROPOSAL_INVALID_STATE": "Trạng thái đề xuất OCR AI không cho phép thao tác này.",
    "OCR_AI_PDF_REQUIRED": "Chỉ hỗ trợ đọc trang bằng OCR AI cho tài liệu PDF.",
    "OCR_AI_TEXT_EMPTY": "Văn bản áp dụng không được để trống.",
    "OCR_AI_TEXT_TOO_LARGE": "Văn bản OCR AI vượt quá giới hạn ký tự cho phép.",
    "OCR_AI_INTERRUPTED": "Tác vụ OCR AI bị gián đoạn khi khởi động lại hệ thống.",
    "OCR_AI_OUTPUT_INVALID": "Kết quả OCR AI không đúng định dạng yêu cầu.",
    "OCR_AI_TIMEOUT": "Tác vụ OCR AI quá thời gian xử lý cho phép.",
    "OCR_AI_CANCELLED": "Tác vụ OCR AI đã bị hủy.",
    "OCR_AI_NOT_CONFIGURED": "Chưa cấu hình model OCR cục bộ cho tác vụ này.",
    "OCR_AI_DISABLED": (
        "OCR AI chưa bật trên máy chủ. Quản trị viên cần bật EVIDENCE_OCR_AI_ENABLED "
        "rồi khởi động lại."
    ),
    "OCR_AI_EXPIRED": "Tác vụ đọc trang đã hết hạn. Hãy gửi yêu cầu mới.",
    "OCR_AI_MODEL_CHANGED": "Cấu hình hoặc model OCR đã thay đổi. Hãy tạo lại yêu cầu đọc trang.",
    "PAGE_TEXT_TASK_NOT_FOUND": "Không tìm thấy tác vụ đọc trang PDF.",
    "EFFECTIVITY_PROCESSING_FAILED": "Chưa cập nhật được dữ liệu hiệu lực. Hãy thử duyệt lại.",
    "DRAFT_NOT_FOUND": "Không tìm thấy tài liệu nháp.",
    "DRAFT_PDF_UNAVAILABLE": "Bản PDF gốc không thể xác minh hoặc truy cập.",
    "DUPLICATE_PDF_HASH": "Bản PDF này đã được nhập.",
    "INVALID_PDF_MAGIC": (
        "Tệp không phải PDF hợp lệ. Hãy chọn tệp PDF, Word (.doc, .docx) hoặc TXT."
    ),
    "INVALID_PDF_STRUCTURE": "Tệp PDF bị cắt hoặc hỏng.",
    "PDF_PARSE_FAILED": "Không đọc được nội dung tệp PDF.",
    "UNSUPPORTED_FILE_TYPE": (
        "Định dạng tệp chưa được hỗ trợ. Hãy dùng PDF, Word (.doc, .docx) hoặc TXT."
    ),
    "DOCUMENT_ENCRYPTED": "Tệp đặt mật khẩu; hãy bỏ mật khẩu rồi nhập lại.",
    "DOCUMENT_TEXT_EMPTY": (
        "Tệp không có chữ để đọc (có thể chỉ chứa ảnh scan). Hãy chuyển thành PDF rồi dùng OCR."
    ),
    "DOCUMENT_CONVERT_FAILED": "Không chuyển được tệp sang PDF; tệp có thể bị hỏng.",
    "TXT_ENCODING_UNSUPPORTED": "Không nhận ra bảng mã của tệp TXT. Hãy lưu lại ở dạng UTF-8.",
    "PDF_SIZE_LIMIT_EXCEEDED": "Tệp vượt giới hạn dung lượng tải lên.",
    "PDF_PAGE_LIMIT_EXCEEDED": "Tài liệu vượt giới hạn số trang cho phép.",
    "INVALID_DOCUMENT_METADATA": "Thông tin tài liệu bắt buộc không hợp lệ.",
    "SESSION_EXPIRED": "Phiên đã hết hạn hoặc không còn khả dụng.",
    "TURN_NOT_FOUND": "Không tìm thấy lượt tra cứu.",
    "MEMORY_ITEM_NOT_FOUND": "Không tìm thấy mục bộ nhớ.",
    "IDEMPOTENCY_KEY_REQUIRED": "Yêu cầu thiếu mã chống gửi lặp.",
    "IDEMPOTENCY_KEY_REUSED": "Mã chống gửi lặp đã được dùng cho nội dung khác.",
    "RUN_MISMATCH": "Luồng sự kiện không thuộc lượt tra cứu hiện tại.",
    "INVALID_LAST_EVENT_ID": "Mã tiếp tục luồng sự kiện không hợp lệ.",
    "RETENTION_NOT_APPROVED": "Chính sách lưu hội thoại chưa được phê duyệt.",
    "RETENTION_UNAVAILABLE": "Lưu hội thoại dài hạn chưa được triển khai; chỉ hỗ trợ phiên tạm.",
    "PREFERENCE_DATE_UNAVAILABLE": (
        "Chưa hỗ trợ đặt ngày mặc định; hãy chọn ngày cho từng lượt tra cứu."
    ),
    "CITATION_INVALID": "Căn cứ không tồn tại hoặc không thể truy cập.",
    "CITATION_SOURCE_UNAVAILABLE": "Bản PDF gốc của căn cứ hiện không thể xác minh hoặc truy cập.",
    "DOCUMENT_STORE_NOT_CONFIGURED": "Kho tài liệu nguồn chưa được cấu hình.",
    "DATABASE_NOT_CONFIGURED": "Cơ sở dữ liệu chưa được cấu hình.",
    "INVALID_CREDENTIALS": "Tên đăng nhập hoặc mật khẩu không đúng.",
    "ACCOUNT_DISABLED": "Tài khoản đã bị vô hiệu hóa.",
    "ACCOUNT_LOCKED": "Tài khoản tạm khóa do đăng nhập sai nhiều lần. Vui lòng thử lại sau.",
    "PASSWORD_CHANGE_REQUIRED": "Bạn cần đổi mật khẩu lần đầu trước khi sử dụng chức năng này.",
    "PASSWORD_TOO_SHORT": "Mật khẩu mới phải có ít nhất 12 ký tự.",
    "PASSWORD_TOO_LONG": "Mật khẩu vượt quá độ dài cho phép.",
    "PASSWORD_EQUALS_USERNAME": "Mật khẩu không được trùng tên đăng nhập.",
    "PASSWORD_UNCHANGED": "Mật khẩu mới phải khác mật khẩu hiện tại.",
    "REVIEWER_REQUIRED": "Chức năng này yêu cầu quyền duyệt nguồn.",
    "AUDITOR_REQUIRED": "Chức năng này yêu cầu quyền kiểm toán.",
    "SELF_APPROVAL_DENIED": "Người biên tập không được tự phê duyệt bản nháp của chính mình.",
    "REVIEW_SCOPE_REQUIRED": "Tài khoản chưa được giao quyền duyệt hiệu lực cho danh mục này.",
    "RELATION_NOT_FOUND": "Không tìm thấy quan hệ hiệu lực.",
    "RELATION_ALREADY_REVIEWED": "Quan hệ này đã được xử lý.",
    "RELATION_TARGET_REQUIRED": "Phải chọn văn bản (hoặc Điều, Khoản) đích trước khi duyệt.",
    "RELATION_DATE_REQUIRED": "Phải có ngày áp dụng trước khi duyệt quan hệ.",
    "ATTESTATION_FUTURE_DATE": "Bản xác nhận 'còn hiệu lực' chỉ khẳng định đến ngày xác minh.",
    "ATTESTATION_NOT_FOUND": "Không tìm thấy bản xác nhận.",
    "SOURCE_NODE_NOT_FOUND": "Không tìm thấy đoạn nguồn đã duyệt.",
    "RESULT_SET_EXPIRED": "Bộ kết quả đã hết hạn; hãy tìm lại.",
    "CONCEPT_EXISTS": "Khái niệm này đã có trong từ điển.",
    "CONCEPT_NOT_FOUND": "Không tìm thấy khái niệm.",
    "CONTENT_GROUP_EXISTS": "Nhóm nội dung này đã có.",
    "AI_NOT_CONFIGURED": "Chưa cấu hình model cho giai đoạn này.",
    "CONTENT_GROUP_NOT_FOUND": "Không tìm thấy nhóm nội dung.",
    "OPEN_REVIEW_TASKS_REMAIN": "Còn tác vụ rà soát mở chưa được xử lý trước khi phê duyệt.",
    "SOURCE_URL_REQUIRED": "Phải có đường dẫn nguồn chính thức trước khi phê duyệt.",
    "CATEGORY_REQUIRED": "Vui lòng chọn ít nhất một danh mục trong phạm vi đã chọn.",
    "USER_NOT_FOUND": "Không tìm thấy tài khoản người dùng.",
    "CATEGORY_NOT_FOUND": "Không tìm thấy danh mục.",
    "PROVIDER_NOT_FOUND": "Không tìm thấy provider.",
    "PROFILE_NOT_FOUND": "Không tìm thấy hồ sơ model.",
    "DUPLICATE_RESOURCE": "Bản ghi đã tồn tại.",
    "QUERY_EMPTY": "Vui lòng nhập từ khóa hoặc cụm từ cần tìm.",
    "QUERY_TOO_LONG": "Câu tìm kiếm quá dài. Rút gọn câu tìm kiếm rồi thử lại.",
    "TOO_MANY_TERMS": "Câu tìm kiếm có quá nhiều từ. Giữ tối đa 20 từ.",
    "PAGE_TOO_DEEP": (
        "Bạn đã xem tới giới hạn kết quả. Hãy thu hẹp bằng bộ lọc hoặc dùng từ khóa "
        "cụ thể hơn."
    ),
    "RATE_LIMITED": "Bạn tìm kiếm quá nhanh. Thử lại sau vài giây.",
    "SEARCH_TIMEOUT": (
        "Tìm kiếm mất quá nhiều thời gian. Thu hẹp bộ lọc hoặc bớt từ khóa rồi thử lại."
    ),
    "COMPARE_SAME_TARGET": (
        "Hai vế so sánh trùng nhau; hãy chọn hai phiên bản hoặc hai văn bản khác nhau."
    ),
    "COMPARE_VERSION_NOT_FOUND": (
        "Không tìm thấy phiên bản đã duyệt và kiểm chứng nguồn trong phạm vi của bạn."
    ),
    "COMPARE_DOCUMENT_TOO_LARGE": (
        "Văn bản vượt quá 1500 nút mỗi bên; hãy chọn phạm vi hẹp hơn (Chương/Điều) "
        "rồi so sánh lại."
    ),
    "COMPARE_MODE_MISMATCH": (
        "Chế độ so sánh không khớp lựa chọn: chế độ 'versions' cần cùng một văn bản "
        "và hai phiên bản khác nhau."
    ),
    "INVALID_REQUEST": "Dữ liệu gửi lên không hợp lệ.",
    "CONFLICT_RUN_NOT_FOUND": "Không tìm thấy lượt rà soát mâu thuẫn trong phạm vi của bạn.",
    "CONFLICT_FINDING_NOT_FOUND": "Không tìm thấy phát hiện mâu thuẫn.",
    "AUTHORITY_RULE_NOT_FOUND": "Không tìm thấy quy tắc thứ bậc hiệu lực.",
    "TARGET_NODE_NOT_FOUND": "Không tìm thấy điều khoản đích đã duyệt.",
    "CONFLICT_SCAN_IDEMPOTENCY_CONFLICT": (
        "Mã yêu cầu rà soát đã được dùng cho phạm vi hoặc tham số khác."
    ),
    "CONFLICT_SCAN_INVALID_STATE": (
        "Trạng thái hiện tại của lượt rà soát không cho phép thao tác này."
    ),
    "CONFLICT_FINDING_ALREADY_LINKED": (
        "Phát hiện này đã được gắn với một đề xuất sửa đổi trước đó."
    ),
    "CONFLICT_FINDING_DISMISSED": (
        "Phát hiện đã bị bác bỏ; không thể tạo đề xuất sửa đổi."
    ),
    "INVALID_REGEX_PATTERN": "Biểu thức chính quy (regex) của cơ quan ban hành không hợp lệ.",
    "CONFLICT_SCAN_TOO_MANY_DOCUMENTS": (
        "Số lượng văn bản trong phạm vi rà soát vượt quá giới hạn cho phép."
    ),
    "CONFLICT_SCAN_INSUFFICIENT_DOCUMENTS": (
        "Cần ít nhất 2 văn bản hợp lệ trong phạm vi của bạn để rà soát mâu thuẫn."
    ),
    "CONFLICT_SCAN_QUEUE_FULL": (
        "Hàng đợi rà soát mâu thuẫn đang đầy. Vui lòng thử lại sau."
    ),
    "AUTHORITY_RULE_EXISTS": "Mã quy tắc thứ bậc hiệu lực đã tồn tại.",
    "CONFLICT_SCAN_ACCESS_REVOKED": (
        "Tài khoản đã bị khóa hoặc mất quyền tra cứu trước khi lượt rà soát hoàn tất."
    ),
    "CONFLICT_SCAN_INTERRUPTED": (
        "Lượt rà soát bị gián đoạn do hệ thống khởi động lại hoặc quá thời gian giữ lượt."
    ),
    "CONFLICT_SCAN_EXPIRED": "Lượt rà soát mâu thuẫn đã hết hạn.",
    "CONFLICT_SCAN_CANCELLED": "Lượt rà soát mâu thuẫn đã bị hủy.",
    "CONFLICT_SCAN_TIMEOUT": "Lượt rà soát mâu thuẫn vượt quá thời gian xử lý cho phép.",
    "CONFLICT_SCAN_FAILED": "Không thể hoàn tất lượt rà soát mâu thuẫn do lỗi xử lý.",
    "CONFLICT_AMENDMENT_ACTION_REQUIRED": (
        "Cần chọn hành động sửa đổi (amendment_action) khi tạo đề xuất sửa đổi."
    ),
}


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", None)
    if isinstance(exc, RequestValidationError):
        status_code = 422
        code = "INVALID_REQUEST"
        message = "Dữ liệu gửi lên không hợp lệ."
    elif isinstance(detail, str) and detail:
        code = detail
        message = _MESSAGES.get(code, "Không thể hoàn tất yêu cầu.")
    else:
        code = "INTERNAL_ERROR"
        message = "Đã xảy ra lỗi. Thử lại hoặc liên hệ quản trị viên."
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "trace_id": f"trace_{uuid4().hex}",
            "details": getattr(exc, "details", None) or {},
        },
        headers={"Cache-Control": "no-store", **(getattr(exc, "headers", None) or {})},
    )


def api_error(
    status_code: int, code: str, *, headers: dict[str, str] | None = None,
    details: dict[str, object] | None = None,
) -> HTTPException:
    error = HTTPException(
        status_code=status_code, detail=code,
        headers={"Cache-Control": "no-store", **(headers or {})},
    )
    # Redacted, code-only context (e.g. which preflight checks failed).
    error.details = details or {}  # type: ignore[attr-defined]
    return error
