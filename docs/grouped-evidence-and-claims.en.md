**Language / Ngôn ngữ:** [Tiếng Việt](grouped-evidence-and-claims.md) · English

English counterpart of `docs/grouped-evidence-and-claims.md`. The Vietnamese file is the original.

# Grouped evidence and claims

An evidence group organizes sources by role: principal provision, subject, condition, exception, transitional provision, and authority. Auto-merge is only a UI organization. It does not drop the identity of each source.

Every claim must have valid evidence IDs. The validator checks numbers, dates, time limits, negation, modality, and exceptions. The validator returns `supported` or `conditional`. It does not claim absolute semantic proof.

Memory, suggestions, analysis, and follow-up questions are not evidence.

## Suggestion deduplication rules (Suggestions Deduplication)

While creating the answer and the reference suggestions:

- Evidence (căn cứ) already cited in the main findings (`claims`) is automatically excluded from the evidence set of the reference suggestions (`suggestions`).
- Suggestions propose only supplementary (bổ sung) related legal evidence that has not yet appeared in the statements of the main findings, so the user receives new lookup directions and the same information is not repeated.
