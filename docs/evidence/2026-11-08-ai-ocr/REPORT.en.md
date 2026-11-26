**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-11-08-ai-ocr/REPORT.md`. The Vietnamese file is the original.

# AI interpretation and scanned-PDF OCR (2026-11-08)

Environment: the test DB `evidence_rerank_eval` (100 approved administrative documents (văn bản)
plus 5 trial scan Decrees (Nghị định) in a separate catalog), `ung-dung-test.ps1`, LOCAL mode,
with the model taken from Model Registry (the `summarize` stage currently points at
`qwen3:1.7b` on a Ryzen 9 6900HX CPU, with no GPU). Pure RRF, rerank off, semantic threshold
0.8: unchanged. The 100 administrative documents (văn bản) were not imported again, the 7,230
vectors were not rebuilt, and the DB, the indexes, the models, and the backups were not
deleted. The backup taken before editing: code in `.agents/backup-2026-11-08-ai-ocr/`, and the
DB in `.agents/backup-2026-11-08-ai-ocr/evidence_rerank_eval.dump` (pg_dump, 38.9 MB).

## A. AI interpretation

### The failure case and its causes

“Penalties regarding blood alcohol concentration” (“Xử phạt về nồng độ cồn”) → press “Diễn giải
AI” (AI interpretation) (`ai_before.txt`, `ai_before_ev.txt`): 10 points, among them fire
prevention and fighting, betting, and enterprise dossiers, all of them “verified”. The corpus
has no clause (Khoản) that provides a penalty regarding blood alcohol concentration
(`ai_truth.txt`: 7 clauses (Khoản) mention “nồng độ cồn” (blood alcohol concentration), and 0
clauses (Khoản) contain “phạt tiền/xử phạt” (a monetary fine/a penalty)).

| Layer | Cause |
|---|---|
| Selecting evidence (căn cứ) | Every clause (Khoản) at the `direct/related` level was sent to the model. An industry-catalog clause (Khoản) (5625/QĐ) contains “nồng độ cồn” (blood alcohol concentration), so it is `direct`; there is no concept of “the issue being asked” (a penalty) |
| Grouping | Grouped by content label; a label proposed by AI and not yet approved (the breath-alcohol measuring-device clause (Khoản) was tagged “Thời hạn” (Time limit)); each turn still calls AI to assign labels |
| Prompt | The model **is not told the question**: only “summarize the evidence (căn cứ) by group X” |
| Verification | Only the evidence (căn cứ) code, the numbers, the dates, and the Article (Điều)/Clause (Khoản) are checked; an off-topic point with a valid code gets through. A wrong number is only tagged “chưa kiểm chứng” (not yet verified), and it is still displayed |
| Display | An evidence (căn cứ) code that is not in the displayed list becomes the words “căn cứ đã trích” (evidence already quoted); “Diễn giải tiếp” (Continue the interpretation) repeats every old point; the suggestions are meaningless |

### Changes

- `synthesis/focus.py` (new): splits the question into the **issue asked** (a table of 12
  types: penalty level, penalty, prohibited act, authority, time limit, condition, effectivity
  (hiệu lực), procedure, dossier, subject, concept, and right/obligation; each type has phrases
  used to ask about it and phrases that show a clause (Khoản) provides it) and the **content**
  (the remaining phrases of the sentence, according to `relevance.py`). The table is a typology
  of legal content; it contains no question, no document number, and no administrative document
  (văn bản). A “strict” type (penalty level, penalty, time limit, authority, condition,
  effectivity (hiệu lực), prohibited act): if no clause (Khoản) provides it, do not infer it.
- `synthesis/focused.py` (new), `service.py` (`only_relevant`): from the G2 result set, each
  clause (Khoản) is classed as `primary` (enough content, taking into account the scope written
  in the abstract, and the correct issue asked), `partial` (only part of the content, used only
  when there is no `primary`, and carrying a note), `other_aspect` (the same content, a
  different issue; listed only), `off_topic`, or `mentioned` (a catalog). A `primary` clause
  (Khoản) is built into an administrative document (văn bản) card by `chat_answer.compose` (one
  representative clause (Khoản) per Article (Điều); a clause (Khoản) whose text is identical in
  a consolidated administrative document (văn bản) and an amending (sửa đổi) administrative
  document (văn bản) is sent only once). The model receives the question, the issue asked, the
  content, each evidence (căn cứ) item (type plus document number, abstract, Article
  (Điều)/Clause (Khoản) plus the Article (Điều) title, and effectivity (hiệu lực) only when it
  has been verified), and the points already stated. Each turn takes 4 clauses (Khoản);
  “Diễn giải tiếp” (Continue the interpretation) takes only the administrative documents (văn
  bản) that have not been processed yet. When there is no `primary` for a “strict” issue, the
  answer is “Chưa tìm thấy…” (Not found yet…), and **the model is not called**. This mode does
  not assign AI labels.
- `synthesis/checks.py` `verify_claim`: the check layers are (1) the evidence (căn cứ) code,
  (2) numbers, dates, the document number, and Article (Điều)/Clause (Khoản)/Point (Điểm) must
  be present in the evidence (căn cứ) — **a mismatch is dropped**, and there is no longer
  “chưa kiểm chứng” (not yet verified), (3) a business conclusion (unless it only repeats the
  wording of the evidence (căn cứ), such as “quyết định xử phạt” (a penalty decision)), (4) a
  passage in quotation marks must be verbatim, (5) the lexical support level of the evidence
  (căn cứ) that is cited (< 0.35 is dropped, < 0.55 is “cần đối chiếu” (needs cross-checking)),
  (6) on the topic of the question, (7) a point that states a “strict” issue (a penalty, a time
  limit…) needs a clause (Khoản) that provides that issue, (8) a negation reversed in meaning
  (dropped), a negation, exception, or condition that was dropped, and “phải” (must) ↔ “có thể”
  (may) (needs cross-checking), (9) effectivity (hiệu lực) is stated only when it has been
  verified or the evidence (căn cứ) itself states it, (10) a duplicate point (the figures are
  compared), (11) a long verbatim copy. A point that is kept says only “đã đối chiếu với căn
  cứ” (cross-checked against the evidence (căn cứ)), and does not say “đúng” (correct). When
  every point is dropped, the model is asked once more, with the reasons for dropping.
  `clean_text`: NFC, strip markdown and the code `e1`, and “Căn cứ: ,,” (Evidence (căn cứ): ,,),
  and capitalize the start of the sentence; verbatim quotations are left untouched (they are
  taken from the DB).
- Q&A (`chat_answer._answer`): a “strict” issue for which no clause (Khoản) provides a rule →
  the summary “Chưa tìm thấy điều khoản quy định … về …; các văn bản này không dùng để suy ra
  …” (No provision was found that regulates … regarding …; these administrative documents (văn
  bản) are not to be used to infer …).
- The UI `AiAnswerView.tsx` (shared by Q&A and the Search page): the main answer → the points,
  with citation numbers [n] that lead to the clause (Khoản) → the part that lacks evidence
  (căn cứ) → the note, once → “Diễn giải tiếp” (Continue the interpretation) → “Căn cứ hỗ trợ”
  (Supporting evidence) (only a clause (Khoản) that some point cites): type, document number,
  date, abstract, Article (Điều)/Clause (Khoản) plus the Article (Điều) title, a short
  quotation of ≤ 320 characters, effectivity (hiệu lực) as “(đã xác minh)” (verified) or
  “Chưa xác minh trong kho” (Not verified in the corpus), and the button “Mở văn bản gốc” (Open
  the original administrative document); administrative documents (văn bản) with the same
  content and a different issue sit in a collapsed section; “Thông tin kiểm tra” (Check
  information) (the number of clauses (Khoản) dropped, and the points that were dropped,
  with the reasons).
- Independent of the model: it calls `runtime.generate("summarize", …)` through Model Registry
  (Local/API, egress, a timeout of ≤ 30 s per turn, tokens, a cost ceiling, and Hybrid Auto
  left as it is). There is no model name in the code. If the model fails → “Chưa diễn giải được
  bằng AI lúc này” (AI cannot produce an interpretation right now), and the evidence (căn cứ)
  is still displayed.

### Real HTTP results (`ai_after4.txt`, `ai_after5.txt`, `ocr_ai.txt`)

| Question | AI interpretation |
|---|---|
| Penalties regarding blood alcohol concentration (Xử phạt về nồng độ cồn) | “No provision was found in the corpus that regulates a penalty regarding ‘nồng độ cồn’ (blood alcohol concentration)” (“Chưa tìm thấy trong kho điều khoản quy định xử phạt về ‘nồng độ cồn’”); 5 administrative documents (văn bản) that mention blood alcohol concentration in other content (an on-site inspection, a measuring device…) are listed separately; 0 model calls, 0.1 s. Q&A also says “Chưa tìm thấy…” (Not found yet…) |
| The penalty level for not wearing a helmet (Mức phạt khi không đội mũ bảo hiểm) | “Chưa tìm thấy…” (Not found yet…), and 2 administrative documents (văn bản) that mention a helmet in other content |
| The procedure for appointment and dismissal in the People’s Public Security (Thủ tục bổ nhiệm, miễn nhiệm trong CAND) | 01/VBHN-BCA and 77/2019/TT-BCA; 5 points cross-checked (a dossier in 02 sets, the provincial-level Public Security takes the lead together with the Department of Justice…); 3 points dropped because they state an Article (Điều) or a number that is not in the evidence (căn cứ); 42 s |
| The periodic reporting regime (Chế độ báo cáo định kỳ) | 10/2014/TT-BCA (the 20th of every month, May 25 (25/5), November 25 (25/11)), 04/CT-BCA, 05/2015/TT-BCA; a point that assigns the content of 04/CT-BCA to 10/2014 or to 117/2021 was dropped; “Diễn giải tiếp” (Continue the interpretation) adds 05/2015 and does not repeat points |
| Effectivity of application (hiệu lực thi hành) of the Circular (Thông tư) on the code of conduct of the People’s Public Security (Hiệu lực thi hành của Thông tư quy tắc ứng xử CAND) | “27/2017/TT-BCA has effectivity of application (hiệu lực thi hành) from 2017-10-06, replacing (thay thế) Decision 893/2008/QĐ-BCA of 2008-07-04” [Article (Điều) 15] (“27/2017/TT-BCA có hiệu lực thi hành kể từ 06/10/2017, thay thế QĐ 893/2008/QĐ-BCA ngày 04/7/2008”). On another turn the model copied the year wrong (2017-07-04, written 04/7/2017): it was dropped and is not displayed |
| Objects prohibited from being brought into a temporary holding room or a detention room (Đồ vật cấm đưa vào buồng tạm giữ, tạm giam) | 58/2026/TT-BCA, 3 points |
| Penalties for personal-income-tax violations (outside the corpus) (Xử phạt vi phạm thuế TNCN (ngoài kho)) | “Không tìm thấy căn cứ…” (No evidence (căn cứ) found…), and the model is not called |
| OCR: the time limit for carrying out a remedial measure in the field of statistics (Thời hạn thi hành biện pháp khắc phục hậu quả trong lĩnh vực thống kê) | 362/2026/NĐ-CP (scan): 30 working days from the date the decision is received… |
| OCR: the public-duty allowance for officials and public servants at commune level (Phụ cấp công vụ đối với cán bộ, công chức ở xã) | 381/2026/NĐ-CP (scan): 55% of the salary currently received, plus the position allowance… Before selection was tightened, 350/2026 (the medical allowance) was included; after the content was required to be complete, it is no longer included |

Chrome headless at 1024/1366/1920 (`ai-report-*.json`, `ai-*.png`): no horizontal overflow, no
console errors, and every [n] points at a clause (Khoản) that really exists; one
liability-disclaimer sentence. Opening the original file from “Căn cứ hỗ trợ” (Supporting
evidence): Word for 01/VBHN-BCA and 77/2019/TT-BCA downloads the correct `source_file_sha256`;
scanned PDF 362/2026 opens the tab `#page=6`, and the SHA-256 equals the scan.

