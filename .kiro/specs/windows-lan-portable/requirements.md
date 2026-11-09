# Requirements: Windows LAN Portable (offline)

> Spec reconstructed from the implemented code on 2026-11-09. This is not a historical Kiro-generated spec. Evidence is cited by repository path. Operator guide: `deploy/lan-portable/README.txt` (English: `deploy/lan-portable/README.en.txt`).

## Introduction

One folder runs the whole system on Windows 64-bit without Internet and without installing Python, Node.js, PostgreSQL, Ollama or Tesseract. Client machines only need a browser.

## Requirements

### Requirement 1: One-command start

#### Acceptance Criteria

1. WHEN the operator runs `Start-Server.bat` THE SYSTEM SHALL check runtime, models, database, ports and configuration, start the bundled PostgreSQL with pgvector, the bundled Ollama and the web/API server, check readiness and print the LAN address.
2. WHEN started a second time while running THE SYSTEM SHALL NOT create a second process.
3. IF a component is missing or a port is busy THEN THE SYSTEM SHALL name it and write details to `logs/launcher.log`.

### Requirement 2: First run from a seed

#### Acceptance Criteria

1. WHEN the first run finds no database THE SYSTEM SHALL initialise one from the bundled seed, compare table contents with the seed, and restore data, vectors and indexes without re-importing, re-running OCR or re-embedding.
2. THE SYSTEM SHALL NOT include plaintext passwords; accounts, roles, ACLs and audit data come from the seed.

### Requirement 3: Network exposure

#### Acceptance Criteria

1. THE SYSTEM SHALL listen on LAN only for the web port (default 8800); PostgreSQL (55433) and Ollama (21434) SHALL listen on `127.0.0.1` only.
2. THE SYSTEM SHALL NOT change Windows Firewall by itself; `tools/Allow-LAN-Firewall.bat` SHALL add a rule only for the web port, local subnet, Private/Domain profiles, after an administrator prompt, and SHALL support `remove`.
3. THE SYSTEM SHALL document that the connection is unencrypted HTTP and suitable only for trusted networks.

### Requirement 4: Stop, status, verify

#### Acceptance Criteria

1. WHEN `Stop-Server.bat` runs THE SYSTEM SHALL stop only processes started from the package folder (PostgreSQL with fast shutdown).
2. THE SYSTEM SHALL provide `tools/Status.bat` and `tools/Verify-Package.bat`, which compares SHA-256 of runtime, model, application and original files with the release `checksums.sha256`.

### Requirement 5: Backup and restore

#### Acceptance Criteria

1. WHEN `Backup-Data.bat` runs THE SYSTEM SHALL write a consistent database snapshot and the original-file store with per-file SHA-256, while the server runs.
2. WHEN `Restore-Data.bat` runs THE SYSTEM SHALL verify integrity, show contents, require the typed confirmation `KHOI PHUC`, back up current data to `backups\pre-restore-*`, build a new database, compare tables, then switch and keep the old data folder.
3. THE SYSTEM SHALL only add to the document store on restore and never delete files from it.

### Requirement 6: Configuration and portability

#### Acceptance Criteria

1. THE SYSTEM SHALL read ports, bind addresses, AI mode and limits from `config\evidence.env` and SHALL use only relative paths and a run-time detected IP.
2. THE SYSTEM SHALL synchronise local model profile endpoints with the bundled Ollama port at start.
3. THE SYSTEM SHALL generate the database password randomly at initialisation and keep it in `secrets\`; API keys SHALL be DPAPI-encrypted per Windows account.

### Requirement 7: Builder

#### Acceptance Criteria

1. THE SYSTEM SHALL provide `scripts/build-lan-portable.ps1` to assemble the package outside the repository; the release package (about 4.5 GB, zip 3.6 GB) SHALL NOT be committed.
