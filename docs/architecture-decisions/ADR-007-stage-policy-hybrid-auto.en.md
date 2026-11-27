**Language / Ngôn ngữ:** [Tiếng Việt](ADR-007-stage-policy-hybrid-auto.md) · English

English counterpart of `docs/architecture-decisions/ADR-007-stage-policy-hybrid-auto.md`. The Vietnamese file is the original.

# ADR-007 — Per-stage model-call policy, Hybrid Auto, and the cost cap (G1.0)

- Date: 2026-11-07
- Status: Implemented
- Supersedes: the invariant “at most 2 LLM calls per turn” in the handoff record (B.3/C.9, WP 3.3), SRS §25 (`llm_attempt_budget=2`), and ADR-004 section 4 (number of attempts).
- Basis (căn cứ): the finalized design `docs/thiet-ke-tra-cuu-hieu-luc.md`, decisions D5 and D8; consistency points 2, 3, and 4.

## 1. Context

The number of model calls was fixed at 2, and `API` mode forced every route to use a profile in the `public` zone. The owner decided: Local first; escalate automatically to the API (Hybrid Auto) when the local result falls short or the user chooses deep analysis; do not escalate because evidence (căn cứ) is missing; comply with permissions and the cost cap; Local Only mode never calls the API.

## 2. Decision

1. **Per-stage policy** (`stage_policies`, migration `0010`): the maximum number of sends per request (1–10), output tokens, timeout (≤ 30 s, and not above `EVIDENCE_AI_TIMEOUT_SECONDS`), and concurrent requests, for each pair of (mode, stage). If the row is missing, use `LLM_ATTEMPT_BUDGET` (now 1–10, default 2). Every HTTP send, including an error, a timeout, and a fallback, still consumes one attempt. There is no autonomous loop.
2. **Stages in the Registry:** `answer`, `summarize`, `expand`, `relation`, `label`, `embedding`, `rerank`. When the ADR was written (2026-11-07) the application called only `answer` (update of 2026-11-09: G1–G4 are fully wired; see `ACTIVE_STAGES` in `model_registry/stages.py`); the other stages can be configured but are not yet used.
3. **The two modes keep their names:**
   - `LOCAL` = Local Only. A `public` profile is rejected when a route is saved and at runtime; a LOCAL route must not have an escalation profile; the runtime in this mode does not read an escalation profile.
   - `API` = Hybrid Auto. The primary route may be a local profile (checked against the local-endpoint rules); `stage_routes.escalation_profile_id` additionally points at one `public` profile, and only for a stage that has a check in code (`answer`, `summarize`).
4. **When to escalate:** (a) a local model has actually run and no result passes the application’s check (for `answer`: JSON of the right shape, and every id belongs to the evidence (căn cứ) set that was supplied), then call the escalation profile **once**; (b) the user turns on “Phân tích sâu” (Deep analysis) (`deep_analysis`), which calls the escalation profile first and uses local as the fallback. If there is no evidence, no model is called, so the system never escalates because evidence is missing, nothing was found, or effectivity (hiệu lực) is not yet verified. A local route that cannot be used (a configuration error, or a temporary skip) is not a reason to escalate.
5. **Conditions for leaving the machine** stay as in ADR-004: the domain is on the allowlist, HTTPS, the user has `remote_ai_allowed`, every source category allows external processing, and the administrative document (văn bản) is not `restricted`.
6. **Cost:** a profile has a price per million input and output tokens and a daily and monthly cap. Once the cap is reached, do not send to that profile; the result falls back to the no-model path (verbatim text) and reports `ai_limited`. If the server does not report a token count, estimate high (characters/3 for the input, the full output-token allowance) so the cap stops early rather than late.
7. **Log:** each send writes one `ai_usage_events` row (mode, stage, profile, person, outcome `ok/rejected/unusable/error/unreachable/cancelled`, whether it escalated, tokens, duration, estimated cost). The question, the answer, and the text of the administrative document are not stored.
8. **Transparency:** the response includes `external_ai_used` (evidence content was sent to an external API) and `ai_limited`; the interface shows “Đã dùng API ngoài cho lượt này.” (“An external API was used for this turn.”). The Admin Portal shows the escalation route, the limits currently in force, and daily and monthly usage.

## 3. Consequences

- Configuration that is already deployed still runs: with no policy row, the limit is still 2 attempts; an old API route that points straight at a `public` profile is still valid.
- Policy, routes, and the amount already spent are read from the database on every request, so a configuration change does not need a restart. The temporary skip state and the concurrency limit are still counted inside one process (as in ADR-006).
- The cost cap is checked before the send, so many concurrent requests can go slightly over the cap (by at most the number of sends already running).

## 4. Verification

`backend/tests/test_ai_policy.py` (Local Only does not call the API even when deep analysis (“Phân tích sâu”) is on; escalate once when local returns an id outside the set; keep a good local result; deep analysis calls the API first; reject when the user or the category does not allow it; do not escalate when local cannot run; the cost cap; the token and cost log contains no content; the policy replaces the 2 attempts; with no evidence (căn cứ), 0 calls) and `test_ai_registry_postgres.py::test_hybrid_auto_route_stage_policy_and_cost_cap` on real PostgreSQL.
