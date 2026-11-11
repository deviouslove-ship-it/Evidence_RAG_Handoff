# PDF anchor coordinate contract

Anchor hợp lệ gồm:

- document version ID và source hash;
- page number;
- original character offset/length;
- character boxes/quads;
- page width, height, rotation;
- MediaBox và CropBox.

Hiển thị phải dùng cùng transform của PDF viewer. Với nhiều dòng, dùng nhiều quad, không dùng một rectangle bao quá rộng. Với rotation/CropBox không chắc chắn, fallback về trang + quote và ghi rõ không tô chính xác.

> **[Không triển khai tô sáng tọa độ bbox trên PDF]** Trình xem hiện mở đúng trang PDF và hiển thị trích đoạn nguyên văn (`quote_exact`); việc vẽ lớp phủ highlight tọa độ từng từ (bbox/quads) trên trang PDF và bộ fixture chứng minh độ chính xác anchor (cổng WP 0.3/1.5) được chốt **không triển khai**.

Chưa có fixture PDF thật trong repo để chứng minh độ chính xác anchor; gate WP 0.3/1.5 không triển khai.
