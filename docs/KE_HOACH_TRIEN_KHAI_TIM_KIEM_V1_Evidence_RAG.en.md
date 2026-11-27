**Language / Ngôn ngữ:** [Tiếng Việt](KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md) · English

English counterpart of `docs/KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md`. The Vietnamese file is the original.

# IMPLEMENTATION PLAN — Administrative-document (văn bản) search (Search v1)

> **[Not implemented — see ADR-010]** Every passage in this document about the Gold question set, trap set, calibration and held-out is not implemented, per [ADR-010](architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md). The rest remains unchanged.

System: Vietnamese Evidence RAG Agent · Document version 1.0 · 2026-10-31
Recipient: the implementing AI (the source and `SRS_v1.3.md` are already in the repo)
Status: **the owner has locked the direction** (section 1). This document replaces the previous options paper; every difference is recorded in section 2.

---

## 0. How to use this document

1. This is the **revised** version of option A (Search v1 on PostgreSQL). Follow this document, and on the points stated in section 2 do not follow the old options paper.
2. The document describes the source as it stood in the previous options paper (file names, line numbers). **The first task (SR-0) is to check it again against the real source**; where something does not match, report it and write an ADR, and do not follow memory.
3. Working rules:
   - Work on your own, and ask little. For a point that is not yet locked: use the default in section 11, write an ADR, and continue. Stop and wait for a person only in four groups: **business rules, access rights, security, and correctness of evidence (căn cứ)**.
   - **Strict backward compatibility:** do not break an existing interface; a new parameter defaults to keeping the old behavior; chat keeps its current behavior (12 evidence items, claims, SSE).
   - A WP is finished only when: code + migration + green tests + updated documentation + a report in the template in section 12. Report honestly what is not finished.
   - Do not claim a figure that has not been measured ("p95 300 ms", "correct/complete"). Every number records the environment, the version and the data.
   - Do not invent a legal administrative document (văn bản). A fixture carries the label "HƯ CẤU" (FICTIONAL). Quality evaluation uses only a real administrative document that has been approved.
   - Do not approve a document yourself, and do not certify a sample answer yourself. Those two tasks are done by a person with authority.

---

## 1. Decisions that have been locked

| # | Topic | Decision |
|---|---|---|
| 1 | Option | **A:** Search v1 on PostgreSQL. Option B (semantic: a Vietnamese tokenizer + embedding + RRF + pre-gate + rerank) is done **later**, once a model runs locally and Gold [Not implemented — see ADR-010] has been approved. Option C (Elasticsearch/OpenSearch/Meilisearch/ParadeDB) is **rejected**: it would duplicate the ACL, add operations, and conflict with the decision "PostgreSQL is the only DB" |
| 2 | Form | **Integrated into the existing app as a separate module**, not a standalone app. Search is a separate page in the User Portal; the Chat Agent has a button "Xem tất cả kết quả tìm kiếm" (View all search results). Chat keeps its current behavior |
| 3 | Phrase mode | The default is **auto-detect**: if the user wraps double quotes, it is an exact phrase; there is a checkbox "Tìm chính xác cụm từ" (Search for the exact phrase) for a person who is not used to quotes |
| 4 | Sharing | Chat and the search page use **one** `SearchService`; moving up to option B only plugs in another channel, and does not change the API or the interface |
| 5 | Operating system and mode | Windows; it runs entirely in **Local Mode** (no external service, and no download of an external resource); Search v1 does not use an AI model |
| 6 | Data | The current number of approved administrative documents (văn bản), and the time milestone that is wanted: **the owner will provide them** (section 10). Approving an administrative document is done by the reviewer or by the person who holds the business knowledge; the AI must not approve one itself |

**Why integrate, and not split the app:** the ACL, login, audit log, PDF viewer, citation API and effectivity (hiệu lực) snapshot are shared; one installer, one service, one database and one backup on Windows; the system runs on an internal network, so it does not yet need its own scale-out. Consider a split only when search serves a different user group or network zone, needs an independent release, or later moves to an external search engine. So that a split is not painful: keep the module clean (`SearchService`, the prefix `/api/v1/search`, a separate page, and do not mix it into the chat code).

---

## 2. Points revised relative to the previous option

