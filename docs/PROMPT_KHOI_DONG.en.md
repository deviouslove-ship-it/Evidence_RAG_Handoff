**Language / Ngôn ngữ:** [Tiếng Việt](PROMPT_KHOI_DONG.md) · English

English counterpart of `docs/PROMPT_KHOI_DONG.md`. The Vietnamese file is the original.

# Startup prompt — synchronized with dossier 1.1 / SRS v1.3

> **[Not implemented — see ADR-010]** Every part of this document about the Gold question set, the trap set, calibration, and held-out must not be implemented, per [ADR-010](architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md). The rest stands unchanged.

This document is used to assign the implementation work that follows. Updating the dossier does not mean the WPs have been carried out.

## 1. Shared prompt

You are a coding agent implementing the Vietnamese Evidence RAG Agent on Windows. Read `docs/SRS_v1.3.md`, `docs/HOSO_BAN_GIAO.md`, and `docs/architecture-decisions/ADR-000.md`. If you are in the handoff package, use the mapping in the README. SRS v1.3 and ADR-000 already include WP 0.0 for integration and reconciliation. Do not rewrite the specification or re-decide an owner decision.

Implement the WPs in section F in order, including memory, anti-hallucination, analysis/suggestions, and the USER desktop. The USER opens the shortcut, logs in inside the Windows app, uses the round Orb at the right corner of the desktop, clicks to open or collapse the chat, and opens a PDF or the workspace in the same session. Drag/resize/tray/stop/retry/logout/exit follow S14. The Admin Portal is separate from the User Portal and shares auth, the backend, PostgreSQL, the document store, and RAG. Do not create a chatbot or a database on each USER machine. Keep the theme/tokens and readable text. The Orb has no square background and no extra shadow. Login and the panel use opaque backgrounds. The drag region does not cover text. Do not show a console.

Configure the LLM as API or Local through the Registry/Router, per stage: adapter/provider, approved endpoint/runtime, model ID/artifact, params, revision, secret reference, and fallback. Do not hardcode permissions, provider, model, endpoint, key, host, port, or path. Use configuration, the manifest, and platform APIs. API Mode has the Internet and permitted egress. Local Mode cuts off the Internet, uses only an approved internal runtime/endpoint, and does not switch to the API by itself. The POC model is not a required model. The owner enters the key later. If the model or key is not yet available, finish the features and the contract tests, return real evidence/extractive output, and do not simulate AI or declare the provider gate met.

Do not hardcode PATH or the LLM. Every project tool and runtime installed to build, install, and operate the app must sit under the root `E:\Programs` decided by the owner. The root is only the deployment-profile value `installation.programs_root` / `EVIDENCE_PROGRAMS_ROOT`. Do not embed it in code or scripts. Resolve the executable, model, artifact, and tool cache from the manifest under the root. Do not use a PATH/global/AppData/Program Files fallback. If the root or a dependency is missing, report an error. Do not switch drives on your own. Each machine installs only the components for its role. Business data and backups have their own configured paths. Do not move them on your own. Comply with B.8 and SRS §25.9.

Follow B.3/B.7/B.8 and SRS §25: the CURATOR drafts, and the REVIEWER approves. The analysis/retrieval cache stays OFF until the fingerprint and the tests are sufficient. Incognito is RAM only; store only when retention and opt-in are in place. Delete derivatives/cache/jobs. Restore applies the deletion ledger. Gold [Not implemented — see ADR-010] is 150–200 cases approved by the person who holds the business domain, split by scenario group, with regression kept separate from held-out. llm_attempt_budget=2 includes timeout, retry, and fallback. The P0 summary is produced by code. Scope is SELECTED or ALL_AUTHORIZED. The server always checks the ACL. SSE uses query_id/run_id/revisions/sequence. An explicit retry does not mix turns.

