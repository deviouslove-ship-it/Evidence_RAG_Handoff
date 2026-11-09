# Vietnamese Evidence RAG Agent

**Language / Ngôn ngữ:** [Tiếng Việt](README.md) · English

Grounded lookup of Vietnamese legal documents. One FastAPI backend, one PostgreSQL database and a SHA-256-immutable PDF store serve the **User Portal** (Q&A, document search), the **Admin Portal** and the **Windows USER app (Tauri 2)**. Current state: [`docs/implementation-status.md`](docs/implementation-status.md) (Vietnamese).

This is the English counterpart of `README.md`. The Vietnamese file is the original.

## Built with Kiro (Kiroween 2026)

The project was developed with Kiro (Claude Sonnet 5.5 and Claude Opus 5.5) from 2026-10-30 to 2026-11-09, as confirmed by the project owner.

- Evidence and limits: [`KIRO_WORK_SUMMARY.en.md`](KIRO_WORK_SUMMARY.en.md), [`PROJECT_TIMELINE.md`](PROJECT_TIMELINE.md)
- Architecture overview: [`docs/en/ARCHITECTURE_OVERVIEW.md`](docs/en/ARCHITECTURE_OVERVIEW.md)
- Kiro specs (10 groups), steering and hooks: [`.kiro/`](.kiro/). They were reconstructed from the implemented code on 2026-11-09 and are not historical Kiro specs. Vietnamese translations: [`docs/vi/kiro/`](docs/vi/kiro/README.vi.md)

## Run locally

Tools, runtimes and development data live under `E:\Programs\EvidenceRAG` (pass it with `-ProgramsRoot` or `EVIDENCE_PROGRAMS_ROOT`).

```powershell
$env:EVIDENCE_BOOTSTRAP_PASSWORD = "<bootstrap password, needed on the first run only>"
.\scripts\start-local-stack.ps1 -ProgramsRoot E:\Programs -LaunchDesktop
```

The script starts PostgreSQL on `127.0.0.1:55432`, the backend on `127.0.0.1:8000` (`/health`), the web app on `127.0.0.1:1420` and, optionally, the desktop app.

On the first run against an empty database, `scripts/seed_local_runtime.py` creates a trial category and four accounts that use the password `EVIDENCE_BOOTSTRAP_PASSWORD`; a password change is forced at first login:

| Account | Role | Used for |
|---|---|---|
| `admin` | `SYS_ADMIN`, `AUDITOR` | Categories, accounts, AI configuration, audit log |
| `curator` | `CURATOR` | Upload PDFs, create and submit drafts |
| `reviewer` | `REVIEWER` | Review, approve or reject drafts |
| `chuyenvien` | `USER` | Q&A and document search |

### Ready-to-run package to copy to another machine (no installation)

The development machine builds a clean package that runs on any 64-bit Windows machine (even without Python, PostgreSQL or Node):

```powershell
.\scripts\package-portable.ps1 -ProgramsRoot E:\Programs -PackageDirectory <target folder> -Zip
```

Copy the folder (or zip) to the target machine and run `start.cmd`. On first run the package creates an empty database, a random database password and random initial passwords for the four accounts (printed on screen, saved in `secrets\first-login.txt`, change forced at first login). Access addresses (IP, host name) are detected at run time; ports, bind addresses and AI mode are in `config\evidence.env`. Operator guide: `README.txt` inside the package (source: `deploy/portable/`). The package contains no data or passwords from the development machine.

For the offline package with local models see [`deploy/lan-portable/README.en.txt`](deploy/lan-portable/README.en.txt) and [`deploy/windows/README.en.md`](deploy/windows/README.en.md).

### Let others test over the LAN from the development machine (web)

The simplest way for the test phase is to let users open a **browser**: nothing to install on their machines. The desktop app connects only to `127.0.0.1`, so it does not apply here.

```powershell
# First time, open PowerShell "Run as administrator" to open the firewall port (local network only):
.\scripts\start-local-stack.ps1 -ProgramsRoot E:\Programs -Lan -OpenFirewall
# Later runs, normal shell:
.\scripts\start-local-stack.ps1 -ProgramsRoot E:\Programs -Lan
```

The script prints addresses like `http://<server IP>:8000/` to send to testers. The backend also serves the built web app (`frontend/dist`) on the same port, so no CORS or API address setup is needed; PostgreSQL still listens on `127.0.0.1` only. Build the web app first if `frontend/dist` is missing. Paths come from the script location and `-ProgramsRoot`/`EVIDENCE_PROGRAMS_ROOT`; none is hard-coded. This uses unencrypted HTTP: trusted networks only.

The seed does not approve any document and creates no model profile. Re-running it does not reset passwords, permissions or approval state.

## Features

