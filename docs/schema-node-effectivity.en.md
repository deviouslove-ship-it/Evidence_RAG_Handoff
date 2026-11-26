**Language / Ngôn ngữ:** [Tiếng Việt](schema-node-effectivity.md) · English

English counterpart of `docs/schema-node-effectivity.md`. The Vietnamese file is the original.

# Schema node effectivity

Each node has its own review status and validity. An amendment (sửa đổi) relation is a directed graph among nodes that have been approved. The resolver runs to a fixed point. It does not stop at two hops of the context BFS.

Output states:

- `active`: there is no effectivity (hiệu lực) edge;
- `modified`/`repeal`/`suspend`: according to an approved edge;
- `unknown`: a cycle, a conflict, a missing edge, an unverified relation, or the resource guard.

A snapshot is staged and then published atomically under `snapshot_revision`. The cache must recheck the revision and the ACL. A worker error makes the snapshot stale and the system is fail-closed.

## Update according to the current source (migration `0011_effectivity.sql`, `backend/app/effectivity/`)

- **Two-axis model (ADR-008):**
  - Axis A (`effective_status` / `status`): `active`, `not_yet_effective`, `modified` (administrative-document (văn bản) level: `partially_modified`), `suspended`, `repealed`, `replaced`, `unknown`.
  - Axis B (`verification_state`): `verified`, `unverified`, `not_found`. The state `active` + `verified` is produced only from a person's confirmation (`effectivity_attestations`).
- **Hierarchy of administrative documents (văn bản) and provisions (điều khoản):** `document_effective_intervals` stores effectivity (hiệu lực) intervals at administrative-document level. `node_effective_intervals` stores node-level exceptions, including the subtree. A terminating status of the whole administrative document (`repealed`, `replaced`, `suspended`, `not_yet_effective`) overrides a node-level exception.
- **Relations at `node` scope (`node_amendments.scope = 'node'`):** supports `replace`, `suspend`, `modify`, and `repeal_partial`. After approval and snapshot publication, `replace` creates a `replaced` interval (`verified`), `repeal_partial` creates a `repealed` interval (`verified`), `suspend` creates a `suspended` interval (`verified`), and `modify` creates a `modified` interval (`unverified`).
