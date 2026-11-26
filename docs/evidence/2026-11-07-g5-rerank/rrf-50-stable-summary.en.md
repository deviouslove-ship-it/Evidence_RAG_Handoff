**Language / Ngôn ngữ:** [Tiếng Việt](rrf-50-stable-summary.md) · English

English counterpart of `docs/evidence/2026-11-07-g5-rerank/rrf-50-stable-summary.md`. The Vietnamese file is the original.

# Pure RRF, 50 questions

Questions: 50; questions that were reranked: 0 (expected 0). Response time (seconds): median 2.433, mean 2.687, maximum 11.392.

| Set | Questions | Pairs | R@10 | R@20 | R@50 | R@entire pool | MRR@10 | NDCG@10 | P@10 |
|---|---|---|---|---|---|---|---|---|---|
| Original 24 questions | 24 | 42 | 0.762 | 0.809 | 0.905 | 0.929 | 0.659 | 0.536 | 0.404 |
| 26 added questions | 26 | 32 | 1.000 | 1.000 | 1.000 | 1.000 | 0.891 | 0.638 | 0.285 |
| All 50 questions | 50 | 74 | 0.865 | 0.892 | 0.946 | 0.960 | 0.779 | 0.589 | 0.342 |

By topic:

| Topic | Set | Questions | R@10 | R@20 | R@50 | R@entire pool | MRR@10 | NDCG@10 |
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

Evidence (căn cứ) not in the top 10 results:

| Set | Question | Evidence (căn cứ) | Candidate pool | Best rank | Channel |
|---|---|---|---|---|---|
| v1 | complaint against a disciplinary decision concerning a public-security worker (khiếu nại quyết định kỷ luật công nhân công an) | 23/2022/TT-BCA Article (Điều) 6 | 70 | 45 | exact+concept |
| v1 | authority to settle a first-instance and second-instance complaint in the People's Public Security (thẩm quyền giải quyết khiếu nại lần đầu lần hai trong Công an nhân dân) | 23/2022/TT-BCA Article (Điều) 6 | 233 | 26 | exact+concept |
| v1 | residence registration via VNeID with documents that are not digitally signed (đăng ký cư trú qua VNeID giấy tờ không ký số) | 55/2021/TT-BCA Article (Điều) 3 | 130 | 12 | semantic+concept |
| v1 | receiving a residence-registration dossier and notifying the result (tiếp nhận hồ sơ đăng ký cư trú và thông báo kết quả) | 43/VBHN-BCA Article (Điều) 3 | 280 | 36 | semantic+concept |
| v1 | Does Circular (Thông tư) 29/2016/TT-BCA still have effectivity (hiệu lực) (Thông tư 29/2016/TT-BCA còn hiệu lực không) | 110/2021/TT-BCA Article (Điều) 2 | 157 | - | - |
| v1 | rules of inmate detention facilities and rules of temporary detention camps (nội quy cơ sở giam giữ phạm nhân và nội quy trại tạm giam) | 58/2026/TT-BCA Article (Điều) 11 | 148 | - | - |
| v1 | items prohibited from being brought into temporary holding and temporary detention cells (đồ vật cấm đưa vào buồng tạm giữ tạm giam) | 96/2026/TT-BCA Article (Điều) 3 | 352 | - | - |
| v1 | traffic police checking a driving licence on VNeID (cảnh sát giao thông kiểm tra giấy phép lái xe trên VNeID) | 32/2023/TT-BCA Article (Điều) 12 | 732 | 15 | semantic+concept |
| v1 | traffic police checking a driving licence on VNeID (cảnh sát giao thông kiểm tra giấy phép lái xe trên VNeID) | 28/2024/TT-BCA Article (Điều) 1 | 732 | 33 | semantic+concept |
| v1 | patrol and control checking documents already integrated with the electronic citizen identity (tuần tra kiểm soát kiểm tra giấy tờ đã tích hợp căn cước điện tử) | 32/2023/TT-BCA Article (Điều) 12 | 949 | 151 | concept |

RAM (MB): api peak 96.0 / median 92.1; ollama peak 3544.4 / median 3253.0
