**Language / Ngôn ngữ:** [Tiếng Việt](00_README.md) · English

English counterpart of `00_README.md`. The Vietnamese file is the original.

# Handoff dossier — Vietnamese Evidence RAG Agent

The original dossier was prepared on 2026-10-21 · Dossier 1.1 · SRS v1.3. The handoff documents have been integrated into `docs/` (the single copy; there is no longer a copy at the repository root). Current implementation status is recorded in `docs/implementation-status.md`. How to run the system, and the repository structure, are in `README.md`.

## Reading order and the current version

1. `docs/HOSO_BAN_GIAO.md` — the main dossier, parts A–G. B.7 settles the approach for the 8 feedback items. C.12 and D.5 S14 describe the USER desktop.
2. `docs/SRS_v1.3.md` — the current technical specification. §25 synchronizes the contract for the 8 feedback items, for API/Local LLM, and for the desktop. §26 is the Search v1 contract (owner update of 2026-11-05 in §26.8).
3. `docs/architecture-decisions/ADR-000.md` — decisions, technical defaults, and acceptance boundaries. ADR-001…009 record the implementation decisions made after that.
4. `docs/PROMPT_KHOI_DONG.md` — the shared prompt and the assignment of all 56 WPs.
5. `docs/KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md` — the Search v1 plan locked by the owner.
6. `docs/TAI_LIEU_MO_TA_HE_THONG.md` and `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md` — the system description and the Admin operating guide, including Document management (Quản lý văn bản).

`docs/history/SRS_v1.2.1.md` is kept byte-for-byte as the historical copy. Older decisions in that file are not current requirements. Do not use it to re-select mode, OS, Gold, or approval authority.

Priority: new direction from the owner → B.4/B.7/B.8 → the main dossier → SRS v1.3. ADRs record decisions. They do not create a competing source of specification.

## Product intent checked against history

- The USER opens the Windows app and logs in inside the app; then uses the round Orb at the right corner of the desktop, clicks to open or collapse the chat, opens a PDF or the workspace in the same session, and has stop/retry/tray/logout/exit.
- A separate Admin Portal covers documents, categories (danh mục), ingestion, accounts/permissions, AI Configuration, monitoring/audit, and evaluation. The USER sees only the use-functions allowed by their permissions.
- Desktop, web, and admin share authentication, the backend, PostgreSQL, the document store, and RAG. There is no chatbot or database of its own on each USER machine.
- The LLM is configured as API or Local through the Registry/Router. Do not hardcode the provider, model, endpoint, key, or path. The owner enters the key later. Local cuts off the Internet. It may still connect to an approved internal LAN endpoint. It does not switch to the API by itself.
- Keep the Navy/Blue theme and the tokens. Text is readable across the whole app. The Orb has no square background and no extra shadow. Login and the panel use opaque backgrounds. Drag and resize do not cover content.
- History is used only to understand the requirements. Do not carry test accounts, secrets, machine paths, or old test results into the new set.

## PATH, LLM, and the tool installation directory

- Do not hardcode PATH, an executable path, a model path, or an LLM provider, endpoint, or key in source or scripts.
- The owner has decided that every project tool and runtime is installed under `E:\Programs`. The root is read from the deployment profile `installation.programs_root` or `EVIDENCE_PROGRAMS_ROOT`. It is not a path constant in the app.
- The manifest determines the app, runtime, database, tool, model store, and cache under the root. Do not use a global PATH, Program Files, or AppData fallback, and do not switch drives when the root is missing. Install only the components required for the machine's role. A USER machine does not get its own database installed.
- PDFs, business data, logs, and backups use their own configuration. Do not move that data on your own. Details: dossier B.8, SRS §25.9, and ADR-000.13.

## The parts/ directory

Three extracts are generated from the main dossier. They differ only in the outer title and the separator at the end of the part. When updating, edit `docs/HOSO_BAN_GIAO.md` and then regenerate all three. Do not edit them independently.

| File | Contents | For |
|---|---|---|
| `P1_Mo_ta_tinh_nang_A-C.md` | Decisions, the 8 approaches, features, USER desktop | Every stream |
| `P2_Thiet_ke_UX_UI_D.md` | Design system, S1–S14, portal/desktop, responsive, accessibility | Frontend/desktop |
| `P3_API_va_Plan_trien_khai_E-G.md` | API/SSE/permission matrix, 56 WP/gate, prompt | Backend/retrieval/evaluation |

Every deployment path comes from configuration, the environment, or a platform API. Do not copy a host, port, or path from the old machine.

## Work for the owner / the person who holds the business domain

F.11 states the complete list: approve the important business-domain principles of the ERD; approve Gold/trap; document permissions and egress; domain; retention of conversations and backups; quality thresholds after the baseline; provide the target Windows machine and enter the provider, key, or local model themselves. The absence of a key or model does not block finishing the independent parts, but the real-AI gate is still not met. If there is no retention policy, do not store conversations long term.
