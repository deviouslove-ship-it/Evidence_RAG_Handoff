# Project Timeline and Disclosure

**Language / Ngôn ngữ:** English · [Tiếng Việt](PROJECT_TIMELINE.vi.md)

This project was created and is owned by Vu Tuan Anh.

## Before the Kiroween submission period (October 2026)
- Wrote the product description, specification and implementation plan.
- Scaffolded an initial skeleton, which did not meet the intended design, so that work was stopped.
- No working product was completed during this period.

## Kiroween 2026 (ongoing; snapshot through November 11, deadline December 4)
As of November 11, 2026, the current implementation has been built and continues to be updated using Kiro, including:
- Adjusting and redesigning features
- Upgrading the application
- Generating code
- Running tests
- Fixing bugs

The project owner confirms Kiro use from **October 30 through at least November 11, 2026**; use on both the office and home machines is confirmed through November 9. Kiro IDE used Claude Sonnet 5.5 and Claude Opus 5.5; work done by these models inside Kiro is recorded as Kiro-assisted work. Kiroween is still in progress, with a submission deadline of December 4, 2026.

## How this is evidenced

| Evidence | Covers | Strength |
|---|---|---|
| Kiro session logs stored locally | 7 sessions on one machine, from 2026-11-05 to 2026-11-08, plus the review session of 2026-11-09 | Direct. Detailed in [`KIRO_WORK_SUMMARY.en.md`](KIRO_WORK_SUMMARY.en.md) |
| Owner confirmation | October 30 – at least November 11, 2026; both machines through November 9 | Statement by the owner. Logs do not cover October 30 – November 4, the second machine or the Nov 10–11 updates |
| Reconstruction from code | `.kiro/specs/`, `.kiro/steering/` and the descriptions of existing functions | Derived from the current code. Not a historical Kiro record |

Notes:
- Git history shows one author account and does not record which tool wrote a change. The first commit (2026-11-08) is a snapshot of the working folder.
- The `.kiro/specs/` and `.kiro/steering/` files and the two hooks in `.kiro/hooks/` were initially added on 2026-11-09. They were **reconstructed from the implemented code** and are not Kiro-generated specs from the development period; effectivity and citation-pinning specs were updated on 2026-11-11. The only original Kiro artefact in `.kiro/` is `settings/permissions.yaml`, which Kiro drafted on 2026-11-07 and the owner applied.
- The stored-log statistics are a **snapshot through 2026-11-09, not the final Kiroween total**: 257 of 471 counted product files in Git (code, documents, configuration) have at least one Kiro write/edit command; 194 of them come from the historical logs of 2026-11-05 to 2026-11-09 17:19 and 63 were first touched in the current record-review turn (specs, steering, hooks, bilingual documents). 208 files have a whole-file write (`fs_write`). File counts are a lower bound and line counts an upper bound; they exclude the second machine and periods without logs. Only input legal documents, lock files, third-party assets and generated schemas are excluded; Markdown written to develop the project counts. Method and per-file list: [`KIRO_WORK_SUMMARY.en.md`](KIRO_WORK_SUMMARY.en.md) section 8 and [`KIRO_STATS_APPENDIX.en.md`](KIRO_STATS_APPENDIX.en.md).

## Not verified
Domain acceptance of search results, running the portable package on a second physical Windows machine, and real OpenAI/Gemini connections are not verified; no Gold question set is used to score the AI (ADR-010). See `KIRO_WORK_SUMMARY.en.md` section 9 and `docs/implementation-status.md`.

## License
Licensed under the Apache License, Version 2.0. See `LICENSE` and `NOTICE`.
