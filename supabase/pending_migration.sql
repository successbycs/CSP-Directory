ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS raw_crawl_blob text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_page_count integer;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_completed_at timestamp with time zone;

CREATE TABLE IF NOT EXISTS integration_catalog (
  integration_name text PRIMARY KEY,
  category text NOT NULL,
  aliases text[] DEFAULT '{}'::text[],
  source text,
  active boolean NOT NULL DEFAULT true,
  updated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS integration_catalog_category_idx
  ON integration_catalog (category);

CREATE INDEX IF NOT EXISTS integration_catalog_active_idx
  ON integration_catalog (active);
