ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_fit text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_category text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS llm_include_in_directory boolean;
-- M60: about page crawl fields
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS ceo_linkedin text;
-- M61: new enrichment fields
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS youtube_channel_url text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS funding_stage text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS total_funding text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS use_case_details jsonb DEFAULT '[]'::jsonb;