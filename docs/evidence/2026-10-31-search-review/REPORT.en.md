**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-10-31-search-review/REPORT.md`. The Vietnamese file is the original.

# Search v1 review and fixes — 2026-10-31

Scope: the new search page, the `/search` and `/search/approximate` APIs, pagination, input checks, and separation of the result tiers. Search v1 uses PostgreSQL FTS according to ADR-005 and does not call an AI model. The Registry/Router and the evidence content were not changed.

## Bugs reproduced and fixed

| Bug | Cause | After the fix |
|---|---|---|
| Loading more clauses (Khoản) after editing the search box mixed the results of two questions | Pagination read the form that was being edited | Use the most recent successful query; leave the text being typed unchanged |
| Load-more hit an error, then clicking again skipped one page of clauses (Khoản) | The page was incremented before the result arrived | Record only a successful page; the next request asks again for the page that failed |
| Opening a URL with `clause_page>1` lost the leading clauses (Khoản) | The clause buffer existed only in RAM | When the page is opened again, start from the first clause window and keep the question and the filters |
| Approximate results also contained clauses (Khoản) that fully matched the words or the phrase | The query that fetches results lacked the exclusion condition of the count query | The two queries share the filter condition; a full match is not tagged `any_term` |
| A quoted phrase longer than 200 characters got through the limit | The regex did not recognize an over-long phrase and fell through to keywords | Recognize the phrase first and return `QUERY_TOO_LONG` according to the rule |
| There were partial results, but the interface would not open them when the main results were empty | The approximate section sat inside the condition that a main document exists | The approximate section is independent of the main result list |
| Approximate results could not be requested when the backend skipped the optional count step | The interface showed the button only if the count was greater than 0 | Always allow a request on demand; if there is no count yet, do not write "0 clauses" ("0 khoản") |
| The approximate total was lower than the actual list when the suggestion-count ceiling was hit | The detail endpoint reused the suggestion-count ceiling | The total and the `capped` flag describe the actual candidate set; one redundant count query was removed |
| An approximate administrative document (văn bản) could not be viewed past the first page | Pagination controls were missing; loading more clauses always sent `page=1` | Added Previous/Next ("Trước"/"Sau") following the existing convention; loading more clauses keeps the correct page of the approximate administrative document (văn bản) |
| The PDF of an approximate result could not be opened when the main list was empty | The viewer sat inside the condition that a main document exists | Reuse the existing viewer for the case that has only approximate results |

The regression cases were run before the fix and failed with the corresponding bug. The additional PostgreSQL tests also check that a principal without permission receives neither the results nor the approximate total.

## Verification

- Ran `scripts/verify.ps1` with `EVIDENCE_TEST_DATABASE_URL`: 12/12 steps passed.
- Backend: 188 tests passed, with no PostgreSQL skip; 1 deprecation warning from the Starlette/AnyIO library, which is not a test failure.
- Frontend: 72 tests passed; lint and build passed. The existing suite includes contrast, accessibility, Local Mode, and the link from chat to search.
- The existing Chrome headless E2E passed: simulated login, a phrase search, load more clauses (Khoản), open approximate results, and open the fixture PDF; no HTTP(S) request left the local origin.
- Logs: `verification/summary.json`, the logs in `verification/`, and `browser-e2e.json.log`. The `approximate-*-red.txt` logs record the errors from before the fix.

## Limits of the evidence

- Browser E2E uses an API and PDF fixture; the DB tests use a separate schema and FICTIONAL (HƯ CẤU) data, and delete the schema after the run. Search correctness on approved domain administrative documents (văn bản), and the quality of evidence (căn cứ) selection by a real AI model, have not been accepted.
- The 100,000-node load benchmark and p95 were not remeasured in this fix round.
- The existing candidate limit is 5,000. The approximate endpoint marks `capped` when the threshold is hit; the total then is the total inside the candidate set, not the whole store.
- When a URL is opened again, the clause (Khoản) window starts over from the beginning; the old buffer is not reconstructed.
- The frontend was built; the Tauri Windows application was not repackaged or re-released.
- The first run found the local PostgreSQL stopped (`ConnectionRefusedError`). Dev PostgreSQL was started and the real tests were run again; this is an environment condition and was not recorded as a failure of the search code.

## Changed code files

- `backend/app/storage/search.py`
- `backend/tests/test_search_parser.py`
- `backend/tests/test_search_postgres.py`
- `frontend/src/pages/SearchPage.tsx`
- `frontend/src/pages/SearchPage.test.tsx`
