# Windows deployment

**Language / Ngôn ngữ:** [Tiếng Việt](README.md) · English

English counterpart of `README.md` (the Vietnamese original). The paths below are configuration placeholders, not values embedded in the source.

1. The owner provides `installation.programs_root` through the deployment profile or `EVIDENCE_PROGRAMS_ROOT`.
2. Install runtimes/tools/models per the dependency manifest under that root; do not change the system-wide PATH.
3. Configure `DATABASE_URL` and separate data/log/backup roots. To enable the draft-PDF intake API, set `EVIDENCE_DOCUMENT_STORE_ROOT` to the absolute path of a document store with restricted access; original PDFs are stored by SHA-256 under `originals/`. This is deployment data, separate from the Core, and must not be hard-coded.
4. Apply migrations in a maintenance window.
5. Run `verify-egress`, a smoke test, backup and restore.
6. Register the backend/worker as a Windows service using a wrapper from the manifest.

## Ready-to-run package (portable): the simplest way to run on another machine

`scripts/package-portable.ps1 -PackageDirectory <target folder> [-Zip] [-Force] [-SkipBuild]` creates a self-contained folder (about 216 MB, 77 MB compressed) with: relocatable Python and the backend packages (no venv, because a venv hard-codes paths), PostgreSQL with pgvector and `vcruntime140*.dll`, the built web app, backend code, the launcher (`evidence.ps1` + `start/stop/status/open-firewall/close-firewall.cmd`), `config\evidence.env` and `README.txt`.

- No hard-coded paths or IPs: every path is computed from the location of `evidence.ps1`; the access address is detected at run time; ports/bind addresses are configured in `evidence.env`. The packaging script scans text files and stops if any development-machine path remains.
- The package is **clean**: no database, documents, accounts or passwords. The first run creates a new PostgreSQL cluster (UTF8, locale C, `scram-sha-256`, listening on `127.0.0.1` only), the `evidence_rag` database, a random password (`secrets\postgres.password`), runs migrations and creates four accounts `admin/curator/reviewer/chuyenvien` with one random initial password (or `-BootstrapPassword`). It approves no document.
- The launcher ignores the host's `PYTHON*`/`PG*` variables, uses the Python and PostgreSQL in the package, writes no registry or folder outside the package, and needs no Administrator rights (only `open-firewall.cmd` does). Windows PowerShell 5.1 ships with Windows 10/Server 2016+.
- Verified (2026-11-06) on another drive, a path with spaces, a minimal PATH and deliberately wrong environment variables: first run 12–16 s; 30 business steps over HTTP passed (login, forced password change, PDF intake through a child process, approval, search, Q&A, open original PDF, audit chain); clean stop 1 s; restart 4 s with data kept; changing the port/bind address works. **Not verified:** a truly empty Windows machine (Visual C++/system updates never installed), Windows Server, antivirus on the target machine, access from another machine through the firewall.
- Limits: unencrypted HTTP; one process; not yet a Windows service; no OCR (Tesseract) in the package; no desktop app in the package (web through a browser).

## Trial over the LAN from the development machine (test phase)

`scripts/start-local-stack.ps1 -Lan [-Port 8000] [-OpenFirewall]` lets other machines on the internal network use the web app at `http://<server IP>:<Port>/`:

- The backend listens on `0.0.0.0` and serves `frontend/dist` (variable `EVIDENCE_WEB_ROOT`, an absolute path to the folder containing `index.html`, set by the script) on the same origin as the API; it does not use `pnpm dev` and needs no Node on the server once `dist` exists.
- PostgreSQL still listens on `127.0.0.1` only.
- `-OpenFirewall` (needs an administrator PowerShell) creates the rule "Evidence RAG test (TCP port)" for the Private/Domain profile, from the local subnet only. Remove with `Remove-NetFirewallRule -DisplayName "Evidence RAG test (TCP 8000)"`.
- Unencrypted HTTP, no TLS or reverse proxy; do not use outside a trusted test network.
- Current limits: one process, at most 64 in-memory sessions (8 per user), 8 concurrent Q&A turns, 4 concurrent DB search turns; the excess waits or receives a `*_BUSY` code.

There is no service wrapper and no clean-install evidence on a target machine; do not treat this document as evidence for WP 0.2/4.3.

To check the POC on an allocated dev environment, set `EVIDENCE_PROGRAMS_ROOT` or pass `-ProgramsRoot`, then run `scripts/verify.ps1` from the repository root. The log and limits of the 2026-10-22 run are in `docs/evidence/2026-10-22-takeover/REPORT.md`. This script does not deploy a database/service or package Tauri.

For the offline LAN package see `deploy/lan-portable/README.en.txt`.
