**Language / Ngôn ngữ:** [Tiếng Việt](REVIEW_FIXES_2026-11-17.md) · English

# Review and fixes for the Qwen3.5 / OCR AI upgrade — 2026-11-17

## Scope and how it was checked

The review covered the upgrade being edited in the `Evidence_RAG_Handoff` checkout, on top of commit `e985408fcfb0d425bd219e6539a6b868905a0014`. Earlier AI changes were kept; this is the additional fix-up, not yet committed or pushed at the time of the review. Work started on 2026-11-16 and verification finished on 2026-11-17.

- A copy of the changed files from before the review was saved at `<TEMP>/evidence-qwen35-before-review-20261116-194748`.
- The trial PostgreSQL used a separate cluster in `<TEMP>/evidence-qwen35-review-pg-20261116-194838`; tests created and dropped schemas on a temporary database. The real-model flow used another temporary database so it did not contend for locks with the test suite.
- The trial Ollama used the executable configured in `EVIDENCE_PROGRAMS_ROOT`, its own loopback port, `OLLAMA_NO_CLOUD=true`, and a model store that was already present. Weights and the model manifest were not downloaded or modified.
- No connection was made to change the operational database; documents were not re-imported, and vectors/indexes of the old store were not recreated. The r4 ZIP and the Portable r4 folder were not modified or replaced.

## Defects that were fixed

| Problem before the review | Result after the fix | Main place |
|---|---|---|
| The sentence “text trang 17 của văn bản này” (“text of page 17 of this document”) treated “văn bản này” (“this document”) as a document title; a request to reread the image did not force vision | Recognize the context of the turn that is selected; keep a clear name/document number; pass `prefer_ai` correctly through document selection and printed-page confirmation | `frontend/src/components/pageTextIntent.ts`, `frontend/src/pages/EvidenceChat.tsx` |
| The fallback UUID was malformed when LAN HTTP has no `crypto.randomUUID`, and the API returned 422 | A shared UUID v4 helper, preferring `getRandomValues` | `frontend/src/requestId.ts`, `OcrAiPanel.tsx`, `EvidenceChat.tsx` |
| The copy button did nothing when the Clipboard API was missing, and it did not report failure | A synchronous fallback for LAN HTTP and a status message that is visible and readable by a screen reader | `PageTextPanel.tsx` |
| A PDF that finished loading after logout or a page change could still be attached to the iframe | Abort and check the request/context before creating a blob URL; revoke the old URL | `PageTextPanel.tsx` |
| An apply/ignore/cancel OCR response for an old document could be written into the new document's panel | Drop late responses by token, document, version, page and revision | `OcrAiPanel.tsx` |
| Clearing temporary data only stopped polling; some turn changes left a task and the old “reading” state | Cancel the task that already has an ID, end the waiting state, and drop the old controller's response on stop/request change/session clear | `EvidenceChat.tsx` |
| GET still returned AI text of a task past TTL; cleanup was rolled back when an error was returned | Cleanup commits separately, deletes candidate JSON/text, returns 410; the worker also cleans expired tasks while polling the queue | `backend/app/documents/page_text.py`, `ocr_ai_store.py`, `ocr_ai_jobs.py` |
| A USER could receive a result for an old revision or old page text | Compare revision, PDF SHA and page-text SHA before, during and after inference, and when returning a task that is already ready | `page_text.py`, `ocr_ai_jobs.py` |
| A second worker treated a task owned by a live worker as an orphan; temp cleanup could touch another render | A session-level advisory lock held for the whole task; recover or clean an orphan only when no worker holds the lock | `ocr_ai_jobs.py` |
| Cancel only changed the DB status; HTTP inference still waited until timeout | Check task/ACL/source while waiting and cancel the HTTP coroutine; add a 360-second whole-task budget, a lease longer than the budget; no automatic retry | `ocr_ai_jobs.py` |
| A new request still entered the queue when the worker was off | OCR AI is off by default under the chosen option; turn it on deliberately with `EVIDENCE_OCR_AI_ENABLED=true`. When off, the API returns 503 for a new image read; already approved page text is still returned directly | `config.py`, both routers and both OCR/page-text services |
| A digest taken from `/api/show` could be empty on a real Ollama | Take the digest from native `/api/tags` when needed, and normalize `sha256:` | `model_registry/adapters/ollama_local.py` |
| An old result could still be kept or applied after the profile, weights or prompt had changed | Store a fingerprint of profile + model + image before inference; compare it again after inference; check route/digest before apply and profile/prompt inside the transaction | `model_registry/runtime.py`, `profiles.py`, `ocr_ai_jobs.py`, `ocr_ai_store.py`, OCR router |
| The probe accepted only HTTP 200 / non-empty text, or a 1 px image | Check known text on a synthetic image. The probe accepts only the expected letters/digits and allows a different separator; the probe is not an OCR quality score | `diagnostics.py`, `runtime.py`, `portable.ps1`, `config/ocr-probe.png` |
| A warning/title was clipped in a narrow frame even when the page had no horizontal scrollbar | Let the header wrap, wrap status, and let the OCR grid shrink with the frame; do not hide an error by clipping | `frontend/src/styles.css` |
| The OpenAPI contract and the guides did not follow the new flow | Re-export OpenAPI; add guidance for reading one page, turning OCR on, TTL and limits; fix the account description and distinguish a template from a verified package | `docs/openapi.json`, the two repository guides and the Portable guides |
| The test script stopped every Ollama process, or any process, that held the port | Switch to an ownership profile by checkout/port, PID + executable + creation time; stop PostgreSQL only if this run recorded ownership | `ung-dung-test.ps1` — syntax verified; dynamic checks limited as noted at the end |

## Check results