| # | Revision | Reason and requirement |
|---|---|---|
| 1 | **Effectivity (hiệu lực) is computed per clause** | `amendment_state` is set on **each clause**, not at administrative-document (văn bản) level; a clause that is unclear shows "Hiệu lực chưa xác minh" (Effectivity not verified); a stale effectivity snapshot carries a warning |
| 2 | **An empty page does not reveal that something exists** | `KHO_CHUA_CO_VAN_BAN_DUYET` is computed on **the set of documents the user is allowed to see**, and the message is "Chưa tìm thấy tài liệu được phép truy cập" (No document the user is allowed to access was found) |
| 3 | **Normalize Vietnamese tone marks** | The accented channel runs on text that has been normalized to NFC + tone marks (hòa/hoà), both at index time and at query time, **with the same function**. The unaccented channel only raises recall, has its own `match_type`, and **never** receives `exact_phrase` |
| 4 | **Separate the "partial" results** | `any_term` results are gathered into a collapsed "Kết quả gần đúng" (Approximate results) section, and are not mixed with a phrase match or an all-words match |
| 5 | **Keep `pg_trgm` only when measurement shows it is needed** | `phraseto_tsquery` already keeps word position. Add a trigram index only if the benchmark shows it is needed; check that the offline-packaged Windows PostgreSQL already includes the contrib module; LIKE must escape `%` and `_` |
| 6 | **OCR is an exception, and it is not on by default** | An ADR is required (engine, license, size within the 10 GB ceiling, offline execution). Text from OCR becomes evidence (căn cứ) only after a reviewer approves it and attaches `extraction_method=ocr` |
| 7 | **Safe queries** | Do not hand-concatenate a tsquery string from the user's input; use parameterized `plainto_tsquery`/`phraseto_tsquery`; limit the length, the word count, the runtime and the rate |
| 8 | **Verify the phrase on the content, not on `text_indexed`** | `text_indexed` contains the breadcrumb + the title + the document number; a phrase can "match" across the boundary between the breadcrumb and the content. The verification step must run on the node's content field |
| 9 | **A citation record is created lazily** | Do not create an `evidence_id` for every result on every search (the data would bloat). A result carries `node_id` + span; the citation record is created when the user opens the PDF, and at that moment the ACL and the hash must be checked again |
| 10 | **The log does not store the raw query text** | Audit records a hash of the query, the length, the filters and the result count; the raw text is stored only if the owner locks a separate privacy policy |
| 11 | **The performance target is a target to be measured** | p95 ≤ 300 ms is a target that must be measured on the target Windows machine, and it is not yet a commitment; the person-day estimate is also only rough |

---

## 3. Scope

**In scope for Search v1 (P0)**

- Keyword and phrase search over the store of approved administrative documents (văn bản); filter by category, administrative-document type, issuing body and application date.
- Results are grouped by administrative document; each administrative document shows the matching clauses together with a verbatim quotation, a marked snippet, the PDF page, and the effectivity (hiệu lực) status **of the clause**.
- Full pagination, and an exact total; empty states are clearly distinguished.
- Recognize that a query is an administrative-document number (for example `385/2026/NĐ-CP`) and place that administrative document first, reusing the Legal Reference Router if it is already in the source.
- Open the source PDF at the correct page through the existing viewer and citation API (unchanged).
- Share `SearchService` with chat without changing chat behavior.

**Out of scope (done separately, and not bundled)**

- Highlighting a position in the PDF (PDF.js text layer + bbox/quads) — a separate WP.
- Search by meaning, or by a different wording (option B).
- Suggestions while typing (typeahead), saved queries, search history, and export of results (P1).
- Writing a search query into the Chat Agent's AI memory.

---

## 4. Current state (as previously described — must be checked again in SR-0)

- There is only one lexical channel, `to_tsvector('simple')`; a question is split into a bag of keywords, AND of all of them, then a fallback OR of each word; there is no phrase or adjacency (`authorized_search.py`, around lines 193–231).
- `tsvector` is computed again for each row in the query, and the index is not used; the table `lexical_search_index` + GIN already exists in the migration, but no piece of code uses it (`0001_core.sql`).
- A ceiling of 12 nodes per turn, no pagination, and no grouping by administrative document (văn bản) (`fixed_pipeline.py`, around lines 127–135).
- Only an `approved` node with `verified` provenance is searched. As described, the DB currently has **0 approved nodes**, so every query returns empty.
- There is no search API yet; there is no Gold [Not implemented — see ADR-010] and no metric that measures recall/precision ([`history/eval-gold-protocol.md`](history/eval-gold-protocol.md)).
- `text_indexed` already contains the breadcrumb + the title + the document number + the label + the content (`draft.py`); `text_folded` and `text_normalized` are produced at ingest.
- `official_url` is already stored in `document_versions`, but it is not exposed in any API or UI.
- SRS v1.3 defines a baseline of 3 channels, `L1_WORD` + `L2_SYLLABLE` + `DENSE`, RRF, pre-gate and rerank of the top 12 (`SRS_v1.3.md`, around lines 279–303); the current source only implements a very rough part of the lexical channel.

---

## 5. Technical design

### 5.1 Normalization and the index (migration `0006_search_index.sql` + `.down.sql`)

**Normalization (a single function, shared by the index and the query)**

1. Unicode NFC.
2. Tone-mark normalization by a versioned mapping table (`hòa/hoà`, `thúy/thuý`…), checked in both directions, and record `normalization_revision`.
3. Lowercase; collapse whitespace; punctuation is treated as a separator character.
4. Unaccented channel: an extra step that strips marks (`đ → d` is handled separately).
5. The original `text_original` is **never modified**. The normalization function also returns an **offset map** from the normalized text back to `text_original`, so that a highlight can be computed.

If the mapping changes (a change of `normalization_revision`), the old index no longer matches: there must be a reindex job, or a revision check at startup that reports clearly. Do not assume that "a reindex will never be needed".

