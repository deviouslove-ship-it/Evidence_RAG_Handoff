# Tasks: Document Management

> Spec reconstructed from the implemented code on 2026-11-09. Checkboxes reflect what exists in the repository, not a historical task run. Test results were not re-run when this spec was written.

- [x] 1. Migration `0016_document_management` (management fields, lookup-visibility counter) with down script
- [x] 2. Access rules per category/document ACL (`documents/management_access.py`)
- [x] 3. Read path: list, filters, detail, original (`documents/management_read.py`)
- [x] 4. Write path: new revision from edits, OCR page edits, availability actions (`documents/management_write.py`)
- [x] 5. Admin API routes (`api/v1/admin.py`: `/documents`, `/documents/actions`, `/documents/{id}`)
- [x] 6. Cross-process cache invalidation (`storage/lookup_visibility.py`)
- [x] 7. Admin Portal UI (`AdminDocumentManager.tsx`, `AdminDocumentDetail.tsx`)
- [x] 8. Backend and frontend tests exist (`test_document_management.py`, `test_lookup_visibility.py`, `AdminDocuments.test.tsx`)
- [ ] 9. Node picker UI for unresolved clause-level amendment targets (documented as not available in `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md`)
- [ ] 10. Independent verification run of the 09/11/2026 document-management commit (`ba596ce`) with `scripts/verify.ps1` recorded in `docs/evidence/` (not found in repository)
