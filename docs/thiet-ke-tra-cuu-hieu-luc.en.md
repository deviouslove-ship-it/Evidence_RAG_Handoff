**Language / Ngôn ngữ:** [Tiếng Việt](thiet-ke-tra-cuu-hieu-luc.md) · English

English counterpart of `docs/thiet-ke-tra-cuu-hieu-luc.md`. The Vietnamese file is the original.

# Design for comprehensive lookup, effectivity (hiệu lực), and evidence (căn cứ) synthesis (finalized)

Updated 2026-11-06. This version replaces the v1 and v2 proposals from the discussion and is the basis for implementing G0 → G5. The owner’s decisions are recorded in section 1; the rest is the technical design after a consistency review.

Progress (2026-11-07): G0, G1.0, G1, G2, G3, G4, and G5 are implemented (ADR-007, ADR-008, ADR-009); the detailed status and the parts not yet verified are in [implementation-status.md](implementation-status.md).

## 0. Goals and limits

The system helps officers **search, look up, ask questions, synthesize, analyze, and suggest evidence (căn cứ)** from the corpus of administrative documents (văn bản), quickly, completely, accurately, transparently, and in a way that can be checked. The system does **not** make a business decision; the assessment and the final decision belong to the specialist officer.

| Criterion | Priority |
|---|---|
| Find the related administrative documents in full, and do not miss important evidence | Very high |
| Determine effectivity (hiệu lực) correctly | Very high |
| Cite the correct Article (Điều)/Clause (Khoản)/Point (Điểm), and open the correct original PDF | Very high |
| Synthesize and classify provisions | Very high |
| Explain the content | Medium |
| Analysis and suggestions | Supporting |
| Reasoning about a complex situation | Not a focus |
| Drawing a business conclusion on its own | Not done |

Do not over-design: use the code, the database, the permissions, and the interface that already exist; no complicated approval workflow; do not require an officer to confirm every provision by hand; do not add an AI dependency that is not needed.

## 1. Decisions already made

| # | Topic | Decision |
|---|---|---|
| D1 | How effectivity (hiệu lực) is shown | Two separate axes: **effectivity status** and **verification status** (“Đã xác minh” (Verified) · “Chưa xác minh” (Unverified) · “Không tìm thấy thông tin trong kho” (No information found in the corpus)). “Verified” (“Đã xác minh”) always comes with the result, the source, the person, and the time. Do not infer “in effect” (“còn hiệu lực”) from the fact that no repealing (bãi bỏ) administrative document (văn bản) has been seen |
| D2 | Effectivity order | The administrative-document level first, then Article (Điều)/Clause (Khoản)/Point (Điểm); the data model supports the clause level from the start |
| D3 | Administrative-document groups | Group the original, the amendment (sửa đổi), the supplement (bổ sung), the replacement (thay thế), and the consolidated document (văn bản hợp nhất); each administrative document can still be read on its own, with the amending text verbatim and the original PDF. Do not create a consolidated document with AI |
| D4 | Content groups | A catalogue that can be extended, stored in the database; one clause (Khoản) may belong to many groups; a clause with no group still appears; a rule assigns a group when the match is clear enough, the AI proposes, and a person who has been granted permission reviews |
| D5 | Using a model | Local first; an LLM only when it is needed; every model goes through the Model Registry; drop the fixed number of calls and use configurable limits and cost control instead; do not call the API because data is missing |
| D6 | Ranking | Do not use Top-K to drop a result permanently; batched rerank has a cap; the full results can be viewed through pagination and filters; mark what has been reranked and what has not; do not send thousands of clauses into one LLM turn |
| D7 | Who confirms | An officer who has been granted permission; the AI only proposes; store the person, the time, the content, the evidence (căn cứ), and the history; approval may be by group, but each relation has its own record |
| D8 | Escalation from Local to the API | **Hybrid Auto**: switch to the API automatically when the local result does not pass the quality checks, or when the user chooses “phân tích sâu” (“deep analysis”). Only when suitable evidence already exists. Comply with permissions, the cost cap, and the API policy. Local Only mode never calls the API |
| D9 | Administrative documents that are no longer in effect | By default, prefer an administrative document that is in effect and verified, and an administrative document that is not yet verified (with a label); an administrative document that is no longer in effect, or that has been replaced (thay thế), can still be found through a filter or a separate group; search-all, historical comparison, and lookup at a point in time include them in the results. Do not drop an administrative document because it has not been verified |
| D10 | Permission to confirm effectivity | Use the existing `REVIEWER` role and add scope by category; do not add a role |
| D11 | Synthesis cap | The administrator configures the number of evidence items and the token budget; the result list is always complete through pagination; synthesize by group or by batch and then merge with checks; report “đã dùng N trong M căn cứ” (“used N of M evidence items”); the user may ask for a wider scope |
| D12 | Questions and answers when effectivity is not yet verified | Do not block. Evidence that has passed the source check (the correct file, the correct text, the correct page) may be explained, summarized, and synthesized, with an effectivity warning |
| D13 | Comprehensive search is not comprehensive synthesis | Search favors coverage; synthesis works through the groups in scope one after another, and does not take a few representative results and treat them as the whole |
| D14 | Point in time | Distinguish the lookup date (`as_of_date`), the verification date, and the data date of the corpus |
| D15 | Omissions | A list of evidence that must be found, by test topic; do not build a large Gold [Not implemented — see ADR-010] QA set |

