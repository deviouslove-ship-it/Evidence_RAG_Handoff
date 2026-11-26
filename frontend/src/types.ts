export type AmendmentState =
  | "active"
  | "modified"
  | "repealed"
  | "replaced"
  | "suspended"
  | "not_yet_effective"
  | "unknown";

export interface EvidenceRef {
  evidence_id: string;
  document_id: string;
  document_version_id: string;
  node_id: string;
  document_number?: string;
  title: string;
  label: string;
  quote_exact: string;
  page?: number;
  source_hash: string;
  as_of_date: string;
  amendment_state: AmendmentState;
  viewer_url: string;
  outside_scope: boolean;
  effectivity?: EffectivityView | null;
  /** The uploaded file itself (PDF, or the Word/TXT original), never a derived copy. */
  original_url?: string | null;
}

export interface TextSpan {
  start: number;
  end: number;
}

/** A verbatim slice of the clause text; highlight offsets are relative to `text`. */
export interface Excerpt {
  start: number;
  end: number;
  text: string;
  truncated_before: boolean;
  truncated_after: boolean;
  highlights: TextSpan[];
}

export type ClauseTier = "direct" | "related" | "reference";

export interface AnswerClause {
  evidence_id: string;
  node_id: string;
  label: string;
  heading?: string | null;
  page?: number | null;
  page_end?: number | null;
  tier: ClauseTier;
  match: string;
  matched_terms: string[];
  excerpt: Excerpt;
  topics: string[];
  same_as: string[];
  also_matched: string[];
  effectivity?: EffectivityView | null;
  /** OCR text of a scanned page, confirmed by a reviewer against the scan. */
  ocr?: boolean;
}

export interface DocumentRelation {
  kind: string;
  label: string;
  target_number?: string | null;
  verified: boolean;
  source: string;
}

export interface AnswerDocument {
  document_id: string;
  document_version_id: string;
  doc_type: string;
  doc_type_label: string;
  document_number?: string | null;
  title: string;
  issuing_body?: string | null;
  publication_date?: string | null;
  source_format: string;
  original_filename?: string | null;
  original_url: string;
  viewer_url: string;
  role: ClauseTier;
  kind_label?: string | null;
  relations: DocumentRelation[];
  effectivity?: EffectivityView | null;
  clauses: AnswerClause[];
  more_clauses: number;
}

export interface ChatAnswer {
  outcome: "direct" | "related_only" | "not_found";
  understood_phrases: string[];
  summary: string;
  points: string[];
  topics: Array<{ name: string; references: string[]; evidence_ids: string[] }>;
  notes: string[];
  counts: Record<string, number>;
  result_set_id?: string | null;
}

export type VerificationState = "verified" | "unverified" | "not_found";

/** Both effectivity axes at the requested date (design §4). */
export interface EffectivityView {
  status: AmendmentState;
  verification: VerificationState;
  level: "document" | "node";
  as_of_date?: string | null;
  notes: string[];
  verification_source?: string | null;
  verified_by?: string | null;
  verified_at?: string | null;
  pending_proposals: number;
  clause_level_reviewed: boolean;
  data_date?: string | null;
}

export interface Claim {
  text: string;
  evidence_ids: string[];
  status: string;
}

export interface EvidenceGroup {
  group_id: string;
  purpose: string;
  evidence_ids: string[];
  roles: string[];
}

export interface QueryResponse {
  request_id: string;
  query_id: string;
  run_id: string;
  effective_mode: string;
  status: "evidence_found" | "conditional" | "insufficient" | "conflicting";
  source_scope: {
    scope_mode: "SELECTED" | "ALL_AUTHORIZED";
    category_ids: string[];
    document_types: string[];
    as_of_date: string;
  };
  evidence: EvidenceRef[];
  evidence_groups: EvidenceGroup[];
  claims: Claim[];
  missing_information: string[];
  suggestions: Claim[];
  coverage_checks: Record<string, string>;
  facts_revision: string;
  snapshot_revision?: string;
  answer_generated: boolean;
  ai_selection_applied?: boolean;
  external_ai_used?: boolean;
  ai_limited?: boolean;
  explanation_unavailable: boolean;
  disclaimer: string;
  /** One entry per document with its relevant clauses (absent on older payloads). */
  documents?: AnswerDocument[];
  answer?: ChatAnswer | null;
}

