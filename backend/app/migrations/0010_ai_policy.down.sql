DROP TABLE IF EXISTS ai_usage_events;
ALTER TABLE model_profiles
  DROP COLUMN IF EXISTS monthly_cost_limit,
  DROP COLUMN IF EXISTS daily_cost_limit,
  DROP COLUMN IF EXISTS output_price_per_mtok,
  DROP COLUMN IF EXISTS input_price_per_mtok;
ALTER TABLE stage_routes DROP COLUMN IF EXISTS escalation_profile_id;
DROP TABLE IF EXISTS stage_policies;
