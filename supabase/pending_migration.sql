ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier1_result jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier2_result jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier3_result jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_datagma_result jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_g2_result jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_llm_result jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS source_field_map jsonb;