ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS auto_directory_fit text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS auto_directory_category text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS auto_include_in_directory boolean;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS directory_decision_source text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS directory_reasoning text[];
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS hq_address text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS source_urls text[];