**Proposed index** (confirm it with `EXPLAIN` in SR-1; the index expression may be replaced by a generated `tsvector` column if the planner does not use the index, or in order to avoid computing it again; write an ADR):

```sql
-- kênh có dấu (chính xác)
CREATE INDEX document_nodes_search_word_gin
  ON document_nodes
  USING GIN (to_tsvector('simple'::regconfig, text_indexed));

-- kênh không dấu (recall bổ sung, trọng số thấp)
CREATE INDEX document_nodes_search_folded_gin
  ON document_nodes
  USING GIN (to_tsvector('simple'::regconfig, text_folded));
```

- `'simple'::regconfig` must be used explicitly (it is immutable), and the query must use **exactly the same expression**, or the index will not be used.
- **A trigram index (`pg_trgm`) is added only when a benchmark proves it is needed** (for example, phrase verification is slow). If it is added: check that the contrib module is present in the offline-packaged Windows PostgreSQL; record the index size and the write cost; escape `%`, `_` and `\` when LIKE is used.
- The migration has `.down.sql` and an up/down test; do not change the structure of an existing table.

### 5.2 The query

**Query analysis (in the application, not in SQL):**

- Limit the length (default 500 characters) and the word count (default 20); past that, return an error with a clear message.
- Recognize double quotes "…" ⇒ a phrase; there may be several phrases together with loose keywords (P1: if it is complicated, support only one phrase + keywords).
- Recognize an administrative-document (văn bản) number by rules; a unique match that is approved and passes the ACL places that administrative document first.
- Do not interpret an operator (`-`, `|`, `&`, `:*`, `<->`, a single quote…) from the user's input; treat them as separator characters.

**Match tiers (ranked from high to low, and not mixed):**

| Tier | `match_type` | Condition |
|---|---|---|
| T1 | `exact_phrase` | The **accented** phrase (already normalized) occurs in the node content; it has been verified on the content field |
| T2 | `phrase_folded` | The phrase matches on the unaccented channel, but it does not match with accents |
| T3 | `all_terms` | Every word of the query is present, and the words do not have to be adjacent |
| T4 | `any_term` | Only some of the words are present — **shown only in the collapsed "Kết quả gần đúng" (Approximate results) section** |

- Use `phraseto_tsquery('simple'::regconfig, $1)` for a phrase, `plainto_tsquery(...)` for all of the words, and join them with the tsquery operator `||` (OR) when the `any_term` tier is needed. Do not concatenate a tsquery string from the input.
- `phraseto_tsquery` only guarantees that the source words are adjacent; **a verbatim verification step is required** before `exact_phrase` is attached: compare the normalized string (whitespace collapsed, punctuation turned into whitespace) on **the node's content field**, not on `text_indexed`. The T1/T2 label is attached only when verification passes.
- Never attach the label "khớp cụm từ" (phrase match) to a bag-of-words result.

**Scope and permission (SQL, before the search):**

- Take the permitted node set from `authorized_nodes` (set `app.user_id` with `SET LOCAL` inside the transaction), then filter with a semi-join (`n.id IN (SELECT id FROM authorized_nodes)`) so that GIN is still used. A view that has `UNION DISTINCT` easily makes the planner drop the index: **`EXPLAIN` must be checked**. If it does not hold, try the alternatives: compute the permitted `document_id` set in advance (it is small) and then filter; a `MATERIALIZED` CTE; write an ADR together with the measurements.
- The conditions that are always present: the node is `approved`, provenance is `verified`, and the span and page match (keep the current citation conditions exactly).
- Filters: `category_ids` (ACL + scope), `doc_type`, `issuing_body`, `as_of_date`.
- Choose the **version** by `as_of_date` (the approved version that is in effect on that date; if there is no `as_of_date`, the latest approved version), so that several versions are not duplicated.

**Ranking:** within each tier, `ts_rank_cd` plus a score increase when the document number or the title matches. The two channels (accented and unaccented) are merged by simple RRF, or by adding a low-weight score for the unaccented channel; **do not** use the RRF or ts_rank score as an absolute threshold that decides "whether there is a result". The unaccented channel must not promote a result into tier T1.

**Grouping by administrative document, and pagination:**

- Group by `document_id` (after the version has been chosen); each administrative document returns at most N matching clauses (default 5, and it can be configured), with a see-more button.
- Paginate by **administrative document**; `total_documents` and `total_clauses` are exact (counted after grouping, not before). `page_size` is at most 50; there is a depth limit (`page × page_size` ≤ the configured limit, default 1000), and a message is returned when it is exceeded.
- The ceiling of 12 for chat stays; the search page does not use the ceiling of 12.

**Effectivity (hiệu lực) of the clause:** for each clause, return `amendment_state` according to `as_of_date`, taken from the effectivity snapshot (`active`, `modified`, `repealed`, `suspended`, `not_yet_effective`, `unknown`), together with `effectivity_snapshot_status` (`ok` or `stale`). The default is **to show a clause that has been amended (sửa đổi) or repealed (bãi bỏ), together with a label** (the user may be looking for that very provision); there is a filter switch "Chỉ hiện quy định đang áp dụng" (Show only provisions currently in force) (off by default). A stale snapshot returns a warning; do not use an old snapshot to assert effectivity.

**Query safety and performance:**

- Parameterize every query; a separate `statement_timeout` for search; a rate limit per user; there is no path by which the user's input becomes SQL or a tsquery operator.
- A LIKE string (if LIKE is used) must be escaped.
- Do not reveal information outside the user's permission through: the total, pagination, the empty state, an error message, an unusual response time, or a suggestion "bạn muốn tìm…" ("you may have meant…").

### 5.3 Citations and highlight

- Each matching clause returns: `node_id`, `document_version_id`, `label`, `page`, `quote_exact` (verbatim from `text_original`), `snippet`, `highlights` (offsets on `text_original`), `match_type`, `amendment_state`.
- **Highlight:** computed on `text_original` by way of the offset map. If the offset is not certain (the normalization cannot be reversed), then **do not highlight**, and show a snippet with no mark. Never highlight in the wrong place.
- **The citation record is created lazily:** when the user presses "Mở trang PDF nguồn" (Open the source PDF page), call the existing citation API to create or fetch `evidence_id` and `viewer_url`; at that moment check the ACL and the hash as is done today. If the source requires an `evidence_id` immediately inside the result, write an ADR about how to avoid bloating the table (for example an ID determined by the node and the version, without writing a new record).
- Also return `official_url` (if the curator has verified it) for each administrative document (văn bản).

### 5.4 Sharing with chat

Refactor `PostgresAuthorizedNodeSearch` into a `SearchService` with two methods:

- `search_clauses(...)` — `limit=12`, used by the chat pipeline; **keep the current behavior**; add phrase mode only when the user wraps double quotes.
- `search_documents(...)` — `page`/`page_size`, grouped by administrative document (văn bản), used by the search page.

**Required:** before the refactor, write a **characterization test** (golden test) for the current chat results (the same input ⇒ the same 12 evidence items (căn cứ), claims and SSE). The refactor is finished only when these tests are still green.

Design option B so that it is "plug in another channel": a channel interface (`LexicalChannel`, and later `DenseChannel`), a result-merge function that stands on its own, and no change to the API or the UI when a channel is added.

---

## 6. API

```http
GET /api/v1/search?q=báo+cáo+định+kỳ+và+thường+xuyên
    &mode=auto|phrase|keywords
    &category_id=...&doc_type=decree&issuing_body=...&as_of_date=2026-10-31
    &only_active=false&group_by=document&page=1&page_size=20
