**Language / Ngôn ngữ:** [Tiếng Việt](ADR-004-hardening-memory-and-model-runtime.md) · English

English counterpart of `docs/architecture-decisions/ADR-004-hardening-memory-and-model-runtime.md`. The Vietnamese file is the original.

# ADR-004 — Comprehensive review, hardening of AI memory, and a safe model runtime

## Correction of 2026-10-27

The notes below describe the changes of the previous round. They do not prove that the application has stopped hanging, that dead code is gone, or that every feature is complete. Memory is currently temporary only; long-term storage has not been implemented. New tests and the limits on document-citation position, a real model, and desktop testing are recorded in the [review report](../evidence/2026-10-27-audit/REPORT.md).

**Decision date:** 2026-10-26  
**Status:** Accepted and implemented (Accepted)

---

## 1. Context

After the local system skeleton was implemented (FastAPI, React, Tauri 2, PostgreSQL 18.6), an in-depth source review found several latent risks to performance, security, and feature integrity:
1. **AI memory disconnected from the interface:** The backend already had a complete `EphemeralMemoryService` (managing the session, turn, memory items, and facts revision in RAM), but the `EvidenceChat` interface called the stateless lookup API (`/api/v1/query/evidence`). Facts were stored only temporarily in client-side React state, so server memory became an unused feature.
2. **Phantom Preferences feature:** The endpoint `PUT /api/v1/memory/preferences` allowed a preferred-category configuration to be saved, but the backend did not apply it when filtering evidence (căn cứ) on later lookup turns, and there was no `GET` endpoint to reload the preferences.
3. **Duplicate / phantom endpoints:** `POST /api/v1/query/answer` had handling code identical to `POST /api/v1/query/evidence` and did not generate an automatic answer at all; `POST /api/v1/analysis/situation` was a complete duplicate of `POST /api/v1/query/analyze`.
4. **Risk of the application hanging (Hang/Delay/504):** When a Local AI model or a Cloud API was configured, each model call had a timeout of 30 seconds with at most 2 attempts (60 seconds in total). Meanwhile, the timeout of the entire query was 45 seconds. If the model responded slowly or could not connect, the entire lookup turn failed with error code 504 Gateway Timeout even though the legal evidence had already been extracted successfully from the database.
5. **Administrative-document (văn bản) search latency (FTS Query Delay):** In `PostgresAuthorizedNodeSearch`, `to_tsvector` was called repeatedly 3 times in the `WHERE` and `ORDER BY` clauses for each data row, wasting CPU and increasing latency when the volume of administrative documents was large.
6. **Shortcomings in Model Registry and Local AI configuration:**
   - The Local AI connection gate rejected the hostname `localhost` because it allowed only literal IPs, which blocked common runtimes that run on the local machine (Ollama, vLLM, llama.cpp).
   - New-generation reasoning models (DeepSeek R1, Qwen 2.5) often return reasoning tags `<think>...</think>` or markdown code fences ```` ```json ````, which made the JSON parser fail and drop the result.
   - When a model profile was saved, the system always ran `INSERT` for a new `providers` record, producing unused orphan rows.
   - Generation parameters were missing (`params`: `temperature`, `max_tokens`, `json_mode`).
   - The configuration `secret_ref=env:...` had no mechanism to block sensitive system environment variables.
7. **Dead code and a phantom router:** The `ModelRouter` class (`router.py`) and the `StageRoute` structure were called only in old test files and did not participate in the actual runtime (`RegistryRuntime` loads configuration directly from the DB). Several protocols in `adapters/base.py` (`ChatAdapter`, `EmbeddingAdapter`, `RerankAdapter`) were unused.
8. **Identity-spoofing hole through CORS:** The headers `X-Principal-Id` and `X-Roles` were allowed by default in the CORS `allow_headers` list in every mode, with a latent risk that a client could spoof permissions.
9. **Silent SSE stream cutoff:** When the memory session expired while processing was underway, the SSE stream ended without emitting an error event, leaving the user stuck in the status `Đang tra cứu...` (`Đang tra cứu...`, "Searching...").

---

## 2. Technical decisions

### 2.1. Fully connect AI memory into the User Workspace
- Convert `EvidenceChat.tsx` to a working-session model (`AgentSession`) that uses `EphemeralMemoryService` through Server-Sent Events (SSE), with this flow:
  1. Automatically create a RAM session when the user looks up for the first time (`POST /api/v1/agent/sessions`).
  2. Send the lookup turn with an assigned idempotent code through `POST /api/v1/agent/sessions/{id}/turns`.
  3. Add the SSE event `analysis_ready`, emitted by the backend to the client, carrying claims, suggestions, missing_information, and coverage_checks.
  4. Support turn control: the **Dừng** button (`Dừng`, Stop) calls `POST .../turns/{id}/cancel` to cancel the process on the server; the **Thử lại** button (`Thử lại`, Retry) calls `POST .../turns/{id}/retry`.
  5. Build the “Bộ nhớ phiên” interface (`Bộ nhớ phiên`, "Session memory"): let the user view the list of memory items, delete a single item (`DELETE /api/v1/memory/{item_id}`), or press “Xóa dữ liệu tạm” (`Xóa dữ liệu tạm`, "Clear temporary data") to release RAM completely (`DELETE /api/v1/memory` and `DELETE /api/v1/agent/sessions/{id}`).
  6. When the user logs out or navigates away, the working session in RAM is reclaimed immediately (`deleteAgentSession`).

### 2.2. Activate the real Preferences feature
- Add the endpoint `GET /api/v1/memory/preferences`.
- In `create_turn`, the backend applies `_with_preferences`: when the user turns preferences on and looks up in `ALL_AUTHORIZED` mode, the system automatically assigns the saved `default_category_ids` to that turn's query scope.

### 2.3. Remove phantom endpoints and standardize messages
- Remove the routes `POST /api/v1/query/answer` and `POST /api/v1/analysis/situation` completely.
- Standardize interface messages: make clear that the AI's role is only a tool that helps select at most 3 evidence items (căn cứ) directly related to a source that has already been reviewed; displayed content is taken 100% verbatim from the original PDF administrative document (văn bản); there is no feature in which the AI writes a hypothetical answer on its own.
- When selecting related evidence for cross-check (`_unclaimed_for_suggestions`), remove evidence already displayed in claims so that surplus information is not repeated.

### 2.4. Prevent congestion and hangs through fail-safe AI selection
- Wrap the wait for the `ConfiguredSelection` class at 70% of the query timeout (`timeout_seconds = settings.query_timeout_seconds * 0.7`).
- Graceful degradation: if the model responds slowly or the network fails, the system catches `TimeoutError`, skips AI selection, and still returns the original evidence set whose source has been verified, so the user's lookup turn always finishes quickly and successfully.

### 2.5. Optimize the FTS search query
- In `PostgresAuthorizedNodeSearch`, apply the clause `CROSS JOIN LATERAL (SELECT to_tsvector(...) AS tsv) lex`. `to_tsvector` is computed only once for each candidate row and is reused for the search conditions and the `ts_rank_cd` ranking score.

### 2.6. Harden the Model Registry and the Local AI runtime
- Accept the hostname `localhost` alongside loopback IPs for Local AI connections.
- `_canonical_selection` automatically strips reasoning tags `<think>...</think>` and markdown code fences before decoding JSON.
- Protect sensitive environment variables: `_SECRET_DENIED` rejects the variables `DATABASE_URL`, `PG*`, `POSTGRES*`, `*PASSWORD*`, and `EVIDENCE_*` (except `EVIDENCE_AI_*`).
- Redacted error logs: record only the exception class name or the internal error code, and remove endpoint URL information and authentication tokens from the log entirely.
- Extend the `ModelProfileRequest` schema and update the Admin Portal form: add the generation-parameter group `params` (`temperature`, `max_tokens`, `json_mode`).
- When a model profile is saved again, the system checks and updates the existing `providers` record directly instead of creating a new one.

### 2.7. Clean up dead code
- Delete the file `backend/app/model_registry/router.py` and the `StageRoute` struct in `profiles.py`.
- Delete the unused protocols (`ChatAdapter`, `EmbeddingAdapter`, `RerankAdapter`) in `adapters/base.py`.
- Delete the constant function `new_facts_revision()` in `analyze.py`.
- Delete the attribute `artifact_relative_path` in `ModelProfile`.

### 2.8. CORS security and handling of an SSE stream cutoff
- The CORS `allow_headers` list adds `X-Principal-Id` and `X-Roles` only when `dev_allow_in_memory_store = True`. In a real environment these headers are forbidden, in order to remove the risk of identity spoofing.
- When a working session expires or is deleted partway through, the SSE stream emits an explicit error event `turn_error: SESSION_EXPIRED` (sequence 2) before closing the connection.

---

## 3. Consequences

- **Positive:**
  - The application responds quickly, and the app no longer hangs (504) because a model is delayed by the network.
  - Conversation memory actually works, so the user can look up continuously across many question turns.
  - An administrator can configure Local AI / Cloud API model parameters flexibly and safely.
  - The codebase is clean, with no phantom features or dead code that would cause confusion.
  - All 19 frontend vitest tests and the TypeScript type check pass in full.
- **Note:**
  - `python scripts/export_openapi.py` needs to be run again once the Python environment is complete, in order to update the specification `docs/openapi.json`.
  - For a very large volume of administrative documents (văn bản) in the future, a GIN index on a precomputed column expression needs to be added in order to optimize FTS speed further.