The AI builds the ERD, migrations, and test DB itself and does as much of the technically verifiable work as possible. A person is needed only to decide business-domain principles, access rights, security, and the correctness of evidence (căn cứ). Do not self-certify Gold [Not implemented — see ADR-010]. Do not fabricate a legal administrative document (văn bản pháp lý). Do not add a forbidden dependency. Do not use old results as current evidence. If a key, model, reviewer, or device is missing, report exactly which gate is still missing and continue the independent work. At the end of each WP, file the F.10 report, with measurements, the environment, and a CHƯA XONG (NOT DONE) section.

## 2. Per-stream prompts (split across multiple AIs only when the owner allows)

Every stream reads the shared section, B.7/B.8, E, F, and SRS §25. The backend publishes the OpenAPI spec and the permission matrix at the start of Sprint 1. The frontend uses mocks of the same schema. Do not create a different chatbot or workflow. Each WP has one lead. The other streams contribute according to the interface or component. Do not leave acceptance uncovered.

### Backend and data stream (A, B, D, E, G)

Leads WP 0.0–0.2, 0.5, 0.7, 1.1–1.7, 1.10, 2.6–2.7, 3.1–3.4, 3.7, 4.1–4.4, 4.8.

Responsible for the ERD/ACL, curator draft vs reviewer approve, node effectivity (hiệu lực), OpenAPI, session/memory/incognito/delete/restore, provider/route/secret, and the LLM budget. WP 0.5 works with frontend on the POC shell. For WP 4.8 the backend leads the red-team and requires retrieval and frontend to supply leak/cache/SSE/UI tests. The report includes evidence and the parts not yet checked. There is no tool that lets the LLM write business data. Operational session/audit is carried out by a service that checks permissions.

### Retrieval and evaluation stream (C)

Leads WP 0.3, 0.4, 0.6, 1.9, 2.1–2.5, 2.8, 2.10–2.15, 3.8, 3.10–3.13, 4.5–4.6, 4.9.

The POC model is a check of capability, runtime, and format. It does not lock in a fixed model. Gold [Not implemented — see ADR-010] v0 is 150–200 real-PDF cases approved by a person, split by `scenario_group_id`. Lock the split, corpus, protocol, and candidate before the final evaluation round. Use calibration and regression during development. Do not tune on held-out or trap hold-out and then keep reporting the result as independent. Leads WP 4.9 for the P1 items the owner selects, coordinating with backend and frontend. Record explicitly the list of items not selected. Contributes to WP 4.8. Do not claim the red-team has passed when the tests do not yet exist.

### Frontend and USER desktop stream (F)

Leads WP 1.8, 2.9, 3.5, 3.6, 3.9, 3.14, 4.7.

Contribute UI to the other WPs according to the lead's assignment.

Implement separate User and Admin layouts and routes, and the USER desktop on Tauri 2 per C.12/S14, using the same backend and RAG. The Orb is a round toggle. Login and the panel use opaque backgrounds. There is no extra shadow, no leftover square background, and no console. Drag and resize do not cover the title or the buttons. Tray, logout, exit, stop, retry, the viewer, and the workspace keep the session. The scope includes “Tất cả danh mục được phép” (All authorized categories). The USER has no administration function and does not enter a key. The admin form for API/Local configuration does not hardcode a model. Dock beside the panel or the viewer only when the work area is large enough. Check 320/768/1024/1280px, DPI 100/125/150/200%, multiple monitors, zoom, keyboard, contrast, and reduced-motion. WP 4.7 must include a real native check. Tests and builds do not replace Windows acceptance.

## 3. Completion boundary

- Profile B accepts only the offline core, within the published limits. It does not replace the gate for AI configured with a real API or a real local model.
- Do not use API keys, test accounts, machine paths, or secret data from the project history.
- The document set is a self-contained input. Code from the old project is not required in order to understand the contract.
- Every WP has a lead and an F.10 report. Do not accept the whole as complete merely because one unit-test suite passed or a build is green.