## 2. Two layers of checking (resolves D12)

| Layer | Meaning | Condition for use in lookup and Q&A | Already present |
|---|---|---|---|
| **Source check** | The administrative document (văn bản) has source approval: the correct file (SHA-256), text that matches the PDF page, and an Article (Điều)/Clause (Khoản)/Point (Điểm) tree that can be anchored | **Required** (handoff-record invariant: only an approved administrative document enters the official corpus) | Yes (administrative-document approval, and bulk approval for the trial data) |
| **Effectivity (hiệu lực) verification** | Whether the administrative document or clause is in effect or no longer in effect on the lookup date is known | **Not required**; if it is missing, a warning is attached | Not yet (G1, G3) |

A draft that has not passed source approval does not enter lookup. Source approval is light: automatic checks in code, and the approver confirms a batch; it is not effectivity verification.

## 3. Data model

Use the tables that already exist (`document_nodes.parent_id`, `page_end`, `node_amendments`, `node_references`, `effectivity_snapshot_revisions`, `node_effective_intervals`, and the hash-chain audit log); only add columns and small tables.

| Change | Stage | Purpose |
|---|---|---|
| `node_source_spans(node_id, ordinal, source_span_id)` | G0 | One clause (Khoản) anchors to several spans, one span per page |
| Record `document_nodes.parent_id`, `page_end`, a structured `path`, and add `citation_label` | G0 | The tree Article (Điều) → Clause (Khoản) → Point (Điểm); the citation label “Điểm a khoản 2 Điều 5” (“Point a, Clause 2, Article 5”) |
| The function `node_source_text_valid(node_id)` | G0 | Check every source span of one clause (approval, and opening a citation) |
| `node_amendments`: add the scope (administrative document (văn bản) or node), an administrative-document-level target, a target not yet in the corpus (normalized document number, Article/Clause/Point path), a condition, the proposal source (rule, AI, person), confidence, the model version, the approval-batch code, and `superseded_by` | G1 | Effectivity (hiệu lực) relations at both levels in one table |
| `node_references.reference_kind` (evidence (căn cứ), guidance, consolidation (hợp nhất), cross-reference) | G1 | A relation that is only related, and does not change effectivity |
| `document_effective_intervals` (by snapshot) | G1 | Effectivity at administrative-document level; the node level stores only an exception, and the rest is inherited |
| A `verification_state` column on both effectivity-interval tables | G1 | The verification axis |
| `effectivity_attestations` | G1 | A person’s attestation: the target, the result, the time interval it applies to, the source, the person, the time, and the status (in effect, needs re-verification, revoked) |
| `category_acl.can_review` | G1 | Approval scope by category (D10) |
| `ai_usage_events`, and the stage policy in the Registry | G1.0 | Cost control (D5) |
| A vector index by the model’s number of dimensions | G2 | Changing the embedding model does not change the schema |
| `concept_terms` (a concept dictionary) | G2 | Query expansion that has been approved |
| `content_taxonomy`, `node_labels`, `labeling_rules` | G4 | Content groups |

The history of a relation or an attestation uses the existing hash-chain audit log plus `superseded_by` (the old record is not deleted); a separate event table is not created.

## 4. Effectivity (hiệu lực)

