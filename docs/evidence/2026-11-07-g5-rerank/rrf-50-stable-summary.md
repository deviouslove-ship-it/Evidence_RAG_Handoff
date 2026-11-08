# RRF thuần, 50 câu hỏi

Số câu: 50; số câu bị xếp hạng lại: 0 (mong đợi 0). Thời gian trả lời (giây): trung vị 2.433, trung bình 2.687, lớn nhất 11.392.

| Bộ | Câu | Cặp | R@10 | R@20 | R@50 | R@toàn bộ | MRR@10 | NDCG@10 | P@10 |
|---|---|---|---|---|---|---|---|---|---|
| 24 câu gốc | 24 | 42 | 0.762 | 0.809 | 0.905 | 0.929 | 0.659 | 0.536 | 0.404 |
| 26 câu bổ sung | 26 | 32 | 1.000 | 1.000 | 1.000 | 1.000 | 0.891 | 0.638 | 0.285 |
| Cả 50 câu | 50 | 74 | 0.865 | 0.892 | 0.946 | 0.960 | 0.779 | 0.589 | 0.342 |

Theo chủ đề:

| Chủ đề | Bộ | Câu | R@10 | R@20 | R@50 | R@toàn bộ | MRR@10 | NDCG@10 |
|---|---|---|---|---|---|---|---|---|
| van_tay_ho_chieu | v1 | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.647 |
| to_bao_ve_antt | v1 | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.389 | 0.499 |
| dang_ky_xe_truc_tuyen | v1 | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.667 | 0.482 |
| khieu_nai_cong_nhan_cong_an | v1 | 3 | 0.667 | 0.667 | 1.000 | 1.000 | 0.556 | 0.504 |
| cu_tru_truc_tuyen_ban_quet | v1 | 3 | 0.778 | 0.889 | 1.000 | 1.000 | 0.833 | 0.661 |
| hieu_luc_ho_chieu_pho_thong | v1 | 3 | 0.833 | 0.833 | 0.833 | 0.833 | 0.778 | 0.802 |
| noi_quy_giam_giu | v1 | 3 | 0.667 | 0.667 | 0.667 | 0.667 | 0.381 | 0.387 |
| kiem_tra_giay_to_dinh_danh | v1 | 3 | 0.500 | 0.667 | 0.833 | 1.000 | 0.667 | 0.307 |
| to_cao_cand | v2 | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.538 |
| the_cccd_thoi_han_xu_ly | v2 | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.778 | 0.698 |
| tai_nan_giao_thong_thoi_han | v2 | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.833 | 0.696 |
| am_hieu_coi_dieu_khien_giao_thong | v2 | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.690 |
| hieu_lenh_dung_phuong_tien | v2 | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.876 |
| ung_xu_dien_thoai_mang | v2 | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.715 |
| cong_khai_tuyen_sinh | v2 | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.611 | 0.168 |
| niem_phong_mau_nuoc_thai | v2 | 3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.859 |
| xu_ly_vphc_duong_sat | v2 | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 0.750 | 0.430 |

Căn cứ không có trong 10 kết quả đầu:

| Bộ | Câu hỏi | Căn cứ | Nhóm ứng viên | Hạng tốt nhất | Kênh |
|---|---|---|---|---|---|
| v1 | khiếu nại quyết định kỷ luật công nhân công an | 23/2022/TT-BCA Điều 6 | 70 | 45 | exact+concept |
| v1 | thẩm quyền giải quyết khiếu nại lần đầu lần hai trong Công an nhân dân | 23/2022/TT-BCA Điều 6 | 233 | 26 | exact+concept |
| v1 | đăng ký cư trú qua VNeID giấy tờ không ký số | 55/2021/TT-BCA Điều 3 | 130 | 12 | semantic+concept |
| v1 | tiếp nhận hồ sơ đăng ký cư trú và thông báo kết quả | 43/VBHN-BCA Điều 3 | 280 | 36 | semantic+concept |
| v1 | Thông tư 29/2016/TT-BCA còn hiệu lực không | 110/2021/TT-BCA Điều 2 | 157 | - | - |
| v1 | nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam | 58/2026/TT-BCA Điều 11 | 148 | - | - |
| v1 | đồ vật cấm đưa vào buồng tạm giữ tạm giam | 96/2026/TT-BCA Điều 3 | 352 | - | - |
| v1 | cảnh sát giao thông kiểm tra giấy phép lái xe trên VNeID | 32/2023/TT-BCA Điều 12 | 732 | 15 | semantic+concept |
| v1 | cảnh sát giao thông kiểm tra giấy phép lái xe trên VNeID | 28/2024/TT-BCA Điều 1 | 732 | 33 | semantic+concept |
| v1 | tuần tra kiểm soát kiểm tra giấy tờ đã tích hợp căn cước điện tử | 32/2023/TT-BCA Điều 12 | 949 | 151 | concept |

RAM (MB): api đỉnh 96.0 / trung vị 92.1; ollama đỉnh 3544.4 / trung vị 3253.0