- **Grounded Q&A**: a short structured answer, one card per document (type, number, date, body, summary, Article/Clause, short verbatim quote, effectivity) and an "Open original" button (PDF opens in its own tab at the right page; Word/TXT downloads the uploaded file); phrase matching, a separate list for catalogue-style documents; SSE with stop/retry; session memory in RAM only.
- **Document search** (one page, built on comprehensive search G2): by meaning, all words, exact phrase; filters for category, document type, effectivity and time; grouped by document with paging; partial matches in their own group.
- **Admin Portal**: [Document management](docs/en/USER_ADMIN_AND_AI_GUIDE.md#document-management) supports search/filter, detail, version history, OCR edits, suspension and soft delete by permission. The portal also has source intake and review, categories, RBAC/ABAC accounts, AI models (profiles, stage routing for evidence selection, connection tests) and a hash-chained audit log.
- **Document intake**: PDF, Word (`.docx`, `.doc`) and TXT. Word/TXT are rendered into a text-layer PDF (same content, same result each time) so one citation path serves all formats; the original file is kept with its own hash (`document_versions.source_format`, `source_file_sha256`). Scanned PDFs need OCR (Tesseract). Bulk import by folder tree: `scripts/import_official_corpus.py` (see [`test-data/README.md`](test-data/README.md)).
- **AI**: `API` or `LOCAL` mode (Ollama/vLLM/llama.cpp or OpenAI-compatible services: `/v1`, Google Gemini `/v1beta/openai`, `/openai/v1`, `/api/v1`). The model picks at most 3 evidence items from already verified evidence and does not write citations. If the model fails or is slow, a chat turn still returns the original evidence. Recommended models and machine settings: [`docs/ai-model-recommendations.md`](docs/ai-model-recommendations.md) (Vietnamese).
- **Windows desktop**: floating Orb, drag-and-drop across multi-monitor/DPI work areas, system tray.

## Testing

```powershell
$pw = (Get-Content 'E:\Programs\EvidenceRAG\secrets\postgres-dev.password' -Raw).Trim()
$env:EVIDENCE_TEST_DATABASE_URL = "postgresql://evidence_dev_admin:$pw@127.0.0.1:55432/postgres"
.\scripts\verify.ps1 -ProgramsRoot E:\Programs
```

`verify.ps1` runs 12 steps: dependency check, backend lint/typing/tests, source policy (no hard-coded paths), migration pairs, OpenAPI, polarity and temporal fixtures, frontend lint/test/build. PostgreSQL tests use a temporary schema removed afterwards; CI must not skip them. Performance: `scripts/benchmark_search.py`; HTTP smoke test: `scripts/smoke_app_runtime.py`.

## Documents

Original files are Vietnamese unless stated; English counterparts are listed.

| Document | Content | English |
|---|---|---|
| `00_README.md` | Handoff index and specification priority | – |
| `docs/HOSO_BAN_GIAO.md`, `docs/SRS_v1.3.md` | Main handoff file and current technical specification | Not translated (large specification) |
| `docs/architecture-decisions/ADR-000…009` | Architecture decisions | Not translated |
| `docs/TAI_LIEU_MO_TA_HE_THONG.md` | System description and document lifecycle | [`docs/en/SYSTEM_DESCRIPTION.md`](docs/en/SYSTEM_DESCRIPTION.md) |
| `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md` | User and administrator guide, including Document management | [`docs/en/USER_ADMIN_AND_AI_GUIDE.md`](docs/en/USER_ADMIN_AND_AI_GUIDE.md) |
| `deploy/lan-portable/README.txt` | Windows LAN Portable operator guide | [`README.en.txt`](deploy/lan-portable/README.en.txt) |
| `deploy/windows/README.md` | Windows deployment notes | [`README.en.md`](deploy/windows/README.en.md) |
| `docs/vi/ARCHITECTURE_OVERVIEW.md` | Architecture overview (Vietnamese) | [`docs/en/ARCHITECTURE_OVERVIEW.md`](docs/en/ARCHITECTURE_OVERVIEW.md) |
| `KIRO_WORK_SUMMARY.vi.md`, `PROJECT_TIMELINE.vi.md` | Kiro work record and timeline | [`KIRO_WORK_SUMMARY.en.md`](KIRO_WORK_SUMMARY.en.md), [`PROJECT_TIMELINE.md`](PROJECT_TIMELINE.md) |
| `docs/implementation-status.md` | State, verification, remaining limits | Not translated |
| `docs/search-v1-runbook.md` | Search and chat retrieval operations | Not translated |
| `docs/threat-model.md` | Threat model | Not translated |
| `docs/evidence/` | Reports and evidence per round | Not translated |
| `configs/` | AI, deployment, policy templates | – |

## Layout

```text
backend/          FastAPI: authentication, RBAC/ABAC, source review, search, pipeline, migrations
frontend/         React + TypeScript: User Portal, Admin Portal, Orb UI (#/orb)
src-tauri/        Tauri 2 shell for Windows USER
evaluation/       Public corpus, search evaluation harness (FICTIONAL cases)
configs/          Configuration templates
deploy/           Windows notes, portable and LAN portable package sources
tools/            Egress check, hash, footprint
scripts/          verify, seed, stack start, benchmark, smoke
docs/             Specifications, ADRs, OpenAPI, runbooks, evidence; docs/en and docs/vi for translations
parts/            Extracts of the main handoff file (regenerated from docs/HOSO_BAN_GIAO.md)
.kiro/            Kiro permissions, specs, steering, hooks
```

## Safety principles

1. The agent only advises and is read-only; it has no tool that writes or approves business data.
2. ACL filtering happens in SQL for the user before candidates are taken; citations and PDFs are re-checked for permission and hash when opened.
3. Citations come from the approved `text_original`; the LLM writes neither citations nor clause IDs.
4. `API` and `LOCAL` go through the Registry/Router; sending data outside is blocked by default; `LOCAL` refuses every `public` profile (`REMOTE_AI_DENIED`).
5. Separation of duties: `CURATOR` prepares/submits drafts; only a different `REVIEWER` can approve (`SELF_APPROVAL_DENIED`).
6. Session memory is never evidence; by default it lives in RAM only.
7. Gold/trap cases count only after the domain owner approves them.

## License
Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE. Project history is described in [PROJECT_TIMELINE.md](PROJECT_TIMELINE.md).