**Axis A (effectivity):** “Còn hiệu lực” (In effect) · “Chưa có hiệu lực” (Not yet in effect) · “Sửa đổi một phần” (Partially amended) · “Tạm ngưng” (Suspended) · “Hết hiệu lực” (No longer in effect) · “Bị thay thế” (Replaced) · “Chưa xác định” (Undetermined).

**Axis B (verification):** “Đã xác minh” (Verified) · “Chưa xác minh” (Unverified) · “Không tìm thấy thông tin trong kho” (No information found in the corpus).

**Hard rules (in code, not in configuration):**
1. “In effect + Verified” (“Còn hiệu lực + Đã xác minh”) is produced only from a person’s attestation that has a source and a time.
2. No terminating relation → axis A “Undetermined” (“Chưa xác định”) (together with a known event, for example “có hiệu lực từ D1” (“in effect from D1”)), and axis B “No information found in the corpus” (“Không tìm thấy thông tin trong kho”).
3. A relation proposed by the AI or by a rule, and not yet approved, does not change axis A; it only adds the warning “có đề xuất chưa xác nhận” (“there is an unconfirmed proposal”).
4. A relation that is conditional, transitional, or past its time limit is not computed automatically; axis A is “Undetermined” (“Chưa xác định”), and the condition is stated.
5. An attestation moves itself to “cần xác minh lại” (“needs re-verification”) when the corpus gains a new relation that touches the target after the verification time.

**Point in time (D14).**
- `as_of_date`: the date the user looks up; every status is computed **on that date**. Today’s status is not applied to the past or the future.
- Verification date: the attestation records the time interval it asserts (`valid_for_from`, and `valid_for_to` = the verification date when the result is “in effect” (“còn hiệu lực”)). A lookup date outside that interval → axis B “Unverified on the lookup date” (“Chưa xác minh tại ngày tra cứu”), together with “verified on D2” (“đã xác minh tại D2”).
- The data date of the corpus: the snapshot publication date and the date the newest administrative document (văn bản) was loaded; always show “kho đến ngày D” (“corpus through date D”).
- A lookup date after the data date: axis B is at most “Unverified” (“Chưa xác minh”).

**Administrative-document level and clause level.** The effectivity of a clause is the node-level exception row when one exists, and otherwise it inherits the administrative-document level. An administrative document that is repealed (bãi bỏ) needs only one row. An administrative document with several effectivity dates (for example Article 2 of Circular (Thông tư) 28/2024 from 2024-08-01, and the rest from 2024-07-01) records an exception at Article (Điều) level.

**Until G3 is finished:** a fixed warning bar, “Hiệu lực đến cấp Điều, Khoản, Điểm chưa được xác minh; kết quả phản ánh hiệu lực cấp văn bản” (“Effectivity down to Article, Clause, and Point has not been verified; the results reflect administrative-document-level effectivity”). A clause that belongs to an administrative document which has been partially amended (sửa đổi), and whose target has not been linked: “Văn bản đã được sửa đổi một phần; chưa xác định khoản này có bị ảnh hưởng” (“The administrative document has been partially amended; it has not been determined whether this clause is affected”). The clause-level review level is **computed automatically** (every known relation aimed at the administrative document has been linked to a node and approved). The person is not asked to confirm anything further.

## 5. Relations and administrative-document groups

- What changes effectivity (hiệu lực): amend (sửa đổi), supplement (bổ sung), replace (thay thế), repeal (bãi bỏ) (in whole or in part), and suspension of effectivity.
- Related only: implementing guidance, the basis of issuance (căn cứ ban hành), a cross-reference, and consolidation (hợp nhất). Guidance and the basis of issuance do not create a group; they only appear under “Văn bản liên quan” (“Related administrative documents”).
- A group follows the original administrative document (văn bản) and is computed at query time from the relations table. An administrative document that amends several originals (Circular (Thông tư) 66/2023 amends 55, 56, and 57/2021) belongs to several groups; the flat list shows only one card, “thuộc nhóm của…” (“belongs to the group of…”).
- Amending text is shown verbatim from the amending administrative document (Article (Điều), Clause (Khoản), page, PDF). If a consolidated document (văn bản hợp nhất) is in the corpus, link to it as its own administrative document; a consolidated document is used for comparison, and it is not the only evidence (căn cứ) that changes effectivity.
- Identifying an administrative document: normalized document number + type + issue date + issuing body (a consolidated-document number gets reused). An ambiguous match goes to a person’s queue.
- Filter by permission: an administrative document outside the granted categories is not revealed; the only record is “có văn bản liên quan ngoài phạm vi được cấp quyền” (“there is a related administrative document outside the granted scope”).
- When a new administrative document is loaded, automatically try again to match targets that are “chưa có trong kho” (“not yet in the corpus”).

