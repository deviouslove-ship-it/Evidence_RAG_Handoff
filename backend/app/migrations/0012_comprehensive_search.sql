-- G2: comprehensive search (design §6).
-- The vector column no longer fixes 768 dimensions: each embedding index records its
-- model and dimension, and gets its own HNSW index on ``embedding::vector(<dims>)``
-- (created by scripts/build_embeddings.py), so changing the embedding model never
-- changes the schema.
ALTER TABLE node_embeddings ALTER COLUMN embedding TYPE vector;
ALTER TABLE node_embeddings ADD COLUMN embedded_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE embedding_indices
  ADD COLUMN profile_key TEXT,
  ADD COLUMN status TEXT NOT NULL DEFAULT 'building'
    CHECK (status IN ('building', 'ready', 'retired')),
  ADD COLUMN node_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN completed_at TIMESTAMPTZ;
CREATE UNIQUE INDEX one_active_embedding_index ON embedding_indices (is_active) WHERE is_active;

-- Reviewed concept dictionary for query expansion.  A term found in the query adds its
-- expansions; only approved rows are used without asking, AI suggestions are shown to
-- the user (who may deselect them) and kept as proposals for review.
CREATE TABLE concept_terms (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  term TEXT NOT NULL CHECK (length(btrim(term)) BETWEEN 1 AND 200),
  term_folded TEXT NOT NULL,
  expansion TEXT NOT NULL CHECK (length(btrim(expansion)) BETWEEN 1 AND 200),
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'approved', 'rejected')),
  source TEXT NOT NULL DEFAULT 'person' CHECK (source IN ('person', 'ai')),
  model_version TEXT,
  created_by UUID REFERENCES users(id),
  reviewed_by UUID REFERENCES users(id),
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (term_folded, expansion)
);
CREATE INDEX concept_terms_approved ON concept_terms (term_folded) WHERE status = 'approved';
