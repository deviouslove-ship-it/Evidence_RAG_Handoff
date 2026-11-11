# Vietnamese Evidence RAG Agent

**Language / Ngôn ngữ:** [Tiếng Việt](README.md) · English

Grounded lookup of Vietnamese agency administrative and operational documents. One FastAPI backend, one PostgreSQL database and a SHA-256-immutable document store serve the **User Portal** (Q&A, document search), the **Admin Portal** and the **Windows USER app (Tauri 2)**. Current state: [`docs/implementation-status.md`](docs/implementation-status.md) (Vietnamese).

This is the English counterpart of `README.md`. The Vietnamese file is the original.

## Download the app (for judges)

- **Package:** `Evidence-RAG-Portable-20261111-r4.zip` (~3.52 GiB, 3,777,436,554 bytes; includes documents and local AI models). Extract with 7-Zip or Windows' built-in extractor.
- **Download:** https://drive.google.com/file/d/1C9bSKqt_7Rwuqe5NqtTZNzhABVqd7dj6/view?usp=sharing
- **SHA-256:** `989848708e2c1cd3be0d4a0e8978737bc03201f6c75415a37f2a434806636ed8`
- **Verify on Windows:** `Get-FileHash .\Evidence-RAG-Portable-20261111-r4.zip -Algorithm SHA256`
- **Minimum:** Windows 10 / Server 2016 or later (x64), about 8 GB RAM, 6 GB free disk space (per `deploy/lan-portable/README.en.txt`; the AI models run on CPU).
- **Recommended (tested):** Intel Core i3, 32 GB DDR4 RAM, 512 GB SSD.

**How to start** (steps from [`deploy/lan-portable/README.en.txt`](deploy/lan-portable/README.en.txt)):

1. Extract the WHOLE package with WinRAR or 7-Zip into a folder with a short path, for example `D:\EvidenceRAG`. Do not run it inside the archive. Administrator rights are not needed to run.
2. Double-click `Start-Server.bat` (no other command to type). It checks the runtime, models, database, ports and configuration, starts the package's own PostgreSQL + pgvector, Ollama and the web/API server, checks readiness and prints the access address through the LAN IP, for example `http://192.168.1.15:8800/`.
3. The first run takes 1-3 more minutes: the package builds its own database from the original data copy in `seed\` and compares every table with the original. Documents are not re-imported, not re-OCR'd, and vectors are not recreated. Later runs start in a few tens of seconds.
4. Open the printed address (or `http://127.0.0.1:8800/` on the same machine) in a browser. Other machines on the LAN only need a browser.
5. Stop with `Stop-Server.bat`. If other machines cannot connect, the package does not change Windows Firewall by itself: see section 4 of the README, `tools\Allow-LAN-Firewall.bat`. The connection is plain HTTP: use it only on a trusted network.

Complete guides inside the package: `USER_GUIDE.en.md` (English) and `HUONG_DAN_SU_DUNG.vi.md` (Vietnamese).

**Test accounts:** Demo credentials are in the account file `Acount_Demo.md` at the root of the zip package. `chuyenvien` can search right away. To test the full workflow, the admin grants `curator` the lookup categories, and grants `reviewer` both the lookup and the validity-confirmation categories (**Tài khoản & Phân quyền**, boxes **Danh mục được phép tra cứu (ABAC)** and **Danh mục được xác nhận hiệu lực (người duyệt)**). This r4 package already ships with all 9 categories granted to `curator` and `reviewer`; the admin can change them there. A user cannot approve their own submission.
## Built with Kiro (Kiroween 2026)

As of 2026-11-11, Kiro (Claude Sonnet 5.5 and Claude Opus 5.5) is still being used on the project; its use began on 2026-10-30. Kiroween 2026 is still in progress, with a submission deadline of 2026-12-04, as confirmed by the project owner.

- Evidence and limits: [`KIRO_WORK_SUMMARY.en.md`](KIRO_WORK_SUMMARY.en.md), [`PROJECT_TIMELINE.md`](PROJECT_TIMELINE.md), per-file statistics appendix [`KIRO_STATS_APPENDIX.en.md`](KIRO_STATS_APPENDIX.en.md)
- Architecture overview: [`docs/en/ARCHITECTURE_OVERVIEW.md`](docs/en/ARCHITECTURE_OVERVIEW.md)
- Kiro specs (10 groups), steering and hooks: [`.kiro/`](.kiro/). They were initially reconstructed from the implemented code on 2026-11-09; the effectivity and citation-pinning specs were updated on 2026-11-11. They are not historical Kiro specs. Vietnamese translations: [`docs/vi/kiro/`](docs/vi/kiro/README.vi.md)
- Kiro MCP: **Stitch** – UI design, results in [`.stitch/`](.stitch/) (server configured at user level; use confirmed by the project owner, no tool-call log: evidence type B, see [`KIRO_WORK_SUMMARY.en.md`](KIRO_WORK_SUMMARY.en.md) section 7)

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

