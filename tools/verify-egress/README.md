# verify-egress

Tool kiểm tra egress chưa được đóng gói trong round hiện tại. Cần chạy trên Windows đích sau khi áp dụng firewall allowlist.

- Phải thử cả DNS và HTTP/HTTPS tới Internet.
- Chỉ loopback/LAN được duyệt mới được phép.
- Không tự nới firewall hoặc chuyển route.
- Output phải ghi thời điểm, profile, policy revision và kết quả từng probe.

Gate Local Mode chỉ đạt khi có log probe thật trên máy đích, không chỉ unit test.
