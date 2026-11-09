# Tasks: Citation Pinning

> Spec reconstructed from the implemented code on 2026-11-09. Checkboxes reflect what exists in the repository.

- [x] 1. Citation contract and anchor contract documents (`docs/citation-contract.md`, `docs/pdf-anchor-coordinate-contract.md`)
- [x] 2. Authorised citation lookup and routes (`storage/citations.py`, `main.py`)
- [x] 3. Immutable original storage with digest check (`documents/provenance.py`)
- [x] 4. Article/Clause/Point tree with parent, path and label (`tree_parser.py`, migration `0009`)
- [x] 5. Per-page source spans (`spans.py`, `node_writer.py`)
- [x] 6. Evidence validators reject model-supplied quotes (`evidence/validators.py`, `synthesis/checks.py`)
- [x] 7. "Open original" button for PDF, Word and TXT (`OpenOriginalButton.tsx`)
- [ ] 8. Real PDF fixtures proving highlight accuracy (open gate per anchor contract)
- [ ] 9. "Open original" check in the Tauri desktop shell and for TXT sources (reported as not verified in `docs/evidence/2026-11-08-user-lookup/REPORT.md`)
