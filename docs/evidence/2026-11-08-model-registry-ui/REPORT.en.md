**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-11-08-model-registry-ui/REPORT.md`. The Vietnamese file is the original.

# Model Registry UI redesign (2026-11-08)

## Result

The section "Mô hình AI & Kiểm toán" (AI models & audit) has four tabs: **1. Mô hình AI** (1.
AI models), **2. Phân công AI** (2. AI assignment), **Embedding** (unchanged), and **3. Nhật ký
Kiểm toán** (3. Audit log).

| Requirement | How it was done |
|---|---|
| Two separate forms | **AI Local**: Tên hồ sơ (Profile name), Runtime (Ollama/vLLM/llama.cpp), Địa chỉ máy chủ (Server address) (filled in from the runtime), Model ID. **AI API**: Tên hồ sơ (Profile name), Nhà cung cấp (Provider) (OpenAI/Gemini/Tùy chỉnh (Custom)), Base URL (filled in, and editable), Model ID, API Key (a password field). |
| Hide the default parameters | Adapter, temperature, tokens, reasoning level, JSON mode, data region, and version are inferred in `aiConfig.ts`; they can be edited under "Nâng cao" (Advanced). Editing a profile that has already been saved sends back exactly the values that were saved, and does not recompute them. |
| AI assignment on its own | One row per function: the primary model, and "Nâng cao" (Advanced) (fallback, API upgrade, call limit). The embedding row is read-only and leads to the Embedding tab. |
| Check before saving or activating | "Kiểm tra kết nối" (Check connection) (it does not save) and "Kiểm tra & Lưu" (Check & Save); on Phân công AI (AI assignment) it is "Kiểm tra & Áp dụng" (Check & Apply). If the check fails, saving or applying happens only when "Vẫn lưu/áp dụng (chưa dùng được)" (Save or apply anyway (not usable yet)) is chosen. |
| Backward compatible | Old profiles, routes, and `/probe` are unchanged; columns or tables added: none. |

## Backend changes (required for the feature to actually run)

- **API-key store** `model_registry/secret_store.py`: previously the backend accepted only
  `env:NAME`, so the API Key field had nowhere to store a value. An entered key is encrypted
  with Windows DPAPI, written once into `EVIDENCE_SECRET_STORE_DIR` (`secret:<tên>`), is not
  returned through the API, and does not go into the DB or the log.
- **A profile with several functions**: one profile can hold several text-generation functions;
  `embedding` always stands on its own. An old single-function profile is unchanged.
- **Diagnostics** `model_registry/diagnostics.py`: configuration → mode → key → connection →
  the model is in the list → a trial call (JSON or embedding). Separate error codes, and
  messages in Vietnamese. A Gemini `models/<id>` is accepted; `/models` returning 404 or 405 is
  only a warning.
- New endpoints `POST /api/v1/admin/model-registry/test` and
  `POST /api/v1/admin/model-registry/{profile_id}/test`; audit `admin.test_model_draft` /
  `admin.test_model`. OpenAPI was exported again.
- The launchers set `EVIDENCE_SECRET_STORE_DIR` (`ung-dung-test.ps1`,
  `deploy/portable/evidence.ps1`).

## Evidence

- `scripts\verify.ps1`: **12/12** passed. Backend **288 passed** (previously 257, with 31
  added). Frontend **86 passed** (previously 60, with 26 added); lint, tsc, and the build are
  clean.
- New tests: `test_model_diagnostics.py` (24, mock transport), `test_model_registry_api.py`
  (7, real PostgreSQL, checking that the key does not leak into the DB, the audit, or the
  response), `aiConfig.test.ts`, `ModelProfilesPanel.test.tsx`, `AssignmentsPanel.test.tsx`,
  and `AdminPortal.test.tsx`.
- Real HTTP against the application that was running (port 8000, local Ollama):
  - The old registry is intact: 6 `local-*` profiles (qwen3:1.7b, qwen3-embedding:0.6b), all
    of them `ready`, and 12 routes unchanged; `secret_store.available = true`.
  - A qwen3:1.7b draft: passed (connection 78 ms, trial call 1.4 s, and it returns JSON). An
    embedding draft: passed, 1024 dimensions.
  - A model that does not exist: `MODEL_NOT_FOUND`. A wrong port: `CONNECTION_FAILED`. An
    OpenAI draft while the server is in LOCAL mode: `AI_EGRESS_DENIED`.
  - Saving a multi-function profile (answer, summarize, label) together with an entered key:
    it saved, and the check of the saved profile records `ready`; the key file is 253 bytes,
    starts with `EVSEC1`, and **does not contain the key in the clear**; the registry does not
    expose the key.
- Chrome headless at 1366 px (`ai-1…4-*.png`, `ui-report-1366.json`): no horizontal overflow;
  the Local form shows only 4 fields; the API form has a password field and an egress error
  message that is easy to understand; Phân công AI (AI assignment) has every function.
- Q&A and Diễn giải AI (AI interpretation) were run again through `ai_probe.py` after a
  restart: they answer normally (chat 3.1 s, interpretation 14.6 s). The RRF configuration,
  rerank off, and the semantic threshold of 0.8 were left untouched. Administrative documents
  (văn bản) were not imported again, and the 7,230 vectors were not rebuilt.
- **The trial data has been cleaned up**: the profile `zz-check-local`, created in order to
  check a real key, was deleted from `model_profiles` (no route referenced it), together with
  its key file. The audit log is unchanged (the hash chain was not altered).

## Tradeoffs and limits

- **Provider self-approval**: the "phê duyệt" (approval) field was removed; saving from the
  form sets `provider_approved = true`. The API form states clearly that saving means allowing
  data that has already been permitted to be sent; the actual sending is still blocked by the
  server’s egress policy, by the catalog, and by the user’s permissions.
- An entered key travels over HTTP to the server (the portable build runs HTTP on the LAN).
  DPAPI is bound to the Windows account that runs the server; changing that account means the
  key has to be entered again.
- There is no API yet for deleting a profile. Saving a public profile does not check egress at
  save time (as before); the draft check reports `AI_EGRESS_DENIED` before saving.
- A real call to OpenAI or Gemini has not been tested (there is no key); the API path was
  checked with a mock transport and on the real Ollama path.
- It has not been tested in Tauri; it was checked only with Chrome headless and vitest.
- In the dev DB, the function "Hỏi đáp: chọn căn cứ" (Q&A: select evidence (căn cứ))
  (`answer`) does not have a route yet: this state existed beforehand, and the UI shows
  "Chưa phân công" (Not assigned).
- The Embedding tab is unchanged.
