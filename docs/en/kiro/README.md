# Vietnamese translations of `.kiro/specs` and `.kiro/steering`

**Language / Ngôn ngữ:** [Tiếng Việt](../../vi/kiro/README.vi.md) · English

Kiro reads the English files in `.kiro/specs/` and `.kiro/steering/` directly. The canonical files are in [`.kiro/`](../../../.kiro/). The files under `docs/vi/kiro/` are **translations for Vietnamese readers only**; they do not replace the canonical files and Kiro does not read them. If the two copies differ, the English copy is canonical.

**Honest limit.** The specs and steering were **initially reconstructed from code already implemented on 2026-11-09**; the effectivity and citation-pinning specs were synchronized on 2026-11-11; the OCR and Model Registry specs were updated against the source after the upgrade on 2026-11-17. The 2026-11-17 sync was not a Kiro work session. These are not historical specs that Kiro created during development (no Kiro session used spec mode). A `[x]` in tasks means the item exists in the repository; see the 2026-11-17 report for what was tested, and do not infer that every item was retested. See [`KIRO_WORK_SUMMARY.en.md`](../../../KIRO_WORK_SUMMARY.en.md).

## Steering
- [product.vi.md](../../vi/kiro/steering/product.vi.md) — canonical: [`.kiro/steering/product.md`](../../../.kiro/steering/product.md)
- [tech.vi.md](../../vi/kiro/steering/tech.vi.md) — canonical: [`.kiro/steering/tech.md`](../../../.kiro/steering/tech.md)
- [structure.vi.md](../../vi/kiro/steering/structure.vi.md) — canonical: [`.kiro/steering/structure.md`](../../../.kiro/steering/structure.md)

## Specs (each translation combines requirements, design and tasks)
| Spec | Translation | Canonical files |
|---|---|---|
| Document management | [document-management.vi.md](../../vi/kiro/specs/document-management.vi.md) | [`.kiro/specs/document-management/`](../../../.kiro/specs/document-management/) |
| Search and Q&A | [search.vi.md](../../vi/kiro/specs/search.vi.md) | [`.kiro/specs/search/`](../../../.kiro/specs/search/) |
| Effectivity | [effectivity.vi.md](../../vi/kiro/specs/effectivity.vi.md) | [`.kiro/specs/effectivity/`](../../../.kiro/specs/effectivity/) |
| Citation pinning | [citation-pinning.vi.md](../../vi/kiro/specs/citation-pinning.vi.md) | [`.kiro/specs/citation-pinning/`](../../../.kiro/specs/citation-pinning/) |
| Audit log | [audit-log.vi.md](../../vi/kiro/specs/audit-log.vi.md) | [`.kiro/specs/audit-log/`](../../../.kiro/specs/audit-log/) |
| OCR | [ocr.vi.md](../../vi/kiro/specs/ocr.vi.md) | [`.kiro/specs/ocr/`](../../../.kiro/specs/ocr/) |
| Embedding | [embedding.vi.md](../../vi/kiro/specs/embedding.vi.md) | [`.kiro/specs/embedding/`](../../../.kiro/specs/embedding/) |
| Model Registry | [model-registry.vi.md](../../vi/kiro/specs/model-registry.vi.md) | [`.kiro/specs/model-registry/`](../../../.kiro/specs/model-registry/) |
| AI interpretation and synthesis | [ai-synthesis.vi.md](../../vi/kiro/specs/ai-synthesis.vi.md) | [`.kiro/specs/ai-synthesis/`](../../../.kiro/specs/ai-synthesis/) |
| Windows LAN Portable | [windows-lan-portable.vi.md](../../vi/kiro/specs/windows-lan-portable.vi.md) | [`.kiro/specs/windows-lan-portable/`](../../../.kiro/specs/windows-lan-portable/) |

## Hooks
Two hooks live in [`.kiro/hooks/`](../../../.kiro/hooks/):
- `backend-python-lint.json`: after a `.py` file under `backend/` is saved, run `ruff check <file>`; if the file is under `backend/app`, also run `mypy` (strict, `backend/pyproject.toml`).
- `frontend-typescript-check.json`: after a `.ts`/`.tsx` file under `frontend/src/` is saved, run `eslint <file> --max-warnings=0` and then `tsc --noEmit` (`tsc` checks the whole frontend project because a single file cannot be type-checked alone inside the project).

Both call [`scripts/kiro-hook-check.ps1`](../../../scripts/kiro-hook-check.ps1). Tools are taken from `EVIDENCE_PROGRAMS_ROOT` via `configs/development-toolchain.json` (the same source as `scripts/verify.ps1`) and from `frontend/node_modules`; PATH is not used. The result is PASS (code 0), FAIL (code 1), or SKIPPED with a reason (code 3, for example a missing tool). Each run is appended to `.agents/hook-logs/kiro-hooks.log` (not committed), because Kiro does not show `PostFileSave` output in the chat pane.

Kiro emits `PostFileSave` both when a file is saved in the editor and when the agent writes a file (`fs_write`, `str_replace`, `fs_append`), so an extra `PostToolUse` hook is not used, to avoid running twice. The hook was observed firing on 2026-11-09 when the agent wrote a deliberately broken test file (FAIL), then fixed it (PASS). Saving a file by hand in the editor has not been tried.
