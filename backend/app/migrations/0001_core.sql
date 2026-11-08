-- Vietnamese Evidence RAG Agent — core schema
-- PostgreSQL is the only persistent database. Apply with the reviewed migration runner.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE review_status AS ENUM ('draft', 'pending_review', 'approved', 'rejected');
CREATE TYPE node_type AS ENUM ('part', 'chapter', 'section', 'article', 'clause', 'point', 'annex', 'paragraph', 'heading');
CREATE TYPE effective_status AS ENUM ('active', 'modified', 'repealed', 'suspended', 'not_yet_effective', 'unknown');
CREATE TYPE job_status AS ENUM ('queued', 'running', 'succeeded', 'failed', 'cancelled');

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  disabled_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE roles (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE user_roles (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_code TEXT NOT NULL REFERENCES roles(code),
  PRIMARY KEY (user_id, role_code)
);

CREATE TABLE categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  code TEXT NOT NULL UNIQUE,
  parent_id UUID REFERENCES categories(id),
  depth INTEGER NOT NULL DEFAULT 0 CHECK (depth >= 0 AND depth <= 10),
  remote_processing_allowed BOOLEAN NOT NULL DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE category_acl (
  category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  can_query BOOLEAN NOT NULL DEFAULT TRUE,
  can_export BOOLEAN NOT NULL DEFAULT FALSE,
  granted_by UUID REFERENCES users(id),
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (category_id, user_id)
);

CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_type TEXT NOT NULL,
  title TEXT NOT NULL,
  document_number TEXT,
  issuing_body TEXT,
  classification_level TEXT NOT NULL DEFAULT 'internal',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);

CREATE TABLE document_acl (
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  can_query BOOLEAN NOT NULL DEFAULT TRUE,
  can_export BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (document_id, user_id)
);

CREATE TABLE document_categories (
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  PRIMARY KEY (document_id, category_id)
);

CREATE TABLE document_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version_number INTEGER NOT NULL CHECK (version_number > 0),
  official_url TEXT,
  publication_date DATE,
  valid_from DATE,
  valid_to DATE,
  original_file_path TEXT NOT NULL,
  original_file_sha256 TEXT NOT NULL CHECK (original_file_sha256 ~ '^[0-9a-f]{64}$'),
  original_filename TEXT NOT NULL,
  captured_at TIMESTAMPTZ,
  review_status review_status NOT NULL DEFAULT 'draft',
  source_review_revision BIGINT NOT NULL DEFAULT 1,
  UNIQUE (document_id, version_number),
  UNIQUE (original_file_sha256)
);

CREATE TABLE source_provenance (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_version_id UUID NOT NULL UNIQUE REFERENCES document_versions(id) ON DELETE CASCADE,
  official_url TEXT,
  publisher_domain TEXT,
  captured_at TIMESTAMPTZ,
  redirect_chain JSONB NOT NULL DEFAULT '[]'::jsonb,
  authenticity_reviewer UUID REFERENCES users(id),
  fetched_checksum TEXT,
  verified_at TIMESTAMPTZ
);

CREATE TABLE source_pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL CHECK (page_number > 0),
  width NUMERIC NOT NULL,
  height NUMERIC NOT NULL,
  rotation INTEGER NOT NULL DEFAULT 0,
  crop_box JSONB,
  media_box JSONB,
  extraction_method TEXT NOT NULL,
  text_quality TEXT NOT NULL,
  UNIQUE (document_version_id, page_number)
);

CREATE TABLE source_spans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  page_id UUID NOT NULL REFERENCES source_pages(id) ON DELETE CASCADE,
  original_offset INTEGER NOT NULL CHECK (original_offset >= 0),
  original_length INTEGER NOT NULL CHECK (original_length > 0),
  quads JSONB NOT NULL DEFAULT '[]'::jsonb,
  text_original TEXT NOT NULL
);

CREATE TABLE document_nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  document_version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  parent_id UUID REFERENCES document_nodes(id),
  node_type node_type NOT NULL,
  label_original TEXT,
  path TEXT NOT NULL,
  text_original TEXT NOT NULL,
  text_indexed TEXT NOT NULL,
  text_normalized TEXT NOT NULL,
  text_folded TEXT NOT NULL,
  page_start INTEGER,
  page_end INTEGER,
  source_span_id UUID REFERENCES source_spans(id),
  parse_confidence NUMERIC NOT NULL CHECK (parse_confidence BETWEEN 0 AND 1),
  review_status review_status NOT NULL DEFAULT 'draft',
  node_effective_from DATE,
  node_effective_to DATE,
  applicability_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE node_references (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_node_id UUID NOT NULL REFERENCES document_nodes(id) ON DELETE CASCADE,
  target_node_id UUID REFERENCES document_nodes(id),
  target_expression TEXT NOT NULL,
  resolution_state TEXT NOT NULL CHECK (resolution_state IN ('resolved', 'unresolved', 'ambiguous')),
  verified_by UUID REFERENCES users(id),
  verified_at TIMESTAMPTZ
);