```

Example response:

```json
{
  "query": {"original": "…", "phrase": "báo cáo định kỳ và thường xuyên", "mode": "phrase", "normalization_revision": "…"},
  "phrase_found": true,
  "totals": {"documents": 3, "clauses": 5, "approximate_matches_hidden": 7},
  "page": 1, "page_size": 20, "has_more": false,
  "effectivity_snapshot_status": "ok",
  "results": [{
    "document_id": "…", "document_version_id": "…",
    "document_number": "385/2026/NĐ-CP", "title": "…", "doc_type": "decree",
    "issuing_body": "…", "official_url": "https://…",
    "matched_clause_count": 2,
    "clauses": [{
      "node_id": "…", "label": "Khoản 1 Điều 5", "page": 12,
      "match_type": "exact_phrase",
      "amendment_state": "active", "amendment_as_of": "2026-10-31",
      "quote_exact": "…", "snippet": "…",
      "highlights": [{"start": 10, "end": 44}]
    }]
  }],
  "approximate": {"collapsed": true, "total_clauses": 7},
  "empty_reason": null
}
```

- `empty_reason`: `NO_AUTHORIZED_DOCUMENTS` · `NO_RESULTS` · `PHRASE_NOT_FOUND` (it may be accompanied by `all_terms` results).
- An "approximate" result (`any_term`) is fetched by a separate parameter or by a child endpoint (`/search/approximate`), so that it loads on demand, and it is not mixed into the main results page.
- Standard errors: `QUERY_TOO_LONG`, `TOO_MANY_TERMS`, `PAGE_TOO_DEEP`, `RATE_LIMITED`, `SEARCH_TIMEOUT`. A message does not reveal information outside the user's permission.
- A clause whose `amendment_state` is other than `active` is always returned with a label; a clause is not dropped from the results only because of effectivity (hiệu lực) (unless `only_active=true`).
- Opening a PDF: use the existing citation API and `viewer_url` unchanged.
- Code: a new schema in `schemas.py`; a new route in `user.py` (following the `require_user`/`get_pipeline` pattern); a new service `backend/app/storage/search.py`; run `export_openapi.py` again to update `openapi.json`.

---

## 7. UX/UI design of the Search page

Follow the existing design system (Modern Enterprise / Evidence-First; Light; Navy + Blue + White + Slate; color through CSS variables, and a hardcoded HEX is forbidden; color is not the only signal).

### 7.1 Placement and navigation

- An item **"Tìm kiếm văn bản"** (Administrative-document (văn bản) search) on the User Portal navigation bar, next to "Hỏi đáp" (Q&A); a separate path; the query state lives in the URL query string, so that going back or refreshing does not lose the results.
- Chat Agent: after each answer there is a button **"Xem tất cả kết quả tìm kiếm"** (View all search results) that opens this page with the corresponding query; chat behavior does not change.

### 7.2 Layout

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ [Hỏi đáp] [Tìm kiếm văn bản]  …            [Danh mục ▼]  [API/Local Mode]  │ Navy
├────────────────────────────────────────────────────────────────────────────┤
│ Tìm kiếm văn bản                                                           │
│ ┌ Tìm theo từ khóa, cụm từ hoặc số hiệu văn bản… ───────────┐ [Tìm kiếm]   │
│ └────────────────────────────────────────────────────────────┘             │
│ [✓] Tìm chính xác cụm từ                                                   │
│ Lọc: [Danh mục ▼] [Loại văn bản ▼] [Cơ quan ▼] [Ngày áp dụng ▼]            │
│      [ ] Chỉ hiện quy định đang áp dụng                                    │
│ ────────────────────────────────────────────────────────────────────────── │
│ Có 5 khoản chứa đúng cụm từ “…” trong 3 văn bản.                           │
│                                                                            │
│ ▾ Nghị định 385/2026/NĐ-CP — Tên văn bản · Nghị định · Cơ quan             │
│   Liên kết trang công bố chính thức                    2 khoản khớp        │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │ Khoản 1 Điều 5 · Trang 12        [Đúng cụm từ] [Đang áp dụng]       │   │
│   │ “…các bộ, ngành thực hiện ▓báo cáo định kỳ và thường xuyên▓ …”     │   │
│   │ [Mở trang PDF nguồn]                                                │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│   ┌ Khoản 3 Điều 9 · Trang 20  [Đúng cụm từ] [Đã sửa đổi từ 01/07/2026] ┐   │
│   └─────────────────────────────────────────────────────────────────────┘  │
│ ▸ Thông tư …                                                               │
│                                                                            │
│ ‹ Trước   Trang 1 / 1   Sau ›                                              │
│ ▸ Kết quả gần đúng (7 khoản khớp một phần các từ)  — đang thu gọn          │
└────────────────────────────────────────────────────────────────────────────┘
```

