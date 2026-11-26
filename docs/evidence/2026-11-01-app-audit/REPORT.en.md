**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-11-01-app-audit/REPORT.md`. The Vietnamese file is the original.

# Review of correctness, completeness, and stability — 2026-11-01

The backend, administrative-document (văn bản) search, chat retrieval, SSE, overload control, session management, the PDF processing boundary, the interface, and the Windows shell were reviewed. Bugs that had been reproduced were fixed. A green test run is not treated as domain acceptance, and it is not a guarantee that the machine cannot hang under every condition.

## Bugs and changes

| Confirmed issue | Fixed at the cause |
|---|---|
| Results were lost after 5,000 candidates; the totals and the clause (Khoản) pages were incomplete | PostgreSQL computes the document and clause totals and the pagination before the content is sent; the cut of the candidate set at 5,000 was removed |
| An unaccented keyword missed accented content | All of the words are searched on both the original index and the folded index |
| A keyword outside the quotation marks was dropped | The parser keeps the words; the phrase tier applies the accompanying keyword condition |
| A document number (số hiệu) with a prefix, or `NĐ/ND`, was handled inconsistently | The numeric part is split from the administrative-document (văn bản) type name; `đ/Đ` is normalized before SQL `lower` |
| Chat with a phrase dropped the document number (số hiệu) and therefore selected a different administrative document (văn bản) | The adapter keeps the document number and uses the shared pagination and ranking before the return limit |
| Vietnamese capitals and backfill variants were assigned the wrong tier | Candidates are taken with the folded GIN and verified against separately normalized content, without depending on locale C |
| Waiting on the pool, on ACL, or on a count was not under the shared deadline | One time budget covers the database portion; return `SEARCH_TIMEOUT`, and release the slot on cancel |
| Search could queue without a bound | A limit of 4 search database turns per process; overload is rejected after about 100 ms with `SEARCH_BUSY` |
| The audit lock prolonged the time to return a read result | Search audit has a limit of 250 ms; when it expires, a warning is recorded and the result is returned |
| SSE had finished, but the UI waited for the connection to close | Stop reading and cancel the reader when `answer_complete` arrives; still check that the evidence and the analysis are complete |
| Chat retrieval took about 5.6 seconds on a large corpus | Filter document ACL first, take candidates by index and metadata, then hydrate, avoiding materializing a wide security-view UNION; keep title and label search for old records |

Negative ACL, draft and provenance, effectivity (hiệu lực), document numbers (số hiệu), unaccented text, capitals, kì/kỳ, a phrase that crosses a breadcrumb, titles and labels not yet in the index, a total of 5,003 clauses (Khoản), and the clause window after position 5,000 were checked. The original evidence content was not changed, sources were not approved automatically, and model routing was not changed.

## Performance measurements

The corpus is **FICTIONAL (HƯ CẤU)**: 1,000 administrative documents (văn bản) × 100 clauses (Khoản) = 100,000 nodes; a separate schema, the same machine and planner configuration, with a warm-up. These are the times of the data-retrieval service. They do not include a real AI model or the whole UI interaction.

| Flow | p95 before | p95 after | Samples per run |
|---|---:|---:|---:|
| Phrase | 333.97 ms | 82.46 ms | 12 |
| Keyword | 327.05 ms | 60.57 ms | 12 |
| Chat retrieval without quotation marks | 5,663.26 ms | 1,810.39 ms | 5 |

Sources: `benchmark-before/benchmark.json`, `benchmark-final/benchmark.json` (chat before the optimization), and `benchmark-accepted/benchmark.json` (the SQL that was kept). Chat on this corpus is still about 1.8 seconds at p95, and is not yet instantaneous. The other benchmark directories are intermediate or experimental measurements; they do not replace the final-code figures stated above.

A burst of 16 search turns on 100,000 nodes: 4 completed, and 12 received `SEARCH_BUSY`; the slots returned to 4/4, and the database was still responding. The largest event-loop heartbeat gap was about 46 ms; this is not a measurement of WebView frame latency or of the operating system. The actual phrase-page SQL plan uses `document_nodes_search_folded_gin`, and seqscan is not forced off.

## Verification

- `scripts/verify.ps1`: **12/12** passed; **193 backend and 73 frontend** tests, with no PostgreSQL skip. Lint, typing, the build, and the OpenAPI contract passed.
- **17 native Rust tests** passed. A release build was made with `custom-protocol`, the lockfile, and the existing runtime and cache; a window was opened, chat was observed, the view was switched to the search page, a response was confirmed, and then the correct smoke process was stopped.
- Real HTTP through Uvicorn and a separate schema: login, a search of 3 approved fixture administrative documents (văn bản), missing authentication, SSE, **35 consecutive chat turns**, 20 concurrent health requests, logout, and rejection of a revoked token. There were no errors; the server was still alive after the run.
- Existing tests check cancellation of a turn, timeout, loss of the session, isolation of a PDF-worker crash or timeout, and cleanup of temporary files. New tests check pool exhaustion, cancellation while waiting for the pool, overload rejection, and a real audit lock. Chrome E2E with the fixture API was run again after the build.
- Evidence: `verification/summary.json`, the `*-red.txt` logs, `native-tests.log`, `native-release-build.log`, `native-smoke.json`, `native-ui.txt`, `http/http-smoke.json`, `browser-e2e.json.log`, and the benchmark directories.

## Remaining limits

- The dev database, checked directly: **0 approved versions, 0 provenance verified, 0 models ready** (`dev-data-status.json`). Correctness and completeness on real domain administrative documents (văn bản), and the time to select evidence (căn cứ) with a real AI model, have not been accepted.
- The HTTP smoke uses FICTIONAL (HƯ CẤU) data and approval state; the PDF is only a sentinel that checks the hash and the byte boundary, and it is not acceptance of rendering or of domain provenance. The schema and the temporary files were cleaned up after the run.
- The native smoke did not log in and did not connect to the backend on the default port; HTTP was checked separately, and Chrome used the fixture API. There is not yet an end-to-end Windows session through to real data and models.
- No crash or hang was reproduced in the cases that were run. There has been no multi-hour soak, no trial of running out of memory or of the whole operating system, and no proof that memory does not leak under every condition.
- The RAM figures in `native-smoke.json` are only the Windows shell process. They do not include WebView2, PostgreSQL, or a model.
- The document-page depth limit and the configured timeout still apply explicitly through error codes; going past the threshold requires narrowing the query. Admission and the rate limit are currently per process.
- A local release executable was built. A new NSIS installer has not been created, signed, or published.

## Run again

Set `EVIDENCE_PROGRAMS_ROOT` and `EVIDENCE_TEST_DATABASE_URL`; resolve the executable from `configs/development-toolchain.json`. The benchmark uses the DSN in `DATABASE_URL`.

```text
scripts/verify.ps1 -ProgramsRoot <ProgramsRoot>
python scripts/benchmark_search.py --documents 1000 --nodes-per-document 100 --iterations 12 --concurrency 16 --output <output>
python scripts/smoke_app_runtime.py --output <output> --soak-turns 35
cargo test --offline --locked --manifest-path src-tauri/Cargo.toml
cargo build --release --offline --locked --features custom-protocol --manifest-path src-tauri/Cargo.toml
```

Use `CARGO_HOME` and `CARGO_TARGET_DIR` from the project runtime and cache. Do not add an absolute path to the source, and do not change a dependency or the lockfile.