## B. Scanned-PDF OCR

- Runtime: Tesseract 5.5.0 (`vie`, `eng`, `osd`; Apache-2.0) was already on the machine, under
  Program Files; a copy is placed under the program root
  `E:\Programs\EvidenceRAG\tools\tesseract\5.5.0` (190 MB) under the HOSO rule (do not use
  PATH/Program Files). It runs offline. `ung-dung-test.ps1` picks up the copy under
  `tools\tesseract\` on its own; the portable package uses `runtime\tesseract\` if an
  administrator places it there, or `EVIDENCE_OCR_EXECUTABLE` in `evidence.env` (off by
  default, which matches “OCR là plugin ngoại lệ” (OCR is an exception plugin)).
- `documents/ocr.py`: it reads through TSV so each word has a confidence; a page that reads
  poorly is asked for its orientation (`--psm 0`) and is read again after rotation; page
  diagnostics cover the word count, the average confidence, the share of words below 60, the
  weakest words, tokens that cannot be Vietnamese (`B6`, `1Š`, `bd`, `ø`, `§`, `⁄QH15`,
  `UBTVQHI5`), Point (Điểm) markers read wrong (“l)” → “1)”), ink and characters (content left
  out), and rotation. The text is not corrected.
- Storage: migration `0015` (`source_pages.ocr_diagnostics`, `reviewed_by`, `reviewed_at`). An
  OCR page is always `needs_review`; the job is high-risk when a flag is set. A declared
  document number that is not found in the OCR text of the first 2 pages makes the job
  `document_number_not_in_ocr_text`.
- Review: the reviewer confirms **each page** (the UI shows the OCR text, the flags, the words
  suspected of being wrong, and a button to view the correct scan page); only then does the
  page become `usable`, and only then can the page’s clauses (Khoản) enter search and citation.
  “Phê duyệt và đóng mọi tác vụ” (Approve and close every job) does not close a page job. A
  page with no text (a signature page) passes only when it is confirmed on its own. Each
  confirmation writes an audit record `document.confirm_page_text`.
- Parser: a wrapped line “Article (Điều) 3 of this Decree (Nghị định), …” (“Điều 3 của Nghị
  định này, …”) is no longer split off as a new Article (Điều) (on the real OCR text of
  362/2026: 6 → 4 Articles (Điều), matching the original, `ocr_reparse.txt`).
- Citation: a clause (Khoản) from an OCR page carries the `ocr` flag; the UI writes “Trích từ
  bản scan qua OCR đã duyệt; vị trí chỉ xác định đến trang” (Quoted from an approved scan
  through OCR; the position is determined only down to the page). There is no highlight inside
  the PDF (OCR has no character coordinates).

### Tests with real scans (HTTP, `ocr_state.json`, `ocr_original.json`)

5 public scan Decrees (Nghị định) (362, 381, 350, 390, and 356/2026/NĐ-CP; 28 pages, with no
text layer) were loaded through the curator API: 3.8–11.1 s per file; average confidence
94.1–96.2%. A separate catalog, “Thử nghiệm OCR” (OCR trial), is readable only by the trial
account `ocr_tester`; `chuyenvien` (the benchmark account) does not see it.

| Check | Result |
|---|---|
| The SHA-256 of the file stored in `originals/` equals the SHA-256 in the source manifest | 5/5 |
| `/original` returns `application/pdf`, the correct SHA-256 of the scan, and the full page count | 8/8 clause (Khoản) checks |
| The page that is quoted (OCR run again, independently, from the bytes that were received) contains the words of the quotation | 8/8, 100% of the words |
| A person who does not have the catalog: `/original` | 404 (8/8); search does not return the OCR administrative documents (văn bản) |
| Embedding | only 160 + 57 new clauses (Khoản) (catch-up); the old 7,230 vectors are kept unchanged; the total is 7,447 |
| Effectivity (hiệu lực) relations produced | 30 `draft` proposals, 0 of them pointing at an administrative document (văn bản) in the corpus |
| Rotation by 90°/180° (`ocr_rotate.json`) | it rotates back on its own, and the text matches the upright copy; a blank page → `NO_TEXT` |

## Tests and regression

- `verify.ps1` 12/12: backend 257 passed (18 added: `test_ai_interpretation.py` and
  `test_ocr_review.py`, with PostgreSQL), frontend 60 passed (3 added). OpenAPI was updated.
- 50 G5 questions (`ul_bench_ai_ocr.json`, compared with the last run of the previous round):
  R@10 0.851 (=), R@20 0.905 (0.892), R@50 0.960 (=), R@toàn bộ (R@all) 0.960 (=), MRR@10
  0.781 (0.792), NDCG@10 0.613 (0.629), median 3.1 s. The retrieval code is unchanged; 10
  pairs changed rank by ±1–16, all of them on the concept channel (the model’s `expand`
  produces different results from run to run, `ul_bench_ai_ocr_diff.txt`).

## Remaining limits

- Verification is a set of word-level rules: it catches an off-topic point, an invented
  number, date, or Article (Điều), a reversed negation, and an inference of a different issue;
  **it cannot prove** that an interpretation sentence is correct in legal meaning. For example,
  the point “Circular (Thông tư) 33/2014 provides the authority to… issue an assessor card”
  (“Thông tư 33/2014 quy định thẩm quyền… cấp thẻ giám định viên”) is kept because it matches
  the wording of the evidence (căn cứ), even though the focus is slightly off. A point marked
  “cần đối chiếu” (needs cross-checking) is still displayed, together with the reason.
- A small model on CPU: 7–50 s per click; on some turns every point is dropped (in that case
  only the evidence (căn cứ) is shown). The model’s results change from run to run. An
  external API has not been tried, and a larger model has not been tried.
- The issue-asked table was drafted by the agent, and no business officer has approved it; a
  way of asking that is not in the table is interpreted by content, and not by issue.
- A question that carries a document number or an Article (Điều) (a reference lookup) has no
  “Diễn giải AI” (AI interpretation) button (there is no G2 result set).
- OCR: a number that was read wrong cannot be detected when it is still a valid number
  (362/2026, page 1, reads “25/2016” instead of “95/2016” in the abstract line); tables,
  handwriting, and red seals do not yet have a trial sample; a multi-column page covers only
  the opening of a 2-column administrative document (văn bản) (it is read line by line). The
  default extraction time limit is 120 s for the whole file (~1.3–2.7 s/page): a file of more
  than about 60 pages needs `EVIDENCE_PDF_TIMEOUT_SECONDS` raised (the maximum is 600).
- The first three administrative documents (văn bản) loaded (362, 381, 350) use the old
  parser: 362 still has 2 fake “Điều 3 …”, and the clauses (Khoản) in the amending (sửa đổi)
  extract are labeled under Article (Điều) 1 (a general limit of an amending (sửa đổi)
  administrative document (văn bản), which is also present in a text PDF). This can be fixed
  only by deleting and loading again; that has not been done, because it is a data-deletion
  operation.
- OCR page confirmation in the trial was carried out by the agent, using a trial reviewer
  account, comparing layout and headings, and **not checking every character**; these
  administrative documents (văn bản) are only in the trial catalog, they are not yet verified
  for business use, and they are not part of Gold. OCR text that is still wrong (“bồ sung”,
  “ké từ”) is kept exactly as the machine read it.
- There is not yet a function for the reviewer to edit OCR text (only to confirm, or to
  reject and load again).
- The Tauri/WebView2 desktop application has not been rebuilt and has not been tried; the
  results above are from Chrome headless.
- TXT: the test DB has no TXT file; nothing further was tried.