## 6. Comprehensive search, ranking, and pagination

**Four channels, fused with RRF:** exact (document number, Article (Điều), phrase, keyword, diacritic-folded; already present) · semantic (a local embedding) · concept expansion (an approved dictionary, plus the AI when the dictionary yields fewer concepts than the threshold; the user sees them and can deselect them) · administrative-document (văn bản) relations (an amendment (sửa đổi), guidance, or a consolidated document (văn bản hợp nhất) of an administrative document that already matched).

**An honest scope.** The exact channel can be counted in full. The semantic channel always returns the nearest neighbors, so it has a configurable cap N and a relative threshold, stated in the search scope. Report the number of clauses (Khoản) that appear only because of the semantic channel or the relation channel. A result always records the categories that were searched, the number of administrative documents in scope, the data date, and “chưa thấy trong kho” (“not found in the corpus”), rather than “đã tìm hết mọi quy định” (“every provision has been searched”).

**A result set fixed for the turn** (session memory, with an expiry; an anonymous session is not stored durably); pagination reads from that set, so the order stays stable; permission is checked again when each page is opened.

**Rerank (D6):** in batches over the first N candidates (configured); the rest keep RRF order; no candidate is dropped; a `ranking` field (reranked or not yet reranked, how many were reranked, the total); filters run over the whole set.

**Display by effectivity (hiệu lực) (D9):** the default mode places the groups “Còn hiệu lực (đã xác minh)” (“In effect (verified)”) and “Chưa xác minh hiệu lực” (“Effectivity not verified”) first; “Hết hiệu lực, bị thay thế” (“No longer in effect, replaced (thay thế)”) is a separate group, collapsed, and still counted. The mode “Tìm toàn bộ” (“Search everything”), the mode “Đối chiếu lịch sử” (“Compare against history”), or an `as_of_date` other than today places everything in the same list. The effectivity-status filter and the verification-status filter apply to the whole set.

Q&A (chat) keeps the option-C rule (ADR-006): a clause that is no longer in effect does not support the main finding unless the user asked for that clause by name; it still appears as an evidence (căn cứ) card with its status.

## 7. Synthesis, explanation, and suggestions

Three layers, kept apart in the interface: **“Nguyên văn”** (Verbatim) (from the database) · **“Diễn giải”** (Interpretation) (AI, and each point is tied to an evidence (căn cứ) code) · **“Gợi ý tham khảo”** (Suggestion for reference) (what to look at next; not an assertion).

**A check in code for every point the AI writes:** the evidence code must belong to the set that was issued; a number, a date, a document number, and an Article (Điều)/Clause (Khoản) name must appear in the attached evidence; the point must not contain a business-conclusion word (“phải xử lý” (“must be handled”), “đủ điều kiện” (“meets the conditions”), “quyết định” (“decide”)) outside a quotation. A point that does not pass is dropped, or marked “chưa kiểm chứng” (“not yet checked”).

**Comprehensive synthesis (D11, D13):** split into groups (by content group when one exists, otherwise by administrative document (văn bản)), and split into batches by the token budget; summarize each group, and merge in code. When the budget runs out, stop and report “đã tổng hợp N trong M căn cứ, K nhóm còn lại” (“synthesized N of M evidence items, K groups remaining”); the button “Tổng hợp tiếp” (Continue synthesis) runs the next batch. The full list is always independent of the summary budget.

**Condition for running:** at least one evidence item that has passed the source check (D12). If there is no evidence, the result is “không tìm thấy trong kho” (“not found in the corpus”), and no model is called.

## 8. Model policy and Hybrid Auto (D5, D8)

| Task | Handling |
|---|---|
| Exact search, structure, relations, citations, the effectivity (hiệu lực) resolver, and the check of an AI point | Source code |
| Embedding and rerank | A local model (the Registry) |
| Query expansion | A dictionary and rules; the AI when it is needed |
| A relation proposal, and labeling | A background task, local first |
| Summary, explanation, analysis, and suggestions | Local first; API escalation under D8 |

