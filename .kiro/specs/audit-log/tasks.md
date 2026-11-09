# Tasks: Hash-chained Audit Log

> Spec reconstructed from the implemented code on 2026-11-09. Checkboxes reflect what exists in the repository.

- [x] 1. `audit_events` table with `previous_hash`, `event_hash`, `event_order` (core migrations)
- [x] 2. Transactional append with advisory lock (`audit.py::append_audit`)
- [x] 3. Chain verification with truncation flag (`audit.py::verify_audit_chain`)
- [x] 4. Audit view API returning events plus chain status (`admin.py`, `admin_services.py`)
- [x] 5. Audit tab in the Admin Portal
- [ ] 6. External anchoring of the head hash (not present)
- [ ] 7. Full-chain verification beyond the 10,000-event window in a scheduled job (not present)
