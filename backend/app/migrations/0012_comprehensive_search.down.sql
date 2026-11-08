DROP TABLE IF EXISTS concept_terms;
DROP INDEX IF EXISTS one_active_embedding_index;
DO $$
DECLARE item RECORD;
BEGIN
  -- Per-index HNSW indexes created by scripts/build_embeddings.py.
  FOR item IN SELECT indexname FROM pg_indexes
              WHERE schemaname = current_schema() AND indexname LIKE 'node_embeddings_hnsw_%'
  LOOP
    EXECUTE format('DROP INDEX IF EXISTS %I', item.indexname);
  END LOOP;
END $$;
ALTER TABLE embedding_indices DROP COLUMN IF EXISTS completed_at,
  DROP COLUMN IF EXISTS created_at, DROP COLUMN IF EXISTS node_count,
  DROP COLUMN IF EXISTS status, DROP COLUMN IF EXISTS profile_key;
ALTER TABLE node_embeddings DROP COLUMN IF EXISTS embedded_at;
-- The earlier schema only holds 768-dimension vectors.
DELETE FROM node_embeddings WHERE embedding IS NOT NULL AND vector_dims(embedding) <> 768;
ALTER TABLE node_embeddings ALTER COLUMN embedding TYPE vector(768);
