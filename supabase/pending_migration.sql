ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_fit text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_category text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS llm_include_in_directory boolean;
-- M60: about page crawl fields
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS ceo_linkedin text;