CREATE TABLE node_amendments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_node_id UUID NOT NULL REFERENCES document_nodes(id) ON DELETE CASCADE,
  target_node_id UUID REFERENCES document_nodes(id),
  action TEXT NOT NULL CHECK (action IN ('modify', 'replace', 'add', 'repeal', 'suspend')),
  valid_from DATE NOT NULL,
  valid_to DATE,
  evidence_source TEXT NOT NULL,
  review_status review_status NOT NULL DEFAULT 'draft',
  reviewed_by UUID REFERENCES users(id),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE curator_review_tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  node_id UUID REFERENCES document_nodes(id) ON DELETE CASCADE,
  reason TEXT NOT NULL,
  risk TEXT NOT NULL CHECK (risk IN ('low', 'medium', 'high')),
  status TEXT NOT NULL DEFAULT 'open',
  assigned_to UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE effectivity_snapshot_revisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  revision BIGINT NOT NULL UNIQUE,
  source_review_revision BIGINT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT FALSE,
  staged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ,
  published_by UUID REFERENCES users(id)
);
CREATE UNIQUE INDEX one_active_effectivity_snapshot ON effectivity_snapshot_revisions(is_active) WHERE is_active;

CREATE TABLE node_effective_intervals (
  snapshot_revision_id UUID NOT NULL REFERENCES effectivity_snapshot_revisions(id) ON DELETE CASCADE,
  node_id UUID NOT NULL REFERENCES document_nodes(id) ON DELETE CASCADE,
  valid_from DATE NOT NULL,
  valid_to DATE,
  effective_status effective_status NOT NULL,
  resolved_node_id UUID REFERENCES document_nodes(id),
  amendment_chain JSONB NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (snapshot_revision_id, node_id, valid_from),
  CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE INDEX node_effective_intervals_lookup ON node_effective_intervals(snapshot_revision_id, node_id, valid_from);

CREATE TABLE lexical_search_index (
  document_node_id UUID PRIMARY KEY REFERENCES document_nodes(id) ON DELETE CASCADE,
  search_vector tsvector NOT NULL,
  tokenizer_revision TEXT NOT NULL,
  index_revision BIGINT NOT NULL
);
CREATE INDEX lexical_search_index_gin ON lexical_search_index USING GIN(search_vector);

CREATE TABLE embedding_indices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id TEXT NOT NULL,
  model_revision TEXT NOT NULL,
  tokenizer_revision TEXT NOT NULL,
  dimensions INTEGER NOT NULL CHECK (dimensions > 0),
  index_revision BIGINT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (model_id, model_revision, tokenizer_revision, dimensions, index_revision)
);

CREATE TABLE node_embeddings (
  embedding_index_id UUID NOT NULL REFERENCES embedding_indices(id) ON DELETE CASCADE,
  document_node_id UUID NOT NULL REFERENCES document_nodes(id) ON DELETE CASCADE,
  embedding vector(768),
  PRIMARY KEY (embedding_index_id, document_node_id)
);

CREATE TABLE evidence_groups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id UUID NOT NULL,
  citation_id UUID,
  purpose TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evidence_group_members (
  evidence_group_id UUID NOT NULL REFERENCES evidence_groups(id) ON DELETE CASCADE,
  document_node_id UUID NOT NULL REFERENCES document_nodes(id),
  role TEXT NOT NULL,
  required_aspect BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (evidence_group_id, document_node_id)
);

CREATE TABLE claim_aspect_links (
  claim_id UUID NOT NULL,
  aspect TEXT NOT NULL,
  evidence_group_id UUID NOT NULL REFERENCES evidence_groups(id) ON DELETE CASCADE,
  PRIMARY KEY (claim_id, aspect)
);

CREATE TABLE query_fact_revisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id UUID NOT NULL,
  revision TEXT NOT NULL,
  submission_snapshot JSONB NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft', 'confirmed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (query_id, revision)
);

CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  principal_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  persistence_state TEXT NOT NULL CHECK (persistence_state IN ('ephemeral', 'retained')),
  retention_policy_id TEXT,
  expires_at TIMESTAMPTZ,
  memory_revision BIGINT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fact_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  revision BIGINT NOT NULL,
  facts JSONB NOT NULL,
  UNIQUE (conversation_id, revision)
);

