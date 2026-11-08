# Browser E2E — Search page (HƯ CẤU fixture)

Script `search.e2e.mjs` mở `frontend/dist` bằng Chrome headless qua CDP và dùng một
fixture API **cùng origin** (dữ liệu giả, nhãn HƯ CẤU). Không cần Playwright/Puppeteer,
không gọi mạng ngoài.

## Chạy

```powershell
cd frontend
# build trước (script phục vụ dist)
node E:\Programs\EvidenceRAG\runtimes\node\node.exe `
  E:\Programs\EvidenceRAG\tools\pnpm\node_modules\pnpm\bin\pnpm.cjs run build
node E:\Programs\EvidenceRAG\runtimes\node\node.exe `
  E:\Programs\EvidenceRAG\tools\pnpm\node_modules\pnpm\bin\pnpm.cjs run e2e:search
```

- Yêu cầu: đặt `$env:CHROME_PATH` trỏ tới Chrome đã cài (không hardcode trong mã);
  override bằng `CHROME_PATH`), Node >= 22 (global `fetch`/`WebSocket`).
- Script tự mở cổng 127.0.0.1:8731 (static) và 127.0.0.1:9333 (CDP), đóng khi xong.
- Exit code 0 = pass; 1 = có failure; output JSON gồm `steps` và `failures`.
- Đây là test **UI/wiring** với fixture HƯ CẤU, **không** phải backend thật + văn bản approved;
  không dùng kết quả này để tuyên bố chất lượng tìm kiếm.
- Không chạy trong CI mặc định vì runner cần Chrome ổn định; có thể thêm job riêng khi owner
  duyệt.