- Results are **grouped by administrative document (văn bản)**; each group shows the document number, the title, the type, the issuing body, a link to the official publication page (if it has been verified) and the number of matching clauses; expand it to see the clauses (the first group is open by default).
- Each clause shows a match label (`Đúng cụm từ` (Exact phrase), `Cụm từ (không dấu)` (Phrase (unaccented)), `Đủ các từ` (All of the words)) and **the effectivity (hiệu lực) label of that clause itself** (icon + text + date). `Đã sửa đổi` (Amended) / `Đã bãi bỏ` (Repealed) / `Hiệu lực chưa xác minh` (Effectivity not verified) are always shown, and the change is not only a change of color.
- The snippet uses `<mark>` with the color taken from the highlight token; highlight only when the backend returns `highlights`.
- When the effectivity snapshot is stale: a warning band at the top of the results page, "Dữ liệu hiệu lực đang được cập nhật. Chưa thể khẳng định hiệu lực của các khoản bên dưới." (Effectivity data is being updated. The effectivity of the clauses below cannot yet be asserted.)
- On a phone: the filters go into a drawer; the results are one column; a touch target is at least 44×44px.

### 7.3 States and interface copy

| State | Copy |
|---|---|
| Placeholder | "Tìm theo từ khóa, cụm từ hoặc số hiệu văn bản…" (Search by keyword, phrase, or administrative-document (văn bản) number…) |
| Button | "Tìm kiếm" (Search); the checkbox "Tìm chính xác cụm từ" (Search for the exact phrase) |
| Nothing entered | A hint on how to search (three examples: a keyword, a phrase inside double quotes, a document number); no fake data |
| Searching | A neutral skeleton + "Đang tìm trong văn bản đã duyệt…" (Searching administrative documents that have been approved…) |
| Phrase results are present | "Có [N] khoản chứa đúng cụm từ “…” trong [M] văn bản." (There are [N] clauses that contain the exact phrase “…” in [M] administrative documents.) |
| Keyword results are present | "Tìm thấy [N] khoản trong [M] văn bản." ([N] clauses were found in [M] administrative documents.) |
| `PHRASE_NOT_FOUND` with all-words results | "Không tìm thấy đúng cụm từ “…”. Dưới đây là các khoản có đủ các từ của cụm từ này." (The exact phrase “…” was not found. Below are the clauses that contain all of the words of this phrase.) |
| `NO_RESULTS` | "Không có kết quả phù hợp. Thử bớt từ khóa hoặc bỏ tùy chọn tìm chính xác cụm từ." (There is no suitable result. Try fewer keywords, or turn off exact-phrase search.) |
| `NO_AUTHORIZED_DOCUMENTS` | "Chưa tìm thấy tài liệu được phép truy cập." (No document the user is allowed to access was found.) (exactly one message, and it does not reveal whether the store has an administrative document or not) |
| The query is too long or has too many words | "Câu tìm kiếm quá dài. Rút gọn dưới [N] ký tự." (The search query is too long. Shorten it to under [N] characters.) / "Câu tìm kiếm có quá nhiều từ. Giữ tối đa [N] từ." (The search query has too many words. Keep at most [N] words.) |
| Rate | "Bạn tìm kiếm quá nhanh. Thử lại sau vài giây." (You are searching too fast. Try again in a few seconds.) |
| Timeout | "Tìm kiếm mất quá nhiều thời gian. Thu hẹp bộ lọc rồi thử lại." (The search took too long. Narrow the filters and try again.) |
| The connection is lost | "Mất kết nối tới máy chủ. Nội dung bạn nhập vẫn được giữ." (The connection to the server was lost. What you typed is still kept.) + "Thử lại" (Try again) |
| Match labels | "Đúng cụm từ" (Exact phrase) · "Cụm từ (không dấu)" (Phrase (unaccented)) · "Đủ các từ" (All of the words) · "Một phần" (Partial) |
| Open the source | "Mở trang PDF nguồn" (Open the source PDF page) |
| Approximate section | "Kết quả gần đúng ([N] khoản khớp một phần các từ)" (Approximate results ([N] clauses that match some of the words)) — collapsed by default |

