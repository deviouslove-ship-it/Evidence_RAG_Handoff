# Requirements: AI Interpretation and Verified Synthesis

> Spec reconstructed from the implemented code on 2026-11-09. This is not a historical Kiro-generated spec. Evidence is cited by repository path. Decisions: ADR-007, ADR-009 section 2.

## Introduction

"AI interpretation" is an optional, separate action. A model reads only evidence the user may see, and every statement it returns is checked by code before it is shown. Original evidence always remains visible.

## Requirements

### Requirement 1: Evidence-only input

#### Acceptance Criteria

1. WHEN a user selects "Diễn giải AI" THE SYSTEM SHALL send the question and only permitted, approved evidence selected for the question to the `summarize` stage model (`POST /api/v1/synthesis`, `synthesis/service.py`).
2. THE SYSTEM SHALL separate provisions that answer the question from provisions that only share the topic (`synthesis/focus.py`, `focused.py`).
3. IF no evidence exists THEN THE SYSTEM SHALL NOT call a model.

### Requirement 2: Code verification of each statement

#### Acceptance Criteria

1. WHEN the model returns statements THE SYSTEM SHALL check that evidence IDs belong to the granted set (`synthesis/checks.py`).
2. THE SYSTEM SHALL check that numbers, dates, document numbers and Article/Clause/Point labels appear in the attached evidence that was actually sent.
3. IF a statement states a business conclusion outside quotation marks THEN THE SYSTEM SHALL drop it; IF facts are missing THEN THE SYSTEM SHALL label it "not verified".
4. THE SYSTEM SHALL show the answer, citation count, parts lacking evidence, supporting evidence and check information.
5. IF the question is outside the evidence, for example blood-alcohol penalties without matching provisions, THEN THE SYSTEM SHALL answer "not found" rather than an off-topic point.

### Requirement 3: Batching and budgets

#### Acceptance Criteria

1. THE SYSTEM SHALL process evidence in batches no larger than `max_evidence_per_batch`, within `token_budget` and `max_batches_per_run`, configured by administrators (`GET/PUT /api/v1/admin/synthesis-settings`).
2. THE SYSTEM SHALL report "synthesised N of M evidence, K groups remaining" and offer "Continue" and "Widen scope" (doubling the cap).

### Requirement 4: Degradation

#### Acceptance Criteria

1. IF the model fails, times out or returns nothing usable THEN THE SYSTEM SHALL still return the original evidence.
2. WHERE Hybrid Auto allows it THE SYSTEM SHALL escalate to the API profile when no local statement passes the checks, or when "deep analysis" is selected (see `model-registry` spec).

### Requirement 5: Content groups and labels

#### Acceptance Criteria

1. THE SYSTEM SHALL group evidence by content group where labels exist, otherwise by document (`content_taxonomy`, `labeling_rules`, `node_labels`, `node_label_runs`; migration `0013_content_groups.sql`).
2. THE SYSTEM SHALL assign labels by phrase rules automatically, and SHALL treat AI label suggestions as `proposed` until a REVIEWER with `can_review` approves them in batch (`/api/v1/admin/labels/*`).
3. THE SYSTEM SHALL cap AI labelling with `ai_label_budget`.

### Requirement 6: Disclosure

#### Acceptance Criteria

1. THE SYSTEM SHALL tell the user when external AI was used (`external_ai_used`) and when usage was limited (`ai_limited`).
2. THE SYSTEM SHALL state that automatic checks do not replace legal review.