export interface AnalyzeResponse {
  request_id: string;
  query_id: string;
  run_id: string;
  facts_revision: string;
  understood_as: string;
  facts: Array<{
    key: string;
    value: string;
    status: "user_confirmed" | "extracted_unconfirmed" | "inferred_uncertain";
    source?: string | null;
  }>;
  missing_information: string[];
  aspects: string[];
  query_rewrites: string[];
}

export interface UserInfo {
  id: string;
  username: string;
  display_name: string;
  roles: string[];
  permissions: string[];
  must_change_password: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: UserInfo;
}

export interface AuthorizedCategory {
  id: string;
  code: string;
  name: string;
  remote_processing_allowed: boolean;
  document_count?: number;
  created_at?: string;
}

export interface PdfDraftListItem {
  document_id: string;
  document_version_id: string;
  detected_issue_date?: string | null;
  detected_effective_from?: string | null;
  detected_effective_quote?: string | null;
  title: string;
  doc_type: string;
  document_number?: string | null;
  status: string;
  sha256: string;
  page_count: number;
  open_review_tasks: number;
  source_review_revision?: number;
}

export type AdminDocumentAvailability = "active" | "suspended" | "deleted";
export type AdminDocumentAction = "suspend" | "resume" | "delete" | "restore";

export interface AdminDocumentSummary {
  id: string;
  title: string;
  doc_type: string;
  document_number: string | null;
  issuing_body: string | null;
  publication_date: string | null;
  review_status: "draft" | "pending_review" | "approved" | "rejected";
  effectivity: AmendmentState | null;
  availability: AdminDocumentAvailability;
  version_id: string;
  version_number: number;
  can_read: boolean;
  can_edit: boolean;
}

