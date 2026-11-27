**Language / Ngôn ngữ:** [Tiếng Việt](ADR-002-model-capabilities.md) · English

English counterpart of `docs/architecture-decisions/ADR-002-model-capabilities.md`. The Vietnamese file is the original.

# ADR-002 — Capability-based Model Registry and a bounded runtime

**Status:** Updated and technically hardened (2026-10-26).

## Decision

- The Registry stores the adapter, endpoint, model ID/revision, capability, privacy zone, params (temperature, top_p, max_tokens, json_mode), secret reference, fallback, and health in PostgreSQL (`model_profiles`, `stage_routes`, `providers`).
- The execution runtime is `RegistryRuntime`:
  - It loads routes (`stage_routes`) and profiles (`model_profiles`) dynamically from the database for each operation.
  - It uses the standard `openai_compatible` adapter, which supports both Local AI (`ollama_local`, `vllm_local`, `llama_cpp_local`) and a remote OpenAI-compatible API.
  - It removes the static router `router.py` and abstract protocols that are unused in the code, to avoid dead code.
- Practical protection and handling:
  1. **Local AI support:** Accept the hostname `localhost` and local loopback addresses for Local AI endpoints.
  2. **Unwrap reasoning format (Unwrap Reasoning):** Automatically strip reasoning blocks `<think>...</think>` and markdown code fences ```` ```json ```` before parsing the canonical JSON `{"evidence_ids": [...]}`, compatible with modern reasoning models (Qwen 2.5, DeepSeek R1).
  3. **Secret-reference security:** `secret_ref` allows only the syntax `env:VAR_NAME` and strictly forbids sensitive system environment variables (`DATABASE_URL`, `PG*`, `POSTGRES*`, `*PASSWORD*`, `EVIDENCE_*` except `EVIDENCE_AI_*`).
  4. **Timeout and graceful degradation (Graceful Degradation):** The step that selects evidence (căn cứ) through AI is limited to 70% of the query timeout. If the model responds slowly or errors, the system records a redacted security error code in the log (redacted log), skips AI selection, and returns the full set of evidence whose origin has been verified, without breaking the query flow (preventing a 504 Gateway Timeout).
  5. **Prevent orphaned resources:** When an Admin updates a profile, the system updates the corresponding `providers` record directly instead of creating new rows indiscriminately.
- The router selects a profile by `(mode, stage)`; mode is `API` or `LOCAL`.
- `remote_allowed` is a complete AND condition: API mode + scope category + candidate document + user permission + provider approved + payload policy.
- Local Mode rejects a remote profile with `REMOTE_AI_DENIED` and does not fall back to the API.
- The total LLM budget per run is at most two requests that were sent, counting timeout/error/fallback. Fact extraction and analysis rules use deterministic Python code.
- The test endpoint (`/probe`) uses GET `/models` to cross-check the model ID; a secret is stored only as a reference, and the raw key is never sent to the frontend.
- The Admin Portal interface supports editing `temperature` and `max_tokens`, forcing the JSON type `json_mode`, checking the connection (`probe`), and a visual layout of 3 sub-tabs.

## Consequences

- Changing the model of a supported adapter is done only through configuration, without editing source.
- When there is no real model/key, the API returns real evidence/extractive with `answer_generated=false`; the adapter only selects evidence (căn cứ) and does not generate a new quote.
- The app does not hang or crash when a local/cloud model is delayed by the network or crashes.

## What has not yet been demonstrated

There is not yet a performance evaluation on specifically weak hardware (Raspberry Pi/CPU only) or on Local offline without a GPU.