Forbidden: a percentage of "độ chính xác" (accuracy), "chắc chắn" (certain), or "đã xác minh" (verified) for a search result; "khớp cụm từ" (phrase match) for a bag-of-words result.

### 7.4 Accessibility and interface performance

- The search box has a label; Enter submits; there is no new global shortcut.
- The results region has `aria-live="polite"`, which announces the total when there are new results; each administrative document (văn bản) is a heading; the expand button has `aria-expanded`; the "Kết quả gần đúng" (Approximate results) item is a collapsed region with a count label.
- `prefers-reduced-motion` turns off the open and close animation.
- The result list is paginated (there is no infinite scroll); the search page loads lazily; no external resource is loaded in Local Mode.
- An automatic contrast test for the match labels, the effectivity (hiệu lực) labels and `<mark>`.

---

## 8. Work-package plan

Order: SR-0 → (SR-1 ∥ SR-2) → SR-3 → (SR-4 ∥ SR-5) → (SR-6 ∥ SR-7) → SR-8. The rough estimate from the previous options paper (about 11–12 person-days for 1 dev; with the backend and the frontend in parallel, still about 8–9 days) **has not been verified**; lock the schedule after SR-0.

| WP | Work | Acceptance |
|---|---|---|
| SR-0 | Check the current state against the source (section 4): `authorized_search.py`, `0001_core.sql`, `fixed_pipeline.py`, `draft.py`, `citation-contract.md`; check whether `text_indexed`/`text_folded`/`text_normalized` already normalize tone marks; check whether a Legal Reference Router exists in the code; check the contrib module on the packaged Windows PostgreSQL. Write a **characterization test for chat** | A current-state report (it matches, or it does not); an ADR for each difference; a green chat golden test as the baseline |
| SR-1 | Migration `0006` (an accented index and an unaccented index), `.down.sql`, an up/down test; `EXPLAIN` proving that the index is used together with the ACL semi-join; decide `pg_trgm` by measurement; mark `normalization_revision` | The index is used in `EXPLAIN` together with the ACL; the migration up/down is green; an ADR on the trigram index and on how to prevent a revision from drifting |
| SR-2 | `SearchService`: safe query analysis, shared normalization, T1–T4 with verbatim verification on the content field, an offset map, ranking, the ACL, version selection by `as_of_date`, effectivity (hiệu lực) per clause, grouping by administrative document (văn bản), pagination; refactor chat so that it calls `search_clauses` | A test for each tier; the chat golden test is still green; there is no remaining path that concatenates a tsquery from the input |
| SR-3 | `GET /api/v1/search` (plus the approximate-results endpoint), the schema, OpenAPI, the standard error codes, the rate limit, the timeout, and audit that does not store the raw query | OpenAPI is updated; tests of the error codes; audit follows section 2, point 10 |
| SR-4 | The Search page (section 7): the search box, the phrase checkbox, the filters, the administrative-document groups, the matching clauses, the `<mark>` snippet, the effectivity labels, the approximate section, pagination, the empty and error states, the button from the Chat Agent, and opening a PDF through the citation API | UI and accessibility tests like the existing pages; image snapshots of the match labels and the effectivity labels; the empty state is correct for the 3 cases |
| SR-5 | Effectivity integration: a per-clause label from the snapshot, a stale warning, and the switch "Chỉ đang áp dụng" (Only currently in force) | Test: a clause that is `modified/repealed/unknown` shows the correct label; a stale snapshot ⇒ a warning, and effectivity is not asserted |
| SR-6 | The evaluation set: 30–50 queries with an expected answer (administrative document + node) taken from **real approved administrative documents**, including positive cases, negative cases, tone-mark variants and document numbers; a script that computes the metrics; **the person who holds the business knowledge approves the expected answers** | A report of recall@k, precision@k, `exact_phrase_precision`, `wrong_doc_rate`, `wrong_node_rate`, correct-when-there-is-no-result, and p50/p95; only a case that has been approved counts toward the standard |
| SR-7 | Security and performance testing: an ACL leak (including the total, pagination, the empty state and errors), permission revoked part-way through, tsquery or SQL operator input, LIKE escaping, the length, rate and timeout limits, and a p95 benchmark | Every security test is green; the p95 measurement records the environment and the scale of the data |
| SR-8 | Documentation: an ADR, a runbook, a "Tìm kiếm văn bản" (Administrative-document search) section added to SRS v1.3, and a changelog; the data-precondition checklist (section 10) | The documentation is updated; there is no remaining divergence between the SRS and the source |

