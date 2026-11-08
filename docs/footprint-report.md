# Footprint report

Chưa có bản đo trên máy đích. Không công bố ước lượng trước khi đo.

Khi có manifest cài được duyệt, báo riêng:

1. Core Pack: frontend, backend, parser, client, dependency runtime;
2. Model Pack: từng model id, revision, SHA-256, license, RAM/disk;
3. PostgreSQL và pgvector;
4. Data Pack: PDF, source pages, vectors, logs và backup.

`tools/measure-footprint` phải chạy clean install dưới root cấu hình và trả inventory real path. Chưa được dùng kích thước source tree làm bằng chứng gói cài đặt.
