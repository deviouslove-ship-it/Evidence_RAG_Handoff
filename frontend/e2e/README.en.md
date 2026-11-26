**Language / Ngôn ngữ:** [Tiếng Việt](README.md) · English

English counterpart of `frontend/e2e/README.md`. The Vietnamese file is the original.

# Browser E2E — Search page (FICTIONAL (HƯ CẤU) fixture)

The script `search.e2e.mjs` opens `frontend/dist` with headless Chrome over CDP and uses a **same-origin** API fixture (fake data, labeled FICTIONAL (HƯ CẤU)). Playwright or Puppeteer is not required. It does not call an external network.

## Run

```powershell
cd frontend
# build trước (script phục vụ dist)
node E:\Programs\EvidenceRAG\runtimes\node\node.exe `
  E:\Programs\EvidenceRAG\tools\pnpm\node_modules\pnpm\bin\pnpm.cjs run build
node E:\Programs\EvidenceRAG\runtimes\node\node.exe `
  E:\Programs\EvidenceRAG\tools\pnpm\node_modules\pnpm\bin\pnpm.cjs run e2e:search
```

- Requirement: set `$env:CHROME_PATH` to the installed Chrome (do not hardcode it in the code); override with `CHROME_PATH`), Node >= 22 (global `fetch`/`WebSocket`).
- The script opens ports 127.0.0.1:8731 (static) and 127.0.0.1:9333 (CDP) by itself, and closes them when it finishes.
- Exit code 0 = pass; 1 = there is a failure. The JSON output includes `steps` and `failures`.
- This is a **UI/wiring** test with a FICTIONAL (HƯ CẤU) fixture. It is **not** the real backend plus approved administrative documents (văn bản). Do not use this result to claim search quality.
- It does not run in the default CI, because the runner needs a stable Chrome. A separate job can be added when the owner approves.