---

## 9. Acceptance criteria

**A. Hard checks (they must pass; they are not statistics)**

| # | Check |
|---|---|
| 1 | A phrase that is present in 3 approved administrative documents (văn bản) ⇒ all 3 administrative documents are returned on page 1 (when there is no filter) |
| 2 | A phrase that is not in the store ⇒ `phrase_found=false`, **no** result is labeled `exact_phrase`, and the message is correct |
| 3 | A result that only matches loose words ⇒ it **never** has the label "Đúng cụm từ" (Exact phrase) |
| 4 | Typing without accents, or "kì–kỳ", or "hòa–hoà", still finds the accented text; a result that matches only on the unaccented channel has the label `phrase_folded`, not `exact_phrase` |
| 5 | A phrase that crosses the boundary between the breadcrumb or the title and the content is **not** counted as `exact_phrase` |
| 6 | The administrative-document total, the clause total and the pagination are exact (`totals`, `has_more`); the depth limit is not exceeded |
| 7 | ACL: revoking permission ⇒ 0 results, and the name and the content are not revealed, including not through the total, pagination, the empty state or an error; run the PG integration test (it must not be skipped in CI: `EVIDENCE_TEST_DATABASE_URL` must be set) |
| 8 | Effectivity (hiệu lực) of each clause has the correct label; a stale snapshot ⇒ there is a warning; a clause whose effectivity is unclear ⇒ "Hiệu lực chưa xác minh" (Effectivity not verified) |
| 9 | The highlight is at the correct offset on `text_original`; when the offset is not certain, do not highlight |
| 10 | Opening the source PDF: the correct page; the ACL and the hash are checked as they are today; the citation record is created lazily in the correct way |
| 11 | Input that contains an operator or a special character (`"` `-` `|` `&` `:*` `<->` `'` `%` `_`) does not cause an SQL or tsquery error, and it does not change the meaning of the query beyond what was intended |
| 12 | A query that is too long, has too many words, exceeds the rate, or runs too long ⇒ the correct error code, and it does not hang |
| 13 | No chat regression: the same input yields the same 12 evidence items (căn cứ), claims and SSE (the golden test) |
| 14 | Local Mode: the search page generates no request to the outside, and it loads no external resource |
| 15 | The audit log does not contain the raw query text (unless the owner locks a different policy) |

**B. Measured indicators (report them; do not declare that they pass or that they are sufficient while there are no numbers)**

recall@k, precision@k, `exact_phrase_precision`, `wrong_doc_rate`, `wrong_node_rate`, correct-when-there-is-no-result, and p50/p95 latency. The latency target (for example p95 ≤ 300 ms with about 100k nodes on the dev machine) is a **target that must be measured** on the target Windows machine; if there is no real data at that scale, use generated data for a load trial and state clearly that the data is synthetic. The evaluation set must be independent of the data used to tune the thresholds of chat and RAG.

---

## 10. Data preconditions (very important)

As the current state describes it: 0 approved administrative documents (văn bản), 0 verified provenance, and 9/12 of the trial PDFs are scans that yield 0 nodes if there is no OCR (`database-summary.json`, `implementation-status.md`). If this is not resolved, the search page can be correct in code and still always be empty.

| Work | Who does it | Note |
|---|---|---|
| Approve the 3 administrative documents that are `pending_review`, or ingest a set of real administrative documents | **Reviewer / the person who holds the business knowledge** | The AI must not approve them itself |
| Verify provenance and span so that a citation can be opened | Reviewer/curator | |
| OCR for a scanned PDF | The AI drafts an **ADR** (engine, license, size within the 10 GB ceiling, offline execution, and do not install the runtime by default) → the owner approves → implement it as an exception plugin | Text from OCR becomes evidence (căn cứ) only after a reviewer approves it; attach `extraction_method=ocr`; check `text_quality` |
| Provide the current number of approved administrative documents and the time milestone that is wanted | **Owner** | Lock the schedule after SR-0 |

While real data is still awaited, the AI may develop and run tests with fixtures **labeled "HƯ CẤU" (FICTIONAL)**, kept apart from the evaluation corpus; a quality measurement counts only a real administrative document that has been approved.

---

## 11. Defaults the agent uses if there is no direction yet (the owner can change them)

