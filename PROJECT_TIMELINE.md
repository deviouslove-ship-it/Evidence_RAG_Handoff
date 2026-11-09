# Project Timeline and Disclosure

**Language / Ngôn ngữ:** English · [Tiếng Việt](PROJECT_TIMELINE.vi.md)

This project was created and is owned by Vu Tuan Anh.

## Before the Kiroween submission period (October 2026)
- Wrote the product description, specification and implementation plan.
- Scaffolded an initial skeleton, which did not meet the intended design, so that work was stopped.
- No working product was completed during this period.

## During the Kiroween submission period (October 30 – November 9, 2026)
The current implementation was built and refined using Kiro, including:
- Adjusting and redesigning features
- Upgrading the application
- Generating code
- Running tests
- Fixing bugs

The project owner confirms that Kiro was used from **October 30, 2026 to the end of November 9, 2026**, on **both an office machine and a home machine**. Kiro IDE used Claude Sonnet 5.5 and Claude Opus 5.5; work done by these models inside Kiro is recorded as Kiro-assisted work.

## How this is evidenced

| Evidence | Covers | Strength |
|---|---|---|
| Kiro session logs stored locally | 7 sessions on one machine, from 2026-11-05 to 2026-11-08, plus the review session of 2026-11-09 | Direct. Detailed in [`KIRO_WORK_SUMMARY.en.md`](KIRO_WORK_SUMMARY.en.md) |
| Owner confirmation | October 30 – November 9, 2026, both machines | Statement by the owner. No log is available for October 30 – November 4 or for the second machine |
| Reconstruction from code | `.kiro/specs/`, `.kiro/steering/` and the descriptions of existing functions | Derived from the current code. Not a historical Kiro record |

Notes:
- Git history shows one author account and does not record which tool wrote a change. The first commit (2026-11-08) is a snapshot of the working folder.
- The `.kiro/specs/` and `.kiro/steering/` files and the two hooks in `.kiro/hooks/` were added on 2026-11-09. They were **reconstructed from the implemented code** and are not Kiro-generated specs from the development period. The only original Kiro artefact in `.kiro/` is `settings/permissions.yaml`, which Kiro drafted on 2026-11-07 and the owner applied.
- Statistics of the stored logs (194 of 421 tracked files touched by Kiro write commands) are a lower bound for files and an upper bound for lines; they exclude the second machine and the period without logs.

## Not verified
Domain acceptance of search results, expert-confirmed gold sets, running the portable package on a second physical Windows machine, and real OpenAI/Gemini connections are not verified. See `KIRO_WORK_SUMMARY.en.md` section 9 and `docs/implementation-status.md`.

## License
Licensed under the Apache License, Version 2.0. See `LICENSE` and `NOTICE`.
