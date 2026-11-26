**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-11-08-user-lookup/REPORT.md`. The Vietnamese file is the original.

# Review and fix of the USER lookup function (2026-11-08)

Data: the DB `evidence_rerank_eval` (100 approved administrative documents (văn bản), 7,230
vectors of `qwen3-embedding:0.6b`), run with `ung-dung-test.ps1` (LOCAL, pure RRF, no rerank).
Administrative documents (văn bản) were not imported again, vectors were not rebuilt, and the
models, the DB, the indexes, and the backups were not deleted. The code from before the fix is
in `.agents/backup-2026-11-08-user-lookup/`.

## Failure case “Appointment and dismissal procedure in the People’s Public Security” (“Thủ tục bổ nhiệm, miễn nhiệm trong Công an nhân dân”)

Before the fix (real HTTP): 12 evidence (căn cứ) items, headed by the 4,000-character blocks of
catalogs 540/QĐ-BCA and 721/QĐ-BCA; the finding is the verbatim whole block; the same clause
(Khoản) is repeated under “nhận định” (finding) and “gợi ý” (suggestion); the label is
`paragraph`; the provision “Comrades … are responsible for implementation” (“Các đồng chí …
chịu trách nhiệm thi hành”) is selected because the only overlap is the administrative document
(văn bản) name.

The causes that were found:

| Layer | Cause |
|---|---|
| Question analysis | Keywords are loose syllables; there is no notion of a phrase; “còn” (still), “này” (this) make a new question pick up the old facts; the UI on its own sets the document number and the Article (Điều) of the first evidence (căn cứ) as facts for the next turn |
| Chat retrieval | Chat’s own channel (it is not G2); the “tên văn bản” (administrative document (văn bản) name) channel takes every clause (Khoản) of an administrative document (văn bản) whose name matches; “đủ các từ” (all the words) is computed on `text_indexed` (which also includes the administrative document (văn bản) name) |
| Ranking | `ts_rank_cd` prefers a long block that repeats common words many times (catalogs of administrative documents (văn bản)) |
| Concept expansion | An AI suggestion that has not been approved (for example “thủ tục điều động” (a transfer procedure)) counts as a match; when the exact phrase is absent, it falls back to “mọi từ ở bất kỳ đâu” (every word, anywhere) |
| Display | The finding equals the verbatim clause (Khoản); the PDF is embedded in 3 columns; the button that opens the PDF is built from Word |

## Changes

- `storage/relevance.py` (new): splits the question into phrases (punctuation, function words);
  the unit is a pair of adjacent syllables; each syllable belongs to the most frequent pair
  that contains it (a pair that straddles two words, such as “tục bổ”, is excluded); IDF
  weights are counted in PostgreSQL over the clauses (Khoản) the user is allowed to read;
  scoring is done on the text of the clause (Khoản) and on the Article (Điều) title, and the
  administrative document (văn bản) name counts as one half; words that are far apart (outside
  a window of 30 syllables) receive only 0.3. Three levels: `direct` (all of the main phrases,
  written contiguously), `related` (a rare phrase, plus further words of the question nearby),
  and `weak` (only common words, loose syllables, or only near in meaning). A listing passage
  of 4 or more document numbers is “chỉ nhắc đến” (only mentioned), and it is never direct
  evidence (căn cứ). A quotation of ≤ 520 characters is a verbatim slice of `text_original`,
  with the main phrases highlighted.
- `storage/comprehensive.py`: G2 attaches a relevance level to the first 2,000 results; it
  sorts stably by (effectivity (hiệu lực) group D9, relevance level) and keeps the RRF order
  inside each group; no result is removed. Added `mode` (exact phrase / all the words), a view
  by administrative document (văn bản) (`view=documents`), a level filter (`tier`), and all
  clauses (Khoản) of one administrative document (văn bản)
  (`GET …/{id}/documents/{document_id}`). RRF k = 60, the semantic threshold 0.8, and rerank
  off: unchanged.
- Q&A (`storage/chat_retrieval.py`, `workflow/chat_answer.py`, `fixed_pipeline.py`): a question
  that does not state a document number or an Article (Điều) runs on the G2 result set; a
  question that has a document number or an Article (Điều) keeps the old reference lookup.
  Only a `direct` or `related` clause (Khoản) becomes evidence (căn cứ); at most 8
  administrative documents (văn bản), at most 4 clauses (Khoản) per administrative document
  (văn bản), and one representative clause (Khoản) per Article (Điều) (the other clauses
  (Khoản) are marked “Cùng điều còn khớp” (Same article, still matching)); a
  scope, definition, or effectivity (hiệu lực) article, and a form, are ranked later; a clause
  (Khoản) with identical text in a consolidated administrative document (văn bản) and an
  amending (sửa đổi) administrative document (văn bản) is marked “Nội dung giống …” (Content
  identical to …). The answer is written from the metadata and the Article (Điều) title, it
  does not call a model, and it does not create a document number, a date, or effectivity
  (hiệu lực). The consolidated / amend (sửa đổi), supplement (bổ sung) type is read from the
  document number and the abstract; a relation is recorded as “đã xác minh” (verified) only
  when it has been approved (test DB: 0 approved relations). Diễn giải AI (AI interpretation)
  is a separate button, and it appears only on a relevant clause (Khoản) (`only_relevant`).
- The original file: `GET /api/v1/citations/{id}/original` checks the ACL, the version, and the
  SHA-256; a PDF (including a scan) returns the exact file that was loaded, Word and TXT return
  the original file in `sources/` according to `source_file_sha256`, and a constructed PDF is
  not returned.

> Recorded on 2026-11-08, before the two-pane UI existed (2026-11-11).

- UI: one reading column; a short answer, and a card for each administrative document (văn bản)
  (type, document number, date, issuing body, abstract, original file, effectivity (hiệu lực),
  Article (Điều)/Clause (Khoản), a quotation that can be expanded, and “Mở văn bản gốc” (Open
  the original administrative document)); a PDF opens in a separate tab at the page, and Word
  and TXT download in the correct format; facts, session memory, and the coverage check are
  moved into the “Thông tin kỹ thuật” (Technical information) area. One page, “Tìm kiếm văn
  bản” (Search administrative documents) (“Tìm toàn diện” (Comprehensive search) was removed),
  on G2: by meaning / all the words / exact phrase, with filters for catalog, type, effectivity
  (hiệu lực) date, time range, effectivity (hiệu lực) status, and verification; a partial match
  sits in its own collapsed group; an old link `?q=…&mode=phrase` still opens the search page.
  `PdfViewer`, `EvidenceCards`, and `ComprehensiveSearchPage` were removed.

## Measurements

Real HTTP, 7 questions (`chat-after.txt`, `chat-after.json`): 1.3–3.1 seconds per turn.

| Question | Result |
|---|---|
| Appointment and dismissal procedure in the People’s Public Security (Thủ tục bổ nhiệm, miễn nhiệm trong CAND) | 3 direct administrative documents (văn bản): 01/VBHN-BCA (Clause (Khoản) 4 of Article (Điều) 5, Clause (Khoản) 5 of Article (Điều) 8, Article (Điều) 6…), 77/2019/TT-BCA (Clauses (Khoản) 4 and 3 of Article (Điều) 1), 05/VBHN-BCA (Clause (Khoản) 2 of Article (Điều) 21); 2 related (777/QĐ, 14/2024); 540 and 721 are placed under “chỉ nhắc đến” (only mentioned) |
| the periodic reporting regime (chế độ báo cáo định kỳ) | 8 administrative documents (văn bản) with a provision stated directly (10/2014 Article (Điều) 18 at the top), 4 other administrative documents (văn bản) on the search page, and 2 catalogs |
| objects prohibited from being brought into a temporary holding room or a detention room (đồ vật cấm đưa vào buồng tạm giữ, tạm giam) | 58/2026/TT-BCA direct; 7 related |
| What does Article (Điều) 5 of Circular (Thông tư) 55/2021/TT-BCA provide? (Điều 5 Thông tư 55/2021/TT-BCA quy định gì?) | Only 55/2021/TT-BCA (reference lookup) |
| the code of conduct of the People’s Public Security (quy tắc ứng xử của CAND) | 27/2017/TT-BCA (PDF) at the top |
| penalties for personal income tax violations (xử phạt vi phạm thuế thu nhập cá nhân) | “Chưa tìm thấy trong kho…” (Not found in the corpus…) (the corpus has no tax administrative document (văn bản)) |

Opening the original administrative document (văn bản) through the browser (Chrome headless,
`report-*.json`): 8 different Word files and 1 PDF; the SHA-256 of the bytes received matches
`source_file_sha256` (Word) or `original_file_sha256` (PDF) in the DB; the PDF opens the tab
`blob:…#page=N`. Layout at 1024/1366/1920 px: no horizontal overflow, the longest quotation is
513 characters, and there are no console errors. Images: `chat-*.png`, `search-*.png`.