CREATE TABLE providers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  adapter TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  approved BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE model_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_key TEXT NOT NULL UNIQUE,
  provider_id UUID NOT NULL REFERENCES providers(id),
  model_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  capabilities JSONB NOT NULL,
  privacy_zone TEXT NOT NULL,
  params JSONB NOT NULL DEFAULT '{}'::jsonb,
  secret_ref TEXT,
  fallback JSONB NOT NULL DEFAULT '[]'::jsonb,
  health TEXT NOT NULL DEFAULT 'unknown',
  license_check_status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE stage_routes (
  mode TEXT NOT NULL CHECK (mode IN ('API', 'LOCAL')),
  stage TEXT NOT NULL,
  profile_id UUID NOT NULL REFERENCES model_profiles(id),
  fallback JSONB NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (mode, stage)
);

CREATE TABLE security_policies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  policy_key TEXT NOT NULL UNIQUE,
  payload JSONB NOT NULL,
  revision BIGINT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type TEXT NOT NULL,
  status job_status NOT NULL DEFAULT 'queued',
  idempotency_key TEXT NOT NULL UNIQUE,
  payload JSONB NOT NULL,
  result JSONB,
  lease_owner TEXT,
  lease_expires_at TIMESTAMPTZ,
  heartbeat_at TIMESTAMPTZ,
  cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
  retry_count INTEGER NOT NULL DEFAULT 0,
  error_redacted TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX jobs_claim ON jobs(status, created_at) WHERE status IN ('queued', 'running');

CREATE TABLE job_attempts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  attempt_number INTEGER NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  outcome TEXT,
  error_redacted TEXT,
  UNIQUE (job_id, attempt_number)
);

CREATE TABLE evaluation_corpora (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  corpus_key TEXT NOT NULL UNIQUE,
  split_revision TEXT NOT NULL,
  locked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE evaluation_cases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  corpus_id UUID NOT NULL REFERENCES evaluation_corpora(id),
  case_key TEXT NOT NULL,
  scenario_group_id TEXT NOT NULL,
  question TEXT NOT NULL,
  expected_answer TEXT,
  expected_abstention BOOLEAN NOT NULL DEFAULT FALSE,
  evidence JSONB NOT NULL,
  source_hash TEXT NOT NULL,
  review_status review_status NOT NULL DEFAULT 'draft',
  reviewed_by UUID REFERENCES users(id),
  UNIQUE (corpus_id, case_key)
);

CREATE TABLE evaluation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  corpus_id UUID NOT NULL REFERENCES evaluation_corpora(id),
  candidate_revision TEXT NOT NULL,
  metrics JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE feedback_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  principal_id UUID NOT NULL REFERENCES users(id),
  citation_id UUID,
  feedback_type TEXT NOT NULL,
  detail TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  principal_id UUID,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  previous_hash TEXT,
  event_hash TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_timeline ON audit_events(occurred_at DESC);

-- ACL is enforced inside the retrieval relation, not by the API caller.
CREATE VIEW authorized_categories AS
SELECT ca.category_id, ca.user_id
FROM category_acl ca
JOIN categories c ON c.id = ca.category_id
JOIN users u ON u.id = ca.user_id
WHERE ca.can_query
  AND c.deleted_at IS NULL
  AND u.disabled_at IS NULL
  AND current_setting('app.user_id', true) <> ''
  AND ca.user_id = current_setting('app.user_id', true)::uuid;

CREATE VIEW authorized_nodes AS
SELECT DISTINCT n.*
FROM document_nodes n
JOIN document_versions dv ON dv.id = n.document_version_id AND dv.review_status = 'approved'
JOIN documents d ON d.id = n.document_id AND d.deleted_at IS NULL
JOIN document_categories dc ON dc.document_id = d.id
JOIN authorized_categories ac ON ac.category_id = dc.category_id
WHERE current_setting('app.user_id', true) <> ''
  AND ac.user_id = current_setting('app.user_id', true)::uuid
  AND n.review_status = 'approved'
UNION
SELECT DISTINCT n.*
FROM document_nodes n
JOIN document_versions dv ON dv.id = n.document_version_id AND dv.review_status = 'approved'
JOIN documents d ON d.id = n.document_id AND d.deleted_at IS NULL
JOIN document_acl da ON da.document_id = d.id
WHERE da.can_query
  AND da.user_id = current_setting('app.user_id', true)::uuid
  AND n.review_status = 'approved';

REVOKE ALL ON authorized_nodes FROM PUBLIC;
