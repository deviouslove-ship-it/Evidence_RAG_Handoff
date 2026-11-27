**Language / Ngôn ngữ:** [Tiếng Việt](ADR-001-windows-runtime.md) · English

English counterpart of `docs/architecture-decisions/ADR-001-windows-runtime.md`. The Vietnamese file is the original.

# ADR-001 — Windows runtime and PostgreSQL as the only database

**Status:** Technical proposal, not yet verified on the target machine.

## Decision

- PostgreSQL is the only database; migrations use `pgcrypto` and `pgvector`.
- Python uses FastAPI/asyncpg; managed project tools and runtime resolve from the deployment profile `installation.programs_root` or `EVIDENCE_PROGRAMS_ROOT`.
- No fallback to an executable in the global PATH, `Program Files`, `AppData`, `Downloads`, or another drive.
- PostgreSQL data, original PDFs, logs, and backups have their own configured paths; the agent does not move them on its own.
- Local Mode allows only loopback/LAN endpoints that are on the allowlist; there is no mechanism that switches to the API on its own.

## Consequences

1. `DATABASE_URL` is required outside the in-memory POC.
2. `verify-egress` must be run on the target Windows machine after the firewall is configured; the application's self-check does not replace actually disconnecting the Internet.
3. If pgvector has no approved Windows build, the specific build/install approach must be recorded in a subsequent ADR; do not switch to another database.
4. Acceptance requires a clean install, a service restart, an encrypted backup, and a restore onto a clean machine.

## What has not yet been demonstrated

There is not yet evidence of installing PostgreSQL/pgvector, registering the service, an exact-vector benchmark, backup/restore, or a real Internet disconnect on the target machine.
