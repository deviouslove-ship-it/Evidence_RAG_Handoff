# PDF anchor coordinate contract

Anchor hợp lệ gồm:

- document version ID và source hash;
- page number;
- original character offset/length;
- character boxes/quads;
- page width, height, rotation;
- MediaBox và CropBox.

Hiển thị phải dùng cùng transform của PDF viewer. Với nhiều dòng, dùng nhiều quad, không dùng một rectangle bao quá rộng. Với rotation/CropBox không chắc chắn, fallback về trang + quote và ghi rõ không tô chính xác.

Chưa có fixture PDF thật trong repo để chứng minh độ chính xác anchor; gate WP 0.3/1.5 vẫn mở.
