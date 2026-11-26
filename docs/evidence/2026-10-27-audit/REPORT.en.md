**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-10-27-audit/REPORT.md`. The Vietnamese file is the original.

# Technical review results for 2026-10-27

## Changes

- Session memory: each fact is actually deleted on the server, and dependent results are invalidated; expired sessions, a failed delete, an account switch, and concurrent stop and initialize are handled. A retry uses the old turn only if the question, the facts, the scope, and the date are unchanged.
- Default preferences require a valid category. Setting a default date and storing a long-term conversation are refused, because these two functions are not implemented; a fake successful save is not reported.
- The SSE flow checks the turn id, the event order, and the completion data, limits the buffer, and handles a dropped stream. A late response from a stopped turn does not clear the new result; a session that expires during a preference update does not hold the UI lock. The default date uses the local date and updates when the day changes; the category and the auto-selected date are reset when the account changes.
- Model configuration accepts at most 2,048 output tokens, within the runtime limit. A Local connection to `localhost` is pinned to the loopback address, and the corresponding Host and SNI are preserved. RAG-Anything was not added, and model weights were not downloaded.
- OpenAPI was updated, lint and type errors were fixed, and ProgramsRoot is synced when the service starts.

## Evidence

- [12/12 automated checks](final/summary.json) succeeded; the backend had **148 passed, 0 skipped** on real PostgreSQL, and the frontend had **34 passed**. The checks include lint, types, build, OpenAPI, migrations, fixtures, and path policy. The Rust suite had **17 passed** ([log](final/desktop-tests.txt)).
- The backend and the web interface respond with HTTP 200; two APIs that require login return 401 when there is no authentication ([result](final/stack-smoke.json)). This is a smoke test, not a full test through accounts and the desktop interface.
- The Local adapter makes a real HTTP connection to a simulated server on loopback, receives the model list, and sends the correct parameters ([result](final/local-adapter-smoke.json)). This was not a trial against Ollama, a real model, or an external API provider.
- A trial over real HTTP with a temporary PostgreSQL schema and a simulated model: login, saving a profile and a Local route, probe, calling the runtime with the parameters, creating a session, reading SSE, deleting a fact, and logout all passed ([result](final/registry-http-smoke.json)). The trial schema and server were torn down.
- The desktop release was built and has a window; the process was still responding after 5 seconds ([build](final/desktop-build.txt), [launch](final/desktop-launch-smoke.json)). Login, drag and drop, DPI, multiple monitors, and a long run were not tried. The exe file is 9,906,176 bytes, SHA-256 `D6538E059F8A926E3A1414A40F3A12F907B14CF0175B73A6790B9DB59909EEBC`; this size does not include the backend, the database, or the installer.
- The Rust toolchain was placed under ProgramsRoot for the development build, adding about 462,423,977 bytes on the machine; that space is not inside the exe. The total size of the distribution has not been measured.
- The public 12-PDF trial in a temporary store imported 12 drafts, 135 pages, and 648 nodes, of which 174 nodes have an exact verbatim position; 77 review tasks remain and no node is approved ([figures](../2026-10-26-code-audit/public-pdf-draft-ingest.json)). The time of 8.157 seconds is a measurement of that trial alone and does not prove answer quality or operational performance.

## Limits and remaining work

1. The database currently has 9 drafts and 3 versions pending review, and no approved version ([figures](final/database-summary.json)). Three documents that had previously been auto-approved were put back into review, because there was no page data and no citation position that could be cross-checked. A backup was created before the migration and the catalog was checked with `pg_restore --list`; a full restore has not been tried.
2. The current workflow has no interface to edit or reattach a missing citation position, or to restore old page content. Some documents therefore cannot be approved through the current interface; the source cross-check barrier is not bypassed. Scanned PDFs also need OCR and human review.
3. A real model could not be configured in the `ready` state; only policy, the adapter, and a simulated server were checked. External APIs, suggestion accuracy, and the domain Gold set have not been evaluated. The model runtime currently only selects evidence (căn cứ) codes that already exist and does not write a legal conclusion.
4. There is no acceptance on real Windows for the native operations, sustained load, a signed installer, or the user's hardware configuration. It cannot be concluded that every lag, crash, fake feature, or piece of dead code has been removed.