export interface AdminDocumentList {
  items: AdminDocumentSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminDocumentMetadata {
  title: string;
  doc_type: string;
  document_number: string | null;
  issuing_body: string | null;
  publication_date: string | null;
  effective_from: string | null;
  official_url: string | null;
}

export interface AdminDocumentDetail {
  document: AdminDocumentSummary;
  versions: Array<{
    id: string;
    version_number: number;
    review_status: AdminDocumentSummary["review_status"];
    publication_date: string | null;
    source_format: string | null;
    original_filename: string | null;
    retired: boolean;
  }>;
  categories: Array<Pick<AuthorizedCategory, "id" | "name">>;
  page_count: number;
  node_count: number;
  node_page_size: number;
  nodes: Array<{
    id: string;
    parent_id: string | null;
    node_type: string;
    label: string | null;
    path: string;
    text: string;
    page_start: number | null;
    page_end: number | null;
  }>;
  page: {
    page_number: number;
    text: string | null;
    extraction_method: string;
    text_quality: string;
    reviewed: boolean;
    diagnostics?: { flags?: string[] } | null;
  } | null;
  embedding: { indexed_nodes: number; total_nodes: number; index_ready: boolean };
  history: Array<{
    action: string;
    occurred_at: string;
    actor: string | null;
    metadata: Record<string, unknown>;
  }>;
  revision: number;
  official_url: string | null;
  effective_from: string | null;
  original_filename: string | null;
  open_review_tasks: number;
  can_submit: boolean;
  can_review: boolean;
}

export type AdminDocumentPatch = Partial<AdminDocumentMetadata> & {
  revision: number;
  ocr_page?: { page_number: number; text: string };
};

export interface AdminUserItem {
  id: string;
  username: string;
  review_category_ids?: string[];
  display_name: string;
  roles: string[];
  category_ids: string[];
  must_change_password: boolean;
  disabled: boolean;
  remote_ai_allowed?: boolean;
  last_login_at?: string | null;
  created_at: string;
}

export interface ModelRegistryState {
  profiles: Array<{
    id: string;
    profile_id: string;
    adapter: string;
    endpoint: string;
    provider_approved: boolean;
    model_id: string;
    revision: string;
    capabilities: string[];
    privacy_zone: string;
    secret_ref?: string | null;
    fallback: string[];
    health: string;
    params?: {
      temperature?: number;
      top_p?: number;
      max_tokens?: number;
      response_format?: { type: string };
      reasoning_effort?: string;
      token_limit_field?: string;
      dimensions?: number;
      ollama_native?: boolean;
      think?: boolean | null;
      num_ctx?: number;
    };
    input_price_per_mtok?: number | null;
    output_price_per_mtok?: number | null;
    daily_cost_limit?: number | null;
    monthly_cost_limit?: number | null;
  }>;
  routes: Array<{
    mode: string;
    stage: string;
    profile_id: string;
    fallback: string[];
    escalation_profile_id?: string | null;
  }>;
  stage_policies?: StagePolicy[];
  usage?: Array<{
    profile_id: string;
    calls_today: number;
    calls_month: number;
    cost_today: number;
    cost_month: number;
    escalations_month: number;
  }>;
  stages?: Array<{ stage: string; active: boolean; escalation_allowed: boolean }>;
  /** Operating mode of the server (LOCAL or API); only its assignments are used. */
  effective_mode?: string;
  supported_stages?: string[];
  /** Whether a typed API key can be stored on this server. */
  secret_store?: { available: boolean };
}
export interface EmbeddingIndexInfo {
  id: string;
  model_id: string;
  revision: string;
  dimensions: number;
  profile_id: string | null;
  status: string;
  is_active: boolean;
  /** active | building | paused | failed | ready | retired */
  state: string;
  node_count: number;
  vectors?: number;
  storage: string | null;
  index_revision?: number;
  created_at?: string | null;
  completed_at?: string | null;
  activated_at?: string | null;
  retired_at?: string | null;
  verified_at?: string | null;
  last_error?: string | null;
}

export interface EmbeddingJob {
  id: string;
  index_id: string;
  profile_id: string;
  model_id?: string | null;
  dimensions?: number | null;
  kind: "rebuild" | "catch_up";
  status: "queued" | "running" | "paused" | "failed" | "completed" | "cancelled";
  phase: "embedding" | "indexing" | "verifying" | "switching" | "done";
  batch_size: number;
  total_nodes: number;
  done_nodes: number;
  remaining_nodes: number;
  embedded_nodes: number;
  percent: number;
  rate_per_minute: number | null;
  eta_seconds: number | null;
  failed_batches: number;
  consecutive_failures: number;
  last_error: string | null;
  errors: Array<{ at: string; code: string; detail?: string | null }>;
  next_attempt_at: string | null;
  created_at: string | null;
  started_at: string | null;
  updated_at: string | null;
  finished_at: string | null;
}

export interface EmbeddingProfileInfo {
  profile_id: string;
  model_id: string;
  revision: string;
  privacy_zone: string;
  health: string;
  provider_approved: boolean;
  requested_dimensions?: number | null;
}

export interface EmbeddingOverview {
  mode: string;
  remote_embedding_allowed: boolean;
  route_profile_id: string | null;
  active_index: EmbeddingIndexInfo | null;
  eligible_nodes: number;
  missing_in_active: number | null;
  change: {
    detected: boolean;
    reason?: "no_active_index" | "route_changed" | "profile_model_changed";
    profile_id?: string | null;
    model_id?: string | null;
    pending_nodes?: number;
    open_job_id?: string | null;
  };
  profiles: EmbeddingProfileInfo[];
  indices: EmbeddingIndexInfo[];
  jobs: EmbeddingJob[];
  worker: { enabled: boolean; alive: boolean; current_job_id?: string | null;
    last_poll_at?: string | null; last_error?: string | null };
}

export interface EmbeddingPreflight {
  ok: boolean;
  profile_id: string;
  model_id: string;
  revision: string;
  privacy_zone: string;
  rebuild: boolean;
  checks: Array<{ key: string; ok: boolean; detail: string | null; code: string | null }>;
  problems: string[];
  dimensions?: number;
  storage?: string | null;
  latency_ms?: number;
  eligible_nodes?: number;
  already_embedded?: number;
  to_embed?: number;
  kind?: "rebuild" | "catch_up";
  target_index_id?: string | null;
  target_index_status?: string | null;
  estimated_seconds?: number;
  open_job?: EmbeddingJob | null;
  probe_status?: string;
}

export interface StagePolicy {
  mode: string;
  stage: string;
  max_attempts: number;
  max_output_tokens?: number | null;
  timeout_seconds?: number | null;
  max_concurrency?: number | null;
  updated_at?: string;
}

export interface AuditEventsResponse {
  chain: {
    valid: boolean | null;
    complete?: boolean;
    checked: number;
    broken_at?: number | null;
  };
  events: Array<{
    id: string;
    principal_id?: string | null;
    username?: string | null;
    action: string;
    target_type: string;
    target_id?: string | null;
    metadata: Record<string, unknown>;
    previous_hash?: string | null;
    event_hash: string;
    occurred_at: string;
  }>;
}

/** Search v1 contract (GET /api/v1/search). */
export type SearchMode = "auto" | "phrase" | "keywords";

export type SearchMatchType =
  | "exact_phrase"
  | "phrase_folded"
  | "all_terms"
  | "any_term";

export type SearchEmptyReason =
  | "NO_AUTHORIZED_DOCUMENTS"
  | "NO_RESULTS"
  | "PHRASE_NOT_FOUND";

export type EffectivitySnapshotStatus = "ok" | "stale";

export interface SearchHighlight {
  start: number;
  end: number;
}

export interface SearchClause {
  node_id: string;
  label: string;
  page?: number | null;
  match_type: SearchMatchType;
  amendment_state: AmendmentState;
  amendment_as_of?: string | null;
  quote_exact: string;
  snippet?: string | null;
  snippet_start?: number | null;
  highlights?: SearchHighlight[] | null;
  viewer_url?: string | null;
  source_hash?: string | null;
  effectivity?: EffectivityView | null;
}

export interface SearchDocumentResult {
  document_id: string;
  document_version_id: string;
  document_number?: string | null;
  title: string;
  doc_type: string;
  issuing_body?: string | null;
  official_url?: string | null;
  matched_clause_count: number;
  clause_page: number;
  clause_page_size: number;
  has_more_clauses: boolean;
  clauses: SearchClause[];
  effectivity?: EffectivityView | null;
}

export interface SearchResponse {
  query: {
    original: string;
    phrase?: string | null;
    mode: SearchMode;
    normalization_revision?: string;
  };
  phrase_found?: boolean | null;
  totals: {
    documents: number;
    clauses: number;
    approximate_matches_hidden: number;
    /** More than `count_cap` clauses matched; counts cover only the clauses examined. */
    capped?: boolean;
    count_cap?: number | null;
  };
  page: number;
  page_size: number;
  has_more: boolean;
  effectivity_snapshot_status: EffectivitySnapshotStatus;
  results: SearchDocumentResult[];
  approximate?: { collapsed: boolean; total_clauses: number } | null;
  empty_reason?: SearchEmptyReason | null;
  clause_level_warning?: string | null;
  data_date?: string | null;
}

export type PageTextSourceKind = "native" | "ocr_reviewed" | "ocr_ai_unverified";

export type PageTextTaskStatus =
  | "queued"
  | "running"
  | "ready"
  | "failed"
  | "cancelled"
  | "stale"
  | "applied"
  | "rejected";

export interface PageTextResponse {
  task_id?: string | null;
  status: PageTextTaskStatus;
  document_id: string;
  version_id: string;
  document_title: string;
  document_number?: string | null;
  page_number: number;
  total_pages: number;
  source_kind: PageTextSourceKind;
  verified: boolean;
  warning?: string | null;
  page_text?: string | null;
  error_code?: string | null;
  pdf_url: string;
  deduplicated?: boolean;
  warnings?: string[];
  unreadable?: string[];
}

export interface OcrAiDiffLine {
  op: "equal" | "delete" | "insert";
  text: string;
}

export interface AdminOcrAiProposal {
  proposal_id: string;
  purpose: "admin_correction" | "user_page_text";
  document_id: string;
  version_id: string;
  page_number: number;
  source_review_revision: number;
  status: PageTextTaskStatus;
  stale: boolean;
  candidate?: {
    blocks: Array<{ kind: "text" | "table"; text?: string | null; rows?: string[][] | null }>;
    warnings: string[];
    unreadable: string[];
  } | null;
  candidate_text?: string | null;
  current_page_text?: string | null;
  diff?: OcrAiDiffLine[] | null;
  error_code?: string | null;
  applied_version_id?: string | null;
  note?: string | null;
  deduplicated?: boolean;
}

export interface AdminOcrAiApplyResponse {
  version_id: string;
  revision: number;
  status: string;
  proposal: AdminOcrAiProposal;
}

/**
 * Document comparison (Task C1/C2 backend contract, frozen). Field names and casing
 * mirror the OpenAPI schemas of /api/v1/compare/*, /api/v1/documents/{id}/versions and
 * /api/v1/nodes/{id}/diff exactly; dates are ISO strings, UUIDs are strings.
 */
export type CompareMode = "versions" | "amendment_pair" | "cross_document";

export type CompareChangeKind =
  | "unchanged"
  | "modified"
  | "moved_or_renumbered"
  | "added"
  | "removed";

export type CompareAlignmentMethod =
  | "explicit_amendment"
  | "structural_key"
  | "semantic_lexical";

export type CompareImpactLevel = "high" | "medium" | "low";

export type CompareDiffOp = "equal" | "delete" | "insert";

/** OpenAPI `DocumentMeta`: identity of one compared/picked document. */
export interface DocumentMeta {
  id: string;
  title: string;
  document_number: string | null;
  doc_type: string;
  issuing_body: string | null;
}

/** OpenAPI `VersionInfo`. `reviewed_at` is the DB column (never `approved_at`). */
export interface VersionInfo {
  id: string;
  version_number: number;
  publication_date: string | null;
  effective_from: string | null;
  /** retired_at IS NULL — the version currently in force. */
  is_current: boolean;
  based_on_version_id: string | null;
  reviewed_at: string | null;
}

export type RelatedAmendmentDirection =
  | "amends_this_document"
  | "amended_by_this_document";

export type RelatedAmendmentAction = "add" | "modify" | "replace";

/** OpenAPI `RelatedAmendmentDocument`: another ALLOWED document linked by approved links. */
export interface RelatedAmendmentDocument {
  id: string;
  title: string;
  document_number: string | null;
  doc_type: string;
  issuing_body: string | null;
  directions: RelatedAmendmentDirection[];
  actions: RelatedAmendmentAction[];
}

/** GET /api/v1/documents/{id}/versions — approved + verified versions, DESC. */
export interface DocumentVersionsResponse {
  document: DocumentMeta;
  versions: VersionInfo[];
  related_amendment_documents: RelatedAmendmentDocument[];
}

/** OpenAPI `SideView`: one stitched logical node of a compared side. */
export interface SideView {
  /** Primary (first member) node id; citation id is "ev_" + node_id. */
  node_id: string;
  member_node_ids: string[];
  citation_label: string | null;
  structural_key: string;
  text_original: string;
  page_start: number | null;
  page_end: number | null;
}

export interface DiffSegmentView {
  op: CompareDiffOp;
  text: string;
}

/** A deadline/amount span whose (value, unit) key is absent on the other side. */
export interface SpanView {
  value_num: number;
  unit_normalized: string;
  raw_text: string;
}

/** OpenAPI `ChangeSignalsView`. `dates_changed` entries are [day, month, year]. */
export interface ChangeSignalsView {
  deadlines_changed: SpanView[];
  amounts_changed: SpanView[];
  dates_changed: Array<[number, number, number]>;
  modality_shifted: boolean;
  exception_changed: boolean;
  impact_level: CompareImpactLevel;
}

/** OpenAPI `AmendmentLinkView`; non-null only for explicit_amendment alignment. */
export interface AmendmentLinkView {
  action: string | null;
  valid_from: string | null;
  source_quote: string | null;
}

/** OpenAPI `ComparisonItem`. Exactly one side is null ⇔ added/removed. */
export interface ComparisonItem {
  item_key: string;
  change_kind: CompareChangeKind;
  /** Meaningful ONLY for moved_or_renumbered: the text changed too. */
  content_also_modified: boolean;
  /** null ⇔ added/removed (unpaired). */
  alignment_method: CompareAlignmentMethod | null;
  alignment_score: number | null;
  impact_level: CompareImpactLevel;
  signals: ChangeSignalsView;
  amendment_link: AmendmentLinkView | null;
  left: SideView | null;
  right: SideView | null;
  diff_segments: DiffSegmentView[];
}

/** OpenAPI `DocumentSide`: document identity + resolved version + effectivity. */
export interface DocumentSide {
  id: string;
  title: string;
  document_number: string | null;
  doc_type: string;
  issuing_body: string | null;
  version_id: string;
  version_number: number;
  effectivity: EffectivityView;
}

export interface CompareSummary {
  /** ALL aligned pairs, before only_changes filtering. */
  total_items: number;
  added: number;
  removed: number;
  modified: number;
  moved_or_renumbered: number;
  unchanged: number;
  high_impact_changes: number;
  explicit_amendment_links: number;
  deterministic_highlights: string[];
}

/** POST /api/v1/compare/documents request (`extra="forbid"` server-side). */
export interface CompareRequest {
  mode: CompareMode;
  left_document_id: string;
  right_document_id: string;
  /** null/omitted → latest active approved + verified version. */
  left_version_id?: string | null;
  right_version_id?: string | null;
  /** null/omitted → server local today. */
  as_of_date?: string | null;
  only_changes?: boolean;
  include_embeddings?: boolean;
}

/** POST /api/v1/compare/documents response. */
export interface CompareResponse {
  comparison_id: string;
  mode: CompareMode;
  as_of_date: string;
  left_doc: DocumentSide;
  right_doc: DocumentSide;
  summary: CompareSummary;
  items: ComparisonItem[];
  disclaimer: string;
}

export interface NodeVersionRef {
  id: string;
  version_number: number;
}

/** OpenAPI `NodeAmendmentView`: one approved link acting on a node/its document (A5). */
export interface NodeAmendmentView {
  id: string;
  action: string;
  scope: "document" | "node";
  valid_from: string | null;
  source_quote: string | null;
  evidence_source: string;
  source_node_id: string;
  source_label: string | null;
  source_document: DocumentMeta;
}

/** GET /api/v1/nodes/{id}/diff response (spec A5). Missing previous → 200 + message. */
export interface NodeDiffResponse {
  node_id: string;
  document: DocumentMeta;
  version: NodeVersionRef;
  as_of_date: string;
  current: SideView;
  has_previous: boolean;
  previous_version: NodeVersionRef | null;
  previous: SideView | null;
  message: string | null;
  change_kind: CompareChangeKind | null;
  content_also_modified: boolean;
  alignment_method: CompareAlignmentMethod | null;
  alignment_score: number | null;
  impact_level: CompareImpactLevel | null;
  signals: ChangeSignalsView | null;
  diff_segments: DiffSegmentView[];
  amendments: NodeAmendmentView[];
  effectivity: EffectivityView | null;
  disclaimer: string;
}

export type SummarizeFallbackReason =
  | "no_changes"
  | "ai_not_configured"
  | "remote_blocked_by_document_policy"
  | "ai_timeout"
  | "ai_unavailable"
  | "ai_error"
  | "ai_output_rejected";

/** OpenAPI `KeyChangeView`; needs_review points MUST be visibly badged in the UI. */
export interface KeyChangeView {
  point: string;
  item_keys: string[];
  evidence_ids: string[];
  status: "verified" | "needs_review";
  check_notes: string[];
}

/** POST /api/v1/compare/summarize response — always 200 for a valid selection. */
export interface SummarizeResponse {
  comparison_id: string;
  mode_used: "ai" | "deterministic_fallback";
  reason: SummarizeFallbackReason | null;
  executive_summary: string | null;
  summary_status: "verified" | "needs_review" | null;
  key_changes: KeyChangeView[];
  deterministic_highlights: string[];
  external_api_used: boolean;
  ai_limited: boolean;
  disclaimer: string;
}

/** Quick-access preset: SearchPage/DocumentCard "So sánh" opens the compare tab. */
export interface ComparePreset {
  mode: CompareMode;
  leftDocumentId?: string;
  rightDocumentId?: string;
}

/** Vietnamese UI labels shared by the compare page, the diff view and the report. */
export const COMPARE_MODE_LABELS: Record<CompareMode, string> = {
  versions: "So sánh phiên bản",
  amendment_pair: "So sánh gốc – sửa đổi/bổ sung",
  cross_document: "So sánh 2 văn bản cùng chủ đề",
};

export const COMPARE_KIND_LABELS: Record<CompareChangeKind, string> = {
  added: "Thêm mới",
  removed: "Bị bãi bỏ/Xóa",
  modified: "Sửa đổi",
  moved_or_renumbered: "Đổi vị trí/số Điều",
  unchanged: "Không đổi",
};

export const COMPARE_ALIGNMENT_LABELS: Record<CompareAlignmentMethod, string> = {
  explicit_amendment: "Liên kết sửa đổi đã duyệt",
  structural_key: "Khớp số Điều",
  semantic_lexical: "Khớp nội dung",
};

export const COMPARE_IMPACT_LABELS: Record<CompareImpactLevel, string> = {
  high: "Tác động cốt lõi",
  medium: "Tác động trung bình",
  low: "Tác động thấp",
};

export const COMPARE_AMENDMENT_ACTION_LABELS: Record<string, string> = {
  add: "bổ sung",
  modify: "sửa đổi",
  replace: "thay thế",
  repeal: "bãi bỏ",
  repeal_partial: "bãi bỏ một phần",
  suspend: "tạm ngưng",
  commence: "cho hiệu lực",
};