**Modes.** Keep the two configuration values `LOCAL` and `API` (do not break configuration that is already deployed):
- `LOCAL` = **Local Only**: only an approved loopback or LAN endpoint; there is no path out to an API.
- `API` = **Hybrid Auto**: the primary route of each stage may be a local profile; an **escalation profile** (`public`) is added for the summary and explanation stages. Escalate when: (a) the local result does not pass the checks in section 7, or (b) the user presses “Phân tích sâu” (Deep analysis). Do not escalate because evidence (căn cứ) is missing, nothing was found, or effectivity has not been verified. Apply the existing egress conditions in full (an allowed domain, a user who is allowed external AI, and every source category allowing external processing) and the cost cap. The interface records “đã dùng API ngoài” (“an external API was used”); the log records it as well.

**Configurable limits per stage** (in place of the fixed count of 2 attempts): attempts per request, input and output tokens, timeout, concurrent requests, and a daily and monthly cost cap per profile. Over the cap, fall back to the path that does not use a model (verbatim text, grouped by rules) and say so clearly. Each call writes an `ai_usage_events` row.

**Stages in the Registry:** `answer` (already present), `embedding`, `rerank`, `expand`, `relation`, `label`, and `summarize`. Changing the model only changes configuration; a background result (a label, a relation proposal, a vector) records the model version so it can be computed again.

## 9. Confirming an effectivity relation (D7, D10)

- Permission: a `REVIEWER` who has `can_review` on the category of the target or source administrative document (văn bản).
- The person or the task that proposed the relation does not confirm it; the AI has no approval permission.
- A screen organized by the amending administrative document lists the proposals (the original sentence with its page, the target that was matched, the action, the date, the proposal source, and the confidence). A whole batch may be approved; each relation has one audit record, and they share a batch code.
- Store the person, the time, the content, the evidence (căn cứ) (the node that contains the original sentence), and the history (`superseded_by` plus the audit log).
- Administrative-document approval (the source check) also shows the issue date and the effectivity (hiệu lực) date that were read, so the approver can confirm them at the same time; a separate step is not created.

## 10. Who does what

| Task | Automatic code | AI support | A person confirms |
|---|---|---|---|
| Convert Word/TXT, build the tree, anchor pages, and set the text-quality flag | Yes | | Source approval (already present) |
| Issue date and effectivity (hiệu lực) date | Rules | An unusual sentence | At source approval |
| A relation from a sentence pattern | Rules | A complex sentence | **Yes** |
| Match a document number | Yes | | When the match is ambiguous |
| Compute effectivity intervals and publish the snapshot | Yes | | |
| “Còn hiệu lực, đã xác minh” (“In effect, verified”) | | | **Yes**, with the source and the time |
| Administrative-document (văn bản) groups, the search scope, and the citation check | Yes | | |
| Concept expansion | The dictionary | Supplement (bổ sung) | Dictionary approval; the user deselects |
| Embedding and RRF | Yes | | |
| Rerank | | A local model | |
| Content groups | Rules, when clear enough | The remainder | Batch review |
| Summary, explanation, and suggestions | A check in code | Yes | The officer reads and decides |
| A business conclusion | **Not done** | | |

## 11. Stages and the consistency review

