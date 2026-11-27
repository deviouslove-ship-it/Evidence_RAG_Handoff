-- Phase 2: Configurable legal authority hierarchy, async conflict scan runs,
-- conflict findings, and extending node_amendments.proposed_by for conflict review drafts.

CREATE TABLE legal_authority_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_code TEXT NOT NULL UNIQUE,
  doc_type TEXT NOT NULL,
  issuing_body_pattern TEXT,
  authority_rank INTEGER NOT NULL CHECK (authority_rank BETWEEN 1 AND 1000),
  authority_tier_label TEXT NOT NULL,
  is_ambiguous_without_issuer BOOLEAN NOT NULL DEFAULT FALSE,
  match_priority INTEGER NOT NULL DEFAULT 100,
  note TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  updated_by UUID REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX legal_authority_rules_lookup
  ON legal_authority_rules (doc_type, match_priority ASC)
  WHERE is_active;

-- Default reference hierarchy based on Vietnam Law on Promulgation of Legal Documents.
-- Administrators can customize rules for internal or domain-specific documents.
INSERT INTO legal_authority_rules (
  rule_code, doc_type, issuing_body_pattern, authority_rank,
  authority_tier_label, is_ambiguous_without_issuer, match_priority, note
) VALUES
  (
    'code_national_assembly', 'code', NULL, 10,
    'Bộ luật (Quốc hội)', FALSE, 100,
    'Bộ luật do Quốc hội ban hành'
  ),
  (
    'law_national_assembly', 'law', NULL, 10,
    'Luật (Quốc hội)', FALSE, 100,
    'Luật do Quốc hội ban hành'
  ),
  (
    'resolution_ubtvqh', 'resolution', '(uy ban thuong vu quoc hoi|ubtvqh)', 20,
    'Nghị quyết (Ủy ban Thường vụ Quốc hội)', FALSE, 10,
    'Nghị quyết của Ủy ban Thường vụ Quốc hội'
  ),
  (
    'resolution_national_assembly', 'resolution', '(^| )quoc hoi($| )', 15,
    'Nghị quyết (Quốc hội)', FALSE, 20,
    'Nghị quyết của Quốc hội'
  ),
  (
    'resolution_government', 'resolution', '(^| )chinh phu($| )', 30,
    'Nghị quyết (Chính phủ)', FALSE, 30,
    'Nghị quyết của Chính phủ'
  ),
  (
    'resolution_hdnd_provincial', 'resolution', '(hoi dong nhan dan|hdnd).*(tinh|thanh pho)', 50,
    'Nghị quyết (HĐND cấp tỉnh)', FALSE, 50,
    'Nghị quyết của Hội đồng nhân dân cấp tỉnh'
  ),
  (
    'resolution_hdnd_local', 'resolution', '(hoi dong nhan dan|hdnd)', 60,
    'Nghị quyết (HĐND cấp huyện/xã/đơn vị)', FALSE, 60,
    'Nghị quyết của Hội đồng nhân dân cấp cơ sở'
  ),
  (
    'resolution_fallback_ambiguous', 'resolution', NULL, 50,
    'Nghị quyết (cần xác định cơ quan ban hành)', TRUE, 900,
    'Không tự suy đoán thứ bậc khi thiếu hoặc không khớp cơ quan ban hành'
  ),
  (
    'ordinance_ubtvqh', 'ordinance', NULL, 20,
    'Pháp lệnh (Ủy ban Thường vụ Quốc hội)', FALSE, 100,
    'Pháp lệnh của Ủy ban Thường vụ Quốc hội'
  ),
  (
    'decision_president', 'decision', 'chu tich nuoc', 25,
    'Quyết định (Chủ tịch nước)', FALSE, 10,
    'Quyết định của Chủ tịch nước'
  ),
  (
    'decision_prime_minister', 'decision', 'thu tuong', 35,
    'Quyết định (Thủ tướng Chính phủ)', FALSE, 20,
    'Quyết định của Thủ tướng Chính phủ'
  ),
  (
    'decision_ministry_or_province', 'decision',
    '(^bo |lien bo |bo truong|co quan ngang bo|uy ban nhan dan (tinh|thanh pho)|ubnd (tinh|thanh pho)|hoi dong nhan dan (tinh|thanh pho)|hdnd (tinh|thanh pho))',
    50, 'Quyết định (Bộ / cơ quan ngang Bộ / UBND cấp tỉnh)', FALSE, 30,
    'Quyết định của Bộ trưởng, Thủ trưởng cơ quan ngang Bộ hoặc cấp tỉnh'
  ),
  (
    'decision_department_or_local', 'decision',
    '(giam doc|^so |uy ban nhan dan|ubnd|hoi dong nhan dan|hdnd|cuc |chi cuc|don vi|vien truong|hieu truong|tong giam doc)',
    60, 'Quyết định (Cấp Sở / Huyện / Đơn vị nội bộ)', FALSE, 40,
    'Quyết định của cấp sở, cấp huyện hoặc đơn vị nội bộ'
  ),
  (
    'decision_fallback_ambiguous', 'decision', NULL, 50,
    'Quyết định (cần xác định cơ quan ban hành)', TRUE, 900,
    'Không tự suy đoán thứ bậc khi thiếu hoặc không khớp cơ quan ban hành'
  ),
  (
    'decree_government', 'decree', NULL, 30,
    'Nghị định (Chính phủ)', FALSE, 100,
    'Nghị định của Chính phủ'
  ),
  (
    'joint_circular_ministries', 'joint_circular', NULL, 40,
    'Thông tư liên tịch', FALSE, 100,
    'Thông tư liên tịch giữa các Bộ, cơ quan ngang Bộ hoặc cơ quan tư pháp'
  ),
  (
    'circular_ministry', 'circular', NULL, 40,
    'Thông tư (Bộ / cơ quan ngang Bộ)', FALSE, 100,
    'Thông tư của Bộ trưởng, Thủ trưởng cơ quan ngang Bộ'
  ),
  (
    'directive_prime_minister', 'directive', 'thu tuong', 35,
    'Chỉ thị (Thủ tướng Chính phủ)', FALSE, 20,
    'Chỉ thị của Thủ tướng Chính phủ'
  ),
  (
    'directive_ministry_or_province', 'directive',
    '(^bo |lien bo |bo truong|co quan ngang bo|uy ban nhan dan (tinh|thanh pho)|ubnd (tinh|thanh pho)|hoi dong nhan dan (tinh|thanh pho)|hdnd (tinh|thanh pho))',
    50, 'Chỉ thị (Bộ / cơ quan ngang Bộ / UBND cấp tỉnh)', FALSE, 30,
    'Chỉ thị của Bộ, cơ quan ngang Bộ hoặc cấp tỉnh'
  ),
  (
    'directive_department_or_local', 'directive',
    '(giam doc|^so |uy ban nhan dan|ubnd|hoi dong nhan dan|hdnd|cuc |chi cuc|don vi|vien truong|hieu truong|tong giam doc)',
    60, 'Chỉ thị (Cấp Sở / Huyện / Đơn vị nội bộ)', FALSE, 40,
    'Chỉ thị của cấp sở, cấp huyện hoặc đơn vị nội bộ'
  ),
  (
    'directive_fallback_ambiguous', 'directive', NULL, 50,
    'Chỉ thị (cần xác định cơ quan ban hành)', TRUE, 900,
    'Không tự suy đoán thứ bậc khi thiếu hoặc không khớp cơ quan ban hành'
  ),
  (
    'consolidated_fallback_ambiguous', 'consolidated', NULL, 100,
    'Văn bản hợp nhất (cần đối chiếu văn bản gốc)', TRUE, 900,
    'Văn bản hợp nhất cần đối chiếu các văn bản gốc và sửa đổi liên quan'
  ),
  (
    'other_fallback_ambiguous', 'other', NULL, 500,
    'Văn bản khác (chưa xác định thứ bậc)', TRUE, 900,
    'Loại văn bản khác chưa xác định thứ bậc hiệu lực tự động'
  );

