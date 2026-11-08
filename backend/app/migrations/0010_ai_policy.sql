-- G1.0: per-stage call policy, Hybrid Auto escalation, cost caps and usage log.
-- Replaces the fixed "at most 2 LLM attempts" with configuration (ADR-007).
CREATE TABLE stage_policies (
  mode TEXT NOT NULL CHECK (mode IN ('API', 'LOCAL')),
  stage TEXT NOT NULL,
  max_attempts INTEGER NOT NULL CHECK (max_attempts BETWEEN 1 AND 10),
  max_output_tokens INTEGER
    CHECK (max_output_tokens IS NULL OR max_output_tokens BETWEEN 1 AND 16384),
  timeout_seconds NUMERIC
    CHECK (timeout_seconds IS NULL OR (timeout_seconds > 0 AND timeout_seconds <= 30)),
  max_concurrency INTEGER CHECK (max_concurrency IS NULL OR max_concurrency BETWEEN 1 AND 64),
  updated_by UUID REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (mode, stage)
);

-- API mode only: a public profile tried once when the local result fails the
-- application's check, or when the user asks for a deeper analysis.
ALTER TABLE stage_routes ADD COLUMN escalation_profile_id UUID REFERENCES model_profiles(id);

-- Prices per million tokens and spending caps, in the currency the administrator
-- uses for the provider (one currency per profile).
ALTER TABLE model_profiles
  ADD COLUMN input_price_per_mtok NUMERIC CHECK (input_price_per_mtok IS NULL OR input_price_per_mtok >= 0),
  ADD COLUMN output_price_per_mtok NUMERIC CHECK (output_price_per_mtok IS NULL OR output_price_per_mtok >= 0),
  ADD COLUMN daily_cost_limit NUMERIC CHECK (daily_cost_limit IS NULL OR daily_cost_limit >= 0),
  ADD COLUMN monthly_cost_limit NUMERIC CHECK (monthly_cost_limit IS NULL OR monthly_cost_limit >= 0);

-- One row per HTTP send to a model.  No prompt, answer or document content.
CREATE TABLE ai_usage_events (
  id BIGSERIAL PRIMARY KEY,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  mode TEXT NOT NULL,
  stage TEXT NOT NULL,
  profile_key TEXT NOT NULL,
  principal_id UUID,
  outcome TEXT NOT NULL,
  escalated BOOLEAN NOT NULL DEFAULT FALSE,
  input_tokens INTEGER,
  output_tokens INTEGER,
  duration_ms INTEGER,
  estimated_cost NUMERIC
);
CREATE INDEX ai_usage_events_profile_time ON ai_usage_events (profile_key, occurred_at);
