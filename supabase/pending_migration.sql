ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS trustpilot_rating float;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS trustpilot_review_count integer;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS feature_depth_score integer;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS feature_signals text[];