CREATE TABLE conflict_review_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  requested_by UUID NOT NULL REFERENCES users(id),
  request_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN (
    'queued', 'running', 'completed', 'failed', 'cancelled', 'expired'
  )),
  scope_json JSONB NOT NULL,
  as_of_date DATE NOT NULL,
  use_ai BOOLEAN NOT NULL DEFAULT FALSE,
  model_profile_id UUID REFERENCES model_profiles(id) ON DELETE SET NULL,
  limits_json JSONB NOT NULL,
  progress_total INTEGER NOT NULL DEFAULT 0,
  progress_done INTEGER NOT NULL DEFAULT 0,
  summary_json JSONB,
  error_code TEXT,
  error_message TEXT,
  lease_token UUID,
  lease_expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ NOT NULL,
  UNIQUE (requested_by, request_id)
);

-- Enforce at most one running conflict scan system-wide to protect LAN Portable resources.
CREATE UNIQUE INDEX conflict_review_runs_one_running
  ON conflict_review_runs ((TRUE))
  WHERE status = 'running';

CREATE INDEX conflict_review_runs_queue_idx
  ON conflict_review_runs (status, created_at ASC)
  WHERE status IN ('queued', 'running');

CREATE INDEX conflict_review_runs_user_idx
  ON conflict_review_runs (requested_by, created_at DESC);