- **Grounded Q&A**: a two-pane screen, with the current session's question/answer history (RAM) on the left and the answer/evidence on the right. Evidence cards paginate to fit the pane height and recalculate when it resizes; click `[n]` in an answer to scroll to that citation. Each document card shows type, number, date, body, summary, Article/Clause, a short verbatim quote and effectivity; "Open original" opens a PDF in a separate tab at the cited page or downloads the uploaded Word/TXT file. Phrase matching, a separate list for catalogue-style documents, SSE stop/retry, and session memory in RAM only.
- **Document search** (one page, built on comprehensive search G2): by meaning, all words, exact phrase; filters for category, document type, effectivity and time; grouped by document with paging; partial matches in their own group.
- **Admin Portal**: [Document management](docs/en/USER_ADMIN_AND_AI_GUIDE.md#document-management) supports search/filter, detail, version history, OCR edits, suspension and soft delete by permission. The portal also has source intake and review, categories, RBAC/ABAC accounts, AI models (profiles, stage routing for evidence selection, connection tests) and a hash-chained audit log.
- **Document intake**: PDF, Word (`.docx`, `.doc`) and TXT. Word/TXT are rendered into a text-layer PDF (same content, same result each time) so one citation path serves all formats; the original file is kept with its own hash (`document_versions.source_format`, `source_file_sha256`). Scanned PDFs need OCR (Tesseract). Bulk import by folder tree: `scripts/import_official_corpus.py` (see [`test-data/README.md`](test-data/README.md)).
- **AI**: `API` or `LOCAL` mode (Ollama/vLLM/llama.cpp or OpenAI-compatible services: `/v1`, Google Gemini `/v1beta/openai`, `/openai/v1`, `/api/v1`) routed per stage (`answer`, `summarize`, `expand`, `relation`, `label`, `embedding`, `rerank`). In Q&A, the model picks at most 3 evidence items from already verified evidence; in optional "AI interpretation" (`summarize`), each statement is checked by code against attached evidence; the model never writes verbatim quotes or citations. If the model fails or is slow, a chat turn still returns the original evidence. Recommended models and machine settings: [`docs/ai-model-recommendations.md`](docs/ai-model-recommendations.md) (Vietnamese).
- **Article/Clause/Point effectivity relations**: supports proposed replacements, amendments, additions and repeals. An authorized reviewer confirms each relation and its item-level effective date. A replacement may carry an earlier effective date; as-of lookup applies that date. Yellow warning notes appear when node-level effectivity is unverified or the query date is later than the store's data date.
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
| `docs/architecture-decisions/ADR-000…010` | Architecture decisions | Not translated |
| `docs/TAI_LIEU_MO_TA_HE_THONG.md` | System description and document lifecycle | [`docs/en/SYSTEM_DESCRIPTION.md`](docs/en/SYSTEM_DESCRIPTION.md) |
| `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md` | User and administrator guide, including Document management | [`docs/en/USER_ADMIN_AND_AI_GUIDE.md`](docs/en/USER_ADMIN_AND_AI_GUIDE.md) |
| `deploy/lan-portable/README.txt` | Windows LAN Portable operator guide | [`README.en.txt`](deploy/lan-portable/README.en.txt) |
| `deploy/windows/README.md` | Windows deployment notes | [`README.en.md`](deploy/windows/README.en.md) |
| `docs/vi/ARCHITECTURE_OVERVIEW.md` | Architecture overview (Vietnamese) | [`docs/en/ARCHITECTURE_OVERVIEW.md`](docs/en/ARCHITECTURE_OVERVIEW.md) |
| `KIRO_WORK_SUMMARY.vi.md`, `PROJECT_TIMELINE.vi.md` | Kiro work record and timeline | [`KIRO_WORK_SUMMARY.en.md`](KIRO_WORK_SUMMARY.en.md), [`PROJECT_TIMELINE.md`](PROJECT_TIMELINE.md), per-file statistics appendix [`KIRO_STATS_APPENDIX.en.md`](KIRO_STATS_APPENDIX.en.md) |
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
7. No Gold question set is used to score the AI (ADR-010): the AI only assists, the domain staff decide.

## License
Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE. Project history is described in [PROJECT_TIMELINE.md](PROJECT_TIMELINE.md).
