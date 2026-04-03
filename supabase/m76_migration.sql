-- M76 Ops Enrichment Workbench — full migration
-- Paste this entire file into the Supabase SQL Editor and click Run
-- All statements are idempotent (safe to re-run)

-- 1. Per-source result columns on cs_vendors
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier1_result   jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier2_result   jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier3_result   jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_datagma_result jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_g2_result      jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_llm_result     jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS source_field_map     jsonb;

-- 2. vendor_pages table
CREATE TABLE IF NOT EXISTS vendor_pages (
  id             bigserial    PRIMARY KEY,
  vendor_website text         NOT NULL,
  page_url       text         NOT NULL,
  title          text,
  clean_text     text,
  word_count     int,
  page_depth     int,
  tier_used      text,
  crawled_at     timestamptz  DEFAULT now(),
  UNIQUE (vendor_website, page_url)
);

CREATE INDEX IF NOT EXISTS vendor_pages_website_idx    ON vendor_pages (vendor_website);
CREATE INDEX IF NOT EXISTS vendor_pages_crawled_at_idx ON vendor_pages (crawled_at DESC);

-- 3. vendor_page_embeddings table (requires pgvector — already enabled)
CREATE TABLE IF NOT EXISTS vendor_page_embeddings (
  id             bigserial  PRIMARY KEY,
  vendor_website text       NOT NULL,
  page_url       text       NOT NULL,
  chunk_index    int        NOT NULL,
  chunk_text     text,
  embedding      vector(768),
  crawled_at     timestamptz DEFAULT now(),
  UNIQUE (vendor_website, page_url, chunk_index)
);

CREATE INDEX IF NOT EXISTS vendor_page_embeddings_website_idx
  ON vendor_page_embeddings (vendor_website);

CREATE INDEX IF NOT EXISTS vendor_page_embeddings_vector_idx
  ON vendor_page_embeddings
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- 4. pgvector similarity search RPC — used by Python LLM extractor
CREATE OR REPLACE FUNCTION match_vendor_page_chunks(
  query_embedding vector(768),
  match_vendor_website text,
  match_count int DEFAULT 5
)
RETURNS TABLE (
  id bigint,
  page_url text,
  chunk_index int,
  chunk_text text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    vpe.id,
    vpe.page_url,
    vpe.chunk_index,
    vpe.chunk_text,
    1 - (vpe.embedding <=> query_embedding) AS similarity
  FROM vendor_page_embeddings vpe
  WHERE vpe.vendor_website = match_vendor_website
  ORDER BY vpe.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