| Check | Actual result |
|---|---|
| Full backend with temporary PostgreSQL/pgvector | **341 passed, 0 skipped**; 164.93 seconds on the run that also exercised the real model |
| OCR/page-text API after the off-flag compatibility check | **3 passed**, 9.03 seconds; the trial cluster was then stopped |
| Full frontend after the stop/clear-session fix | **110 passed**, 22 test files |
| Backend Ruff | Passed |
| Backend mypy strict | Passed, 103 source files |
| Frontend ESLint, TypeScript and Vite production build | Passed |
| Dependencies | `uv pip check`: 41 packages compatible |
| Migration pairs | 17 valid pairs; applied only on the trial DB |
| OpenAPI | Export and `--check` passed |
| Literal secret/path check in source | Passed; the check rule was not relaxed |
| Polarity/temporal fixtures | 4 polarity cases with no error; temporal chain A → B → C → D resolved |
| PowerShell parser | `portable.ps1`, `build-lan-portable.ps1`, `ung-dung-test.ps1` passed |
| Chrome through Playwright | Sign-in, request page 17, result/warning, copy, open the original PDF; viewports 390×844, 768×900, 1280×800 |
| Responsive layout after the fix | `documentWidth == viewport`, no status clipped at any of the three sizes; keyboard focus has an outline |

The new regressions were run while still failing and run again after the fix. The backend still has one deprecation warning from Starlette/AnyIO; no test failed. The browser used a **HƯ CẤU** (fictional) API fixture and does not represent a full-system test on a LAN workstation; the favicon 404 belongs to the fixture, not to an application JavaScript error.

## Check with the real model

Environment: Ollama **0.40.15**, `qwen3.5:4b`, local-only. A **20-page image PDF** was created containing a fictional (HƯ CẤU) administrative report; page 17 has a dossier total of `1729` and the date `16/11/2026`.

1. An ordinary request returned the already approved page text and did not call AI.
2. A request to reread the image rendered and sent only page 17. Qwen returned the sample content, the number `1729`, the date and the page number; the response recorded `ocr_ai_unverified`, `verified=false`.
3. Two measurements of the USER page-read took about **77.7 and 94.1 seconds**. That is the time on this test machine and load, not a standard benchmark or a speed commitment; the later run shared the regression suite.
4. A USER outside the scope was refused the task/PDF. A USER task cannot be applied into the store even if called from an account that has curator rights.
5. The PDF hash and all page text of the source copy stayed the same after the read. A separate ADMIN flow with the real model created a proposal and applied it as a **new draft**; the old copy stayed `approved`; no embedding was created.
6. The fingerprint was stored and checked; changing the profile revision in the temporary DB made the old snapshot be rejected.
7. The adapter produced native text, `think=false`, and JSON mode returned `{"tong":1729}` from the sample report.

| Model identity that was checked | Value |
|---|---|
| SHA-256 of the manifest file in the model store | `e0b8c85c75aad2573ff49bec177ebb1013772fba665a53d64c04266439a2222d` |
| Native `/api/tags` digest recorded by the runtime | `sha256:d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04` |
| SHA-256 of the rendered image of page 17 | `79974ca0615cc208ace92ac06136d6294a1352651cf7940bb671b103ea3645c1` |

Those two manifest digests are different identifiers: the manifest file has nested manifest layers, including the `d8b0…` layer that Ollama publishes; do not conclude that the weights changed only because the two digests differ. The historical measurements of 2026-11-16 in the earlier report were not edited.

## Limits and conditions before release

- **A new Portable ZIP has not been built, extracted, moved or run.** Reviewing scripts, the parser and assets only verifies the source. The r4 package being handed over still contains `qwen3:1.7b`; do not attribute the new source features to the r4 ZIP.
- The plan needs to keep the old model for rollback. Right now the repo's `models/ollama` and the store under `EVIDENCE_PROGRAMS_ROOT` list only `qwen3.5` and `qwen3-embedding`; `qwen3` is still in r4. Prepare enough manifests/blobs for the profiles and fallbacks that will be packaged, confirm the routes/indexes on a **copy of the database**, and only then build a new package. This review did not copy or change the model store or the operational Registry by itself.
- OCR AI is off by default. The operator must check the model, assign `ocr`, turn the flag on and restart the chosen deployment. Do not turn the flag on by itself on a system that is in operation.
- There was no further test on another Windows/GPU/RAM machine, a LAN workstation, an isolated offline ZIP, power loss, OOM/soak, or concurrent users. The summary result does not replace a business comparison on a real scanned PDF, a hard table, a seal/signature, or handwriting.
- A separator on the probe image was once misread by the model from `OCR-PROBE-17` to `OCR:PROBE-17`. The probe confirms that the model can receive an image and text; it does not guarantee OCR accuracy; keep the warning and the reviewer process.
- The dynamic test that stops a fake process or an external service of `ung-dung-test.ps1` was refused by the automatic reviewer with the message **“blocked by policy”**, with no more detailed reason. The fix passed the parser; the full start/stop of this launcher has not been confirmed dynamically. The blocked test was not repeated another way, and no extra permission was requested.
- Running `ung-dung-test.ps1 -Action status` directly was also refused by Windows because the file is unsigned under `RemoteSigned`. Execution Policy was not changed and the file's security mark was not removed; the existing BAT files already call PowerShell with the launcher's own parameters. This is not confirmation that BAT/start/stop has been run.

The trial services created during the review (temporary PostgreSQL, Ollama on its own port, the fictional (HƯ CẤU) UI server and the Playwright browser) were stopped. The pre-review source copy and the logs/images in the TEMP folder above were kept for comparison. Nothing was committed or pushed, and Git history was not rewritten.
