**Language / Ngôn ngữ:** [Tiếng Việt](ADR-010-khong-trien-khai-bo-cau-hoi-gold.md) · English

English counterpart of `docs/architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md`. The Vietnamese file is the original.

# ADR-010 — The Gold question set is not implemented

- Date: 2026-11-09
- Status: Accepted
- Decided by: the project owner
- Partially supersedes: the material on Gold, the trap set, held-out, and the condition “without Gold, do not yet report correct/complete” (“đúng/đủ”) in [ADR-000](ADR-000.md) (ADR-000.07), [ADR-003](ADR-003-rag-anything-selective-adoption.md), [ADR-005](ADR-005-search-v1.md), SRS v1.3, the handoff record, and the Search v1 plan.
- Related document: [Former Gold protocol](../history/eval-gold-protocol.md) (kept as history; not in force)

## 1. Context

Earlier documents set a goal of building a set of 150–200 Gold questions (with a trap set, split into calibration and held-out), approved by the person who holds the business knowledge, and of using that set as the acceptance condition for answer quality. That work was never done: there is no case, there is no reviewer, and the S1/S2/S3 gates are still open.

## 2. Decision

The Gold question set is not implemented, and a question set is not used to score the AI’s answers.

Reasons:

1. **The AI is not the decision-maker.** The AI only supports lookup and interpretation; the answer is not decided by the AI, so there is no “reference answer” to score against.
2. **The specialist officer is responsible.** The officer looks the question up, compares it with the original evidence (căn cứ), and is responsible for their own report. An AI result always has to be checked before it is used.
3. **Quality is assured by control mechanisms, not by a score:**
   - a citation pinned to its source: the excerpt is taken from `text_original`, the original file is identified by SHA-256, and it is checked again when opened;
   - a two-person approval process: the approver is a different person from the preparer (`SELF_APPROVAL_DENIED`);
   - an audit log for administration and approval actions.

## 3. What is kept

The technical checks of search stay, because they measure the behavior of the search engine and do not score the AI’s answers: citation coverage, exact-phrase precision (`exact_phrase_precision`), and similar checks. An example from the G5 check: coverage of 0.960 and 0.865. These figures are technical measurements on the data and the environment recorded in the report; they are not proof that an answer is correct.

## 4. Consequences

- The principle “Gold/trap is recognized only after the person who holds the business knowledge has approved it” is dropped. The new principle: **do not use a Gold question set to score the AI; the AI only assists, and the specialist officer decides.**
- There is no longer an acceptance condition based on Gold. The system still must not state an accuracy, a coverage, or a deployment-readiness level unless a report exists in the supporting corpus.
- Older documents that mention Gold as work still to be done are labeled “[Not implemented — see ADR-010]”. Historical reports in `docs/evidence/`, and the code and data in `evaluation/`, stay as they are.
- The former protocol was moved to [`docs/history/eval-gold-protocol.md`](../history/eval-gold-protocol.md).
