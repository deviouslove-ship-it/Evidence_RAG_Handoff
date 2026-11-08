-- G4: content groups (D4) and labels.  The catalog is data, extendable by administrators.
CREATE TABLE content_taxonomy (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT NOT NULL UNIQUE CHECK (code ~ '^[a-z0-9_]{2,60}$'),
  name TEXT NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
  description TEXT,
  sort_order INTEGER NOT NULL DEFAULT 100,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Phrase rules: assign a group when the clause text contains the phrase ("đủ rõ").
CREATE TABLE labeling_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  taxonomy_id UUID NOT NULL REFERENCES content_taxonomy(id) ON DELETE CASCADE,
  phrase TEXT NOT NULL CHECK (length(btrim(phrase)) BETWEEN 2 AND 200),
  phrase_folded TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'text' CHECK (scope IN ('text', 'heading')),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (taxonomy_id, phrase_folded, scope)
);

-- One clause may carry several groups.  Rule labels are 'auto'; AI labels are
-- 'proposed' until a reviewer approves or rejects them in a batch.
CREATE TABLE node_labels (
  node_id UUID NOT NULL REFERENCES document_nodes(id) ON DELETE CASCADE,
  taxonomy_id UUID NOT NULL REFERENCES content_taxonomy(id) ON DELETE CASCADE,
  source TEXT NOT NULL CHECK (source IN ('rule', 'ai', 'person')),
  status TEXT NOT NULL CHECK (status IN ('auto', 'proposed', 'approved', 'rejected')),
  confidence NUMERIC CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  model_version TEXT,
  rule_id UUID REFERENCES labeling_rules(id) ON DELETE SET NULL,
  review_batch_id UUID,
  reviewed_by UUID REFERENCES users(id),
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (node_id, taxonomy_id)
);
CREATE INDEX node_labels_review ON node_labels (status) WHERE status = 'proposed';
-- Nodes the lazy labeller already looked at (with or without a resulting label).
CREATE TABLE node_label_runs (
  node_id UUID PRIMARY KEY REFERENCES document_nodes(id) ON DELETE CASCADE,
  rules_revision TEXT NOT NULL,
  ai_attempted BOOLEAN NOT NULL DEFAULT FALSE,
  labelled_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Initial catalog (11 groups) and phrase rules; administrators may change both.
INSERT INTO content_taxonomy (code, name, sort_order) VALUES
  ('pham_vi_doi_tuong', 'Phạm vi điều chỉnh, đối tượng áp dụng', 10),
  ('giai_thich_tu_ngu', 'Giải thích từ ngữ', 20),
  ('nguyen_tac', 'Nguyên tắc', 30),
  ('dieu_kien_tieu_chuan', 'Điều kiện, tiêu chuẩn', 40),
  ('ho_so_giay_to', 'Hồ sơ, giấy tờ, biểu mẫu', 50),
  ('trinh_tu_thu_tuc', 'Trình tự, thủ tục', 60),
  ('thoi_han', 'Thời hạn', 70),
  ('tham_quyen_trach_nhiem', 'Thẩm quyền, trách nhiệm', 80),
  ('quyen_nghia_vu', 'Quyền và nghĩa vụ', 90),
  ('vi_pham_xu_ly', 'Hành vi bị nghiêm cấm, xử lý vi phạm', 100),
  ('hieu_luc_chuyen_tiep', 'Hiệu lực, điều khoản thi hành, chuyển tiếp', 110);

INSERT INTO labeling_rules (taxonomy_id, phrase, phrase_folded, scope)
SELECT t.id, r.phrase, r.folded, r.scope
FROM content_taxonomy t
JOIN (VALUES
  ('pham_vi_doi_tuong', 'Phạm vi điều chỉnh', 'pham vi dieu chinh', 'heading'),
  ('pham_vi_doi_tuong', 'Đối tượng áp dụng', 'doi tuong ap dung', 'heading'),
  ('giai_thich_tu_ngu', 'Giải thích từ ngữ', 'giai thich tu ngu', 'heading'),
  ('giai_thich_tu_ngu', 'được hiểu như sau', 'duoc hieu nhu sau', 'text'),
  ('nguyen_tac', 'Nguyên tắc', 'nguyen tac', 'heading'),
  ('dieu_kien_tieu_chuan', 'Điều kiện', 'dieu kien', 'heading'),
  ('dieu_kien_tieu_chuan', 'Tiêu chuẩn', 'tieu chuan', 'heading'),
  ('ho_so_giay_to', 'Hồ sơ', 'ho so', 'heading'),
  ('ho_so_giay_to', 'hồ sơ gồm', 'ho so gom', 'text'),
  ('ho_so_giay_to', 'biểu mẫu', 'bieu mau', 'text'),
  ('trinh_tu_thu_tuc', 'Trình tự', 'trinh tu', 'heading'),
  ('trinh_tu_thu_tuc', 'Thủ tục', 'thu tuc', 'heading'),
  ('trinh_tu_thu_tuc', 'trình tự, thủ tục', 'trinh tu, thu tuc', 'text'),
  ('thoi_han', 'trong thời hạn', 'trong thoi han', 'text'),
  ('thoi_han', 'ngày làm việc', 'ngay lam viec', 'text'),
  ('thoi_han', 'Thời hạn', 'thoi han', 'heading'),
  ('tham_quyen_trach_nhiem', 'Trách nhiệm', 'trach nhiem', 'heading'),
  ('tham_quyen_trach_nhiem', 'Thẩm quyền', 'tham quyen', 'heading'),
  ('tham_quyen_trach_nhiem', 'có trách nhiệm', 'co trach nhiem', 'text'),
  ('quyen_nghia_vu', 'Quyền và nghĩa vụ', 'quyen va nghia vu', 'heading'),
  ('quyen_nghia_vu', 'có quyền', 'co quyen', 'text'),
  ('vi_pham_xu_ly', 'nghiêm cấm', 'nghiem cam', 'text'),
  ('vi_pham_xu_ly', 'Xử lý vi phạm', 'xu ly vi pham', 'heading'),
  ('vi_pham_xu_ly', 'xử lý vi phạm', 'xu ly vi pham', 'text'),
  ('hieu_luc_chuyen_tiep', 'Hiệu lực thi hành', 'hieu luc thi hanh', 'heading'),
  ('hieu_luc_chuyen_tiep', 'chuyển tiếp', 'chuyen tiep', 'heading'),
  ('hieu_luc_chuyen_tiep', 'có hiệu lực thi hành', 'co hieu luc thi hanh', 'text')
) AS r(code, phrase, folded, scope) ON r.code = t.code;