CREATE TABLE conflict_findings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES conflict_review_runs(id) ON DELETE CASCADE,
  document_a_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  document_b_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  node_a_id UUID NOT NULL REFERENCES document_nodes(id) ON DELETE CASCADE,
  node_b_id UUID NOT NULL REFERENCES document_nodes(id) ON DELETE CASCADE,
  finding_type TEXT NOT NULL CHECK (finding_type IN (
    'contradiction', 'overlap', 'exception_refinement', 'superseded_already'
  )),
  severity TEXT NOT NULL CHECK (severity IN ('high', 'medium', 'low')),
  detection_method TEXT NOT NULL CHECK (detection_method IN ('rule', 'rule_plus_ai')),
  similarity_score NUMERIC(5,4),
  shared_labels TEXT[] NOT NULL DEFAULT '{}',
  signals_json JSONB NOT NULL,
  precedence_result TEXT NOT NULL CHECK (precedence_result IN (
    'higher_authority_a', 'higher_authority_b',
    'same_tier_newer_a', 'same_tier_newer_b',
    'superseded_by_amendment', 'undetermined_requires_review'
  )),
  precedence_basis_json JSONB NOT NULL,
  explanation TEXT NOT NULL,
  ai_confidence NUMERIC(4,3),
  ai_verified BOOLEAN,
  review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN (
    'pending', 'confirmed', 'dismissed', 'linked_amendment'
  )),
  reviewed_by UUID REFERENCES users(id),
  reviewed_at TIMESTAMPTZ,
  review_note TEXT,
  linked_amendment_id UUID REFERENCES node_amendments(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (node_a_id <> node_b_id AND document_a_id <> document_b_id)
);

CREATE INDEX conflict_findings_run_idx
  ON conflict_findings (run_id, severity, finding_type);

CREATE INDEX conflict_findings_review_idx
  ON conflict_findings (review_status, created_at DESC);

-- Extend node_amendments.proposed_by CHECK constraint to allow 'conflict_review'.
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT c.conname
    FROM pg_constraint c
    WHERE c.conrelid = format('%I.node_amendments', current_schema())::regclass
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%proposed_by%'
  LOOP
    EXECUTE format('ALTER TABLE node_amendments DROP CONSTRAINT %I', r.conname);
  END LOOP;
END
$$;

ALTER TABLE node_amendments
  ADD CONSTRAINT node_amendments_proposed_by_check
  CHECK (proposed_by IN ('rule', 'ai', 'person', 'conflict_review'));