| Stage | Content | Depends on | Technical check when the stage is finished |
|---|---|---|---|
| **G0 Foundation** | Anchors across several pages (spans in reading order); `parent_id`, `page_end`, `path`, and `citation_label`; rebuild the tree for an old draft (a trial run, then apply); a quality flag for the text layer | — | The existing test suite; load the trial data set and trial-approve it on a temporary database: the share of clauses (Khoản) that can be anchored, and the share of administrative documents (văn bản) that can be approved; open the citation of a clause that spans pages |
| **G1.0 Registry** | The new stages; a configurable limit policy (drop the fixed 2 attempts); `ai_usage_events`; an escalation profile (Hybrid Auto); API mode allows a local primary route | G0 | Local Only does not call the API; over the cap, fall back to the no-model path; with no evidence (căn cứ), 0 calls |
| **G1 Effectivity (hiệu lực) at administrative-document level** | The tables and columns in section 3; read dates; read administrative-document-level relations (replace (thay thế), repeal (bãi bỏ), a catalogue of instruments no longer in effect, and the header of a consolidated document (văn bản hợp nhất)); match document numbers; a batch approval queue; attestations; the snapshot; display of both axes and the clause-level warning; `can_review` | G0, G1.0 | A real chain in the trial data; the two axes do not produce “đã xác minh” (“verified”) when an attestation is missing; an attestation downgrades itself |
| **G2 Comprehensive search** | Local embedding (qwen3-embedding through Ollama); RRF; the dictionary and expansion; the relation channel; administrative-document groups; a fixed result set; batched rerank; the search scope; display under D9 | G0, G1 (groups, and the effectivity filter) | The list that must be found (D15); pagination with no duplicate and no omission; turn each channel off and measure what it contributes |
| **G3 Effectivity at Article (Điều)/Clause (Khoản)/Point (Điểm) level** | Read “sửa đổi khoản X Điều Y như sau” (“amend clause X of Article Y as follows”); link the target through the tree (this needs G0); an effectivity date at Article level; a review level that is computed automatically; remove the shared warning once the level is sufficient | G0, G1 | Measure precision and coverage on about 30 relations a person has verified |
| **G4 Content groups and synthesis** | The catalogue, the rules, AI labels, and lazy assignment; batch review; synthesis by group or by batch, with checks; Hybrid Auto for the summary | G1.0, G2 | No point lacks evidence; the N/M report is correct; a clause with no label still appears |
| **G5 Quality** | A dedicated reranker once a server is available; continuous coverage tests; a tool to change the model and compute again; a report written out to a file | G2–G4 | — |

**Consistency points already reviewed**

| # | Point | How it is resolved |
|---|---|---|
| 1 | The `effective_status` enum mixes “not yet known” into the status | Keep the enum for axis A; add a column for axis B; the API adds a field (additive) |
| 2 | The handoff record states “at most 2 LLM attempts” as an invariant | A new ADR at G1.0 replaces that with a configuration policy |
| 3 | A fallback stays inside the same data zone | A separate escalation profile, only in `API` mode |
| 4 | `API` mode currently requires a profile in the `public` zone | At G1.0 the primary route may use a local profile inside `API` mode |
| 5 | “Run a summary only when the evidence (căn cứ) has been verified” (v2) conflicts with D12 | Changed to “has passed the source check” |
| 6 | “Pick a representative to summarize” (v2) conflicts with D13 | Synthesize by group or by batch, and report N/M |
| 7 | “The review level needs a person to confirm it” (v2) conflicts with 5.5 | It is computed automatically |
| 8 | A separate `relation_events` table (v2) duplicates the audit log | Dropped; use the audit log plus `superseded_by` |
| 9 | Semantic search has no “whole set” | A configured cap, stated in the scope |
| 10 | A non-deterministic rerank shifts the pages | A result set fixed for the turn |
| 11 | Linking a target at Article/Clause level needs a correct tree | G0 before G3 |
| 12 | An administrative-document (văn bản) group can reveal an administrative document outside the granted permissions | Filter by permission |
| 13 | The vector column is fixed at 768 dimensions | G2: an index sized to the model’s dimensions |
| 14 | Checking a clause that spans pages on the hot search path is expensive | The search path checks the first span (a one-page clause is still checked in full); approval and opening a citation check every span |

## 12. Testing (not based on Gold [Not implemented — see ADR-010] QA)

- **Coverage (D15):** `evaluation/coverage/` holds 5–8 topics. Each topic has a few ways of asking and a list of evidence (căn cứ) that must be found (document number + Article (Điều)/Clause (Khoản)). Measure the find rate of each channel.
- **Citations:** check every result automatically: the text matches the page, the hash, the Article/Clause/Point path, and the correct page opens.
- **Effectivity (hiệu lực):** real chains in the trial data (55/2021 → 66/2023 → VBHN 43/2025; 29/2016 was repealed (bãi bỏ) by 110/2021; 58/2026 and 96/2026 replace (thay thế) older circulars (Thông tư); 28/2024 has two effectivity dates).
- **Against fabrication:** a number, a date, and a document number in the AI portion must be present in the evidence; a question about an administrative document (văn bản) outside the corpus returns “không tìm thấy trong kho” (“not found in the corpus”); with no evidence, there are 0 model calls.
- **Cost and mode:** Local Only does not call the API; over the cap, the path falls back to the one that does not use a model.