| Issue | Default |
|---|---|
| Maximum query length / maximum word count | 500 characters / 20 words |
| Default / maximum `page_size` | 20 / 50 |
| Number of matching clauses shown per administrative document (văn bản) | 5 (with a see-more button) |
| Pagination depth limit | 1000 results |
| `statement_timeout` for search | configurable; a proposal of a few seconds, locked by measurement |
| Maximum rate per user | configurable; a proposal of a per-minute limit |
| A clause that has been amended (sửa đổi) or repealed (bãi bỏ) | Shown together with a label; the switch "Chỉ hiện quy định đang áp dụng" (Show only provisions currently in force) is off by default |
| Trigram index | Do not add it until measurement proves it is needed |
| Storing the raw query text | No; only the hash + the length + the filters + the result count |
| Several phrases in one query | P1; Search v1 supports one phrase inside double quotes plus loose keywords |
| Size of the evaluation set | 30–50 queries |

---

## 12. Report template at the end of each WP (required)

```text
WP: <id> — <tên>
Trạng thái: Xong / Xong một phần / Bị chặn
Đã làm: <danh sách ngắn>
Test: <tên test + kết quả thật, số pass/fail>
Số đo: <nếu có; ghi môi trường, phiên bản, quy mô dữ liệu>
Quyết định/ADR mới: <id>
CHƯA XONG / bị hoãn: <liệt kê rõ, kèm lý do>
Rủi ro / cần người quyết: <nếu có>
```

The "CHƯA XONG" (NOT DONE) part must not be left empty by omitting it; do not change the acceptance criteria in order to make a test green.

---

## 13. Main risks

| Risk | Handling |
|---|---|
| The planner drops the GIN index when it is combined with the ACL view | SR-1 checks `EXPLAIN`; the alternatives: compute the permitted `document_id` set in advance, or a `MATERIALIZED` CTE; record the measurements |
| Normalization drifts between the index and the query ⇒ the text is not found even though it is there | One shared normalization function; tests for hòa/hoà and for NFC/NFD; `normalization_revision` plus a check at startup |
| The label "đúng cụm từ" (exact phrase) is attached by mistake to a result that is not adjacent, or that crosses the breadcrumb | Verbatim verification on the content field; hard checks #3 and #5 |
| The existence of a document is revealed through the total, the empty state or an error | Compute on the permitted set; one empty message; a leak test that includes both the count and the pagination |
| The refactor breaks chat | A golden test before the refactor (SR-0); a new parameter defaults to keeping the old behavior |
| Empty data makes every demo fail | Section 10; an "HƯ CẤU" (FICTIONAL) fixture for development, and a real approved administrative document (văn bản) for measurement |
| OCR pulls in a heavy dependency or a large size | A separate ADR, an exception plugin, and approval before it is turned on |
| A "correct/complete" figure is claimed too early | Report it only when an approved search Gold [Not implemented — see ADR-010] exists; every number records the environment |
| A heavy query slows the system | A timeout, a rate limit, a depth limit, and a p95 measurement |

---

## 14. Later expansion (option B) — not done in Search v1

Once a model runs locally and Gold [Not implemented — see ADR-010] has been approved: add `lexical_search_index` with a revision, a Vietnamese tokenizer (Underthesea/PyVi, following SRS v1.3), embeddings through the Model Registry (extend the registry for a model of the embedding type), RRF + pre-gate + rerank, and route to the administrative document (văn bản) before the node. Every later step sits behind a feature flag, and it is turned on only when the benchmark does not regress; the channel interface and the merge function in section 5.4 already leave room so that the API and the interface of the search page do not change.

---

## 15. Prompt handed to the implementing AI

> You are a coding agent implementing **Search v1** for the Vietnamese Evidence RAG Agent, integrated into the existing app as a separate module (a Search page in the User Portal, and a `SearchService` shared with chat). Read this plan and `SRS_v1.3.md` carefully; this plan wins over the previous options paper on the points in section 2. Start with SR-0: check the current state against the real source, and write a golden test for chat before the refactor. Keep strict backward compatibility: a new parameter defaults to keeping the old behavior, and chat does not change. Work on your own; use the defaults in section 11 when there is no direction yet, and write an ADR; stop and wait for a person only for business rules, access rights, security, and correctness of evidence (căn cứ). Do not concatenate a tsquery from the user's input; attach the label "đúng cụm từ" (exact phrase) only after verbatim verification on the content field; effectivity (hiệu lực) is computed per clause; the empty state must not reveal that a document exists; do not approve an administrative document (văn bản) yourself, and do not certify an evaluation answer yourself; do not claim a figure that has not been measured; a fixture must carry the label "HƯ CẤU" (FICTIONAL). At the end of each WP, report with the template in section 12, and state clearly what is not finished.

---

## 16. What the owner needs to do

1. Provide **the current number of approved administrative documents (văn bản) and the time milestone that is wanted** (section 10).
2. Name the reviewer, or the person who holds the business knowledge, who will approve the 3 administrative documents currently `pending_review` and who will approve the expected answers of the SR-6 evaluation set.
3. Approve the OCR ADR (engine, license, size) if scanned PDFs are to be processed.
4. Confirm the defaults in section 11, in particular: whether a clause that has been amended (sửa đổi) or repealed (bãi bỏ) is shown with a label or hidden by default; and whether the raw query text is stored.
5. Provide the target Windows machine, so that p95 and the index size can be measured.
