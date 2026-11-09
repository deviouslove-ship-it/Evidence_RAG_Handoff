# Requirements: Model Registry (AI Local / AI API)

> Spec reconstructed from the implemented code on 2026-11-09. This is not a historical Kiro-generated spec. Evidence is cited by repository path. Decisions: ADR-002, ADR-004, ADR-007.

## Introduction

Every use of a model is a named stage. Administrators register Local or API model profiles, test them, and assign them per stage and per operating mode, under egress and cost policy.

## Requirements

### Requirement 1: Profiles

#### Acceptance Criteria

1. WHEN SYS_ADMIN adds a profile THE SYSTEM SHALL store adapter, endpoint, model ID, capabilities, version, privacy zone, approval and health (`model_registry/profiles.py`, `POST /api/v1/admin/model-registry`).
2. THE SYSTEM SHALL offer "Add AI Local" (Ollama, vLLM, llama.cpp) and "Add AI API" (OpenAI, Gemini, custom OpenAI-compatible) forms (`frontend/src/components/ai/ProfileEditor.tsx`).
3. WHEN an API key is saved THE SYSTEM SHALL store it encrypted with Windows DPAPI bound to the server account and SHALL NOT return it through any API (`model_registry/secret_store.py`).

### Requirement 2: Test before use

#### Acceptance Criteria

1. WHEN the administrator tests a draft or saved profile THE SYSTEM SHALL check policy, key, connectivity, model presence and a model response, and report each step (`model_registry/diagnostics.py`, `POST /model-registry/test`, `/{id}/test`, `/{id}/probe`).
2. IF a check fails THEN THE SYSTEM SHALL allow saving only when the administrator explicitly chooses "save anyway (not usable)", and SHALL NOT mark the profile ready.

### Requirement 3: Stage assignment

#### Acceptance Criteria

1. THE SYSTEM SHALL support the stages `answer`, `summarize`, `expand`, `relation`, `label`, `embedding`, `rerank` (`model_registry/stages.py`).
2. WHEN the administrator assigns a profile THE SYSTEM SHALL test and apply it per stage and per mode (`POST /model-registry/routes`), with optional fallback and escalation profiles.
3. WHEN a model is unreachable THE SYSTEM SHALL skip it for a cool-down period and degrade to returning the original evidence instead of hanging a chat turn.
4. THE SYSTEM SHALL keep changing the "AI interpretation" model separate from changing the embedding model: only the latter needs an index rebuild.

### Requirement 4: Egress policy

#### Acceptance Criteria

1. IF the mode is `LOCAL` THEN THE SYSTEM SHALL reject `public` profiles and SHALL NOT call any external API (`REMOTE_AI_DENIED`).
2. WHEN the mode is `API` THE SYSTEM SHALL send content outside only if the endpoint domain is allow-listed, the transport is HTTPS, the user has `remote_ai_allowed`, every source category allows remote processing and the document is not `restricted` (`AI_EGRESS_DENIED` otherwise).
3. THE SYSTEM SHALL restrict `embedding` and `rerank` to local profiles in both modes.

### Requirement 5: Hybrid Auto policy and cost caps

#### Acceptance Criteria

1. THE SYSTEM SHALL read per-(mode, stage) limits from `stage_policies`: attempts 1 to 10, output tokens up to 16,384, timeout up to 30 s, concurrency 1 to 64 (`stages.py::StagePolicy`).
2. WHEN a local result for `answer` or `summarize` fails the code checks, or the user selects deep analysis, THE SYSTEM SHALL escalate once to the configured API profile in API mode only.
3. IF no evidence exists THEN THE SYSTEM SHALL NOT call any model.
4. WHEN a daily or monthly cost cap is reached THE SYSTEM SHALL stop sending to that profile and degrade to the no-model path, reporting `ai_limited`.
5. THE SYSTEM SHALL log each call in `ai_usage_events` without question, answer or document text, and SHALL report `external_ai_used`.

### Requirement 6: Auditability

#### Acceptance Criteria

1. WHEN profiles, routes or policies change THE SYSTEM SHALL append audit events.