50 G5 questions (`bench-rrf-50-before.json`, `bench-rrf-50-after.json`, `bench-diff.txt`):

| | R@10 | R@20 | R@50 | R@toàn bộ (R@all) | MRR@10 | NDCG@10 | Median |
|---|---|---|---|---|---|---|---|
| Before | 0.865 | 0.892 | 0.946 | 0.960 | 0.780 | 0.589 | 2.1 s |
| After | 0.851 | 0.892 | 0.960 | 0.960 | 0.792 | 0.629 | 2.9 s |

No required evidence (căn cứ) was lost (R@toàn bộ (R@all) stays at 0.960). One intermediate
measurement gave R@10 of 0.865: the concept-expansion step (`expand`, qwen3:1.7b) produces
different results from run to run, so R@10 fluctuates by ±1 pair. Removing the “mọi từ” (every
word) fallback path of the concept channel was tried, and it lost 1 required evidence (căn cứ)
item (23/2022 Article (Điều) 5), so that path was kept.

`verify.ps1` 12/12: backend 239 passed (real PostgreSQL), frontend 57 passed, ruff/mypy/eslint
clean, and OpenAPI updated.

## Remaining limits

- The relevance-level thresholds were set by principle, and they were checked on 7 questions
  and on 50 questions drafted by the agent; a business officer has not confirmed them. A
  passage of a Plan or a Directive that mentions “báo cáo định kỳ” (periodic report) is still
  counted as “trực tiếp” (direct).
- There is no OCR-scanned PDF in the test DB, and the machine does not have Tesseract
  installed yet: the PDF branch was checked only by a test, confirming that it returns the
  loaded file in `originals/` (OCR does not create a new file). There is no TXT file in the
  test DB; the TXT branch is checked by code shared with Word.
- The desktop application (Tauri) has not been rebuilt, and opening a tab or downloading a
  file in WebView2 has not been tried; when the browser blocks a new tab, the file is
  downloaded.
- Topic grouping uses 27 phrase rules of the 11 G4 content groups; there is no grouping by
  field yet.
- The issue date and the issuing body are missing on many consolidated administrative
  documents (văn bản) in the test DB; the display is “Chưa xác định” (Not determined). A name
  taken from the file name (without diacritics) is kept as it is in the data.
- The frontend test suite went from 77 down to 57 because 36 tests of the Search v1 page and
  of the removed PdfViewer were dropped; they were replaced by 10 tests for the new page, the
  administrative document (văn bản) card, and the button that opens the original file.
