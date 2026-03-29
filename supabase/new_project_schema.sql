-- Full schema for new Supabase project (fadatnutpfnhxwctyvdt)
-- Run this in the SQL editor before running scripts/migrate_supabase.py

-- ─── cs_vendors ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.cs_vendors (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  name text NOT NULL,
  website text NOT NULL UNIQUE,
  source text,
  mission text,
  usp text,
  pricing text,
  free_trial boolean,
  soc2 boolean,
  founded text,
  use_cases text[],
  lifecycle_stages text[],
  raw_description text,
  first_seen date DEFAULT CURRENT_DATE,
  last_enriched_at timestamptz,
  last_enriched_pipeline text,
  enrichment_count integer DEFAULT 0,
  enrichment_pipeline_counts jsonb DEFAULT '{}',
  last_updated timestamptz DEFAULT now(),
  is_new boolean DEFAULT true,
  icp text[] DEFAULT '{}',
  case_studies text[] DEFAULT '{}',
  customers text[] DEFAULT '{}',
  value_statements text[] DEFAULT '{}',
  evidence_urls text[] DEFAULT '{}',
  directory_fit text,
  directory_category text,
  include_in_directory boolean DEFAULT false,
  confidence text,
  icp_buyer jsonb DEFAULT '[]',
  products jsonb DEFAULT '[]',
  leadership jsonb DEFAULT '[]',
  company_hq text,
  contact_email text,
  contact_page_url text,
  demo_url text,
  help_center_url text,
  support_url text,
  about_url text,
  team_url text,
  integration_categories text[] DEFAULT '{}',
  integrations text[] DEFAULT '{}',
  support_signals text[] DEFAULT '{}',
  case_study_details jsonb DEFAULT '[]',
  auto_directory_fit text,
  auto_directory_category text,
  auto_include_in_directory boolean,
  directory_decision_source text,
  directory_reasoning text[],
  hq_address text,
  source_urls text[],
  compliance text[],
  ceo_name text,
  phone_numbers text[],
  contact_emails text[],
  developer_docs_url text,
  integration_taxonomy jsonb,
  external_enrichment jsonb,
  testimonials text[],
  blog_posts text[],
  llm_directory_fit text,
  llm_directory_category text,
  llm_include_in_directory boolean,
  ceo_linkedin text,
  youtube_channel_url text,
  funding_stage text,
  total_funding text,
  use_case_details jsonb DEFAULT '[]',
  has_public_pricing_page boolean,
  pricing_source text,
  g2_url text,
  g2_rating numeric,
  g2_review_count integer,
  g2_market_segment text,
  g2_categories text[] DEFAULT '{}',
  case_study_signals text[] DEFAULT ARRAY[]::text[],
  raw_crawl_blob text,
  crawl_page_count integer,
  crawl_completed_at timestamptz
);

-- ─── discovery_candidates ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.discovery_candidates (
  candidate_domain text PRIMARY KEY,
  candidate_title text,
  candidate_description text,
  source_query text,
  source_engine text,
  source_rank integer,
  discovered_at timestamptz NOT NULL DEFAULT now(),
  candidate_status text NOT NULL DEFAULT 'new',
  drop_reason text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ─── pipeline_runs ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.pipeline_runs (
  run_id text PRIMARY KEY,
  started_at timestamptz,
  completed_at timestamptz,
  queries_executed text,
  candidate_count integer,
  queued_count integer,
  skipped_existing_count integer,
  enriched_count integer,
  dropped_count integer,
  llm_success_count integer,
  llm_fallback_count integer,
  run_status text,
  error_summary text
);

-- ─── lead_captures ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.lead_captures (
  lead_id text PRIMARY KEY,
  capture_version text,
  lead_name text NOT NULL,
  lead_email text NOT NULL,
  company_name text NOT NULL,
  lead_intent text NOT NULL,
  intent_category text NOT NULL,
  follow_up_priority text,
  notes text,
  entry_page text,
  entry_url text,
  cta_surface text,
  cta_variant text,
  cta_label text,
  vendor_name text,
  vendor_website text,
  vendor_category text,
  referrer text,
  utm_source text,
  utm_medium text,
  utm_campaign text,
  utm_term text,
  utm_content text,
  attribution_context jsonb DEFAULT '{}',
  follow_up_status text NOT NULL DEFAULT 'new',
  follow_up_owner text,
  recommended_handoff_channel text,
  recommended_next_step text,
  follow_up_notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS lead_captures_created_at_idx ON public.lead_captures (created_at DESC);
CREATE INDEX IF NOT EXISTS lead_captures_status_idx ON public.lead_captures (follow_up_status, created_at DESC);
CREATE INDEX IF NOT EXISTS lead_captures_email_idx ON public.lead_captures (lead_email);

-- ─── integration_catalog ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.integration_catalog (
  integration_name text PRIMARY KEY,
  category text NOT NULL,
  aliases text[] DEFAULT '{}',
  source text,
  active boolean NOT NULL DEFAULT true,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS integration_catalog_category_idx ON public.integration_catalog (category);
CREATE INDEX IF NOT EXISTS integration_catalog_active_idx ON public.integration_catalog (active);

-- ─── buyer_search_queries ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.buyer_search_queries (
  query_signature text PRIMARY KEY,
  source_vendor_name text NOT NULL,
  source_vendor_website text NOT NULL,
  buyer_role text NOT NULL,
  search_channel text NOT NULL,
  search_provider text NOT NULL,
  query_text text NOT NULL,
  persona_confidence text,
  evidence text[] DEFAULT '{}',
  query_generation_version text,
  query_generation_context jsonb DEFAULT '{}',
  generated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS buyer_search_queries_generated_at_idx ON public.buyer_search_queries (generated_at DESC);
CREATE INDEX IF NOT EXISTS buyer_search_queries_vendor_role_idx ON public.buyer_search_queries (source_vendor_website, buyer_role, search_channel);

-- ─── buyer_search_results ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.buyer_search_results (
  query_signature text NOT NULL REFERENCES public.buyer_search_queries(query_signature) ON DELETE CASCADE,
  run_timestamp timestamptz NOT NULL,
  observed_rank integer NOT NULL,
  buyer_role text NOT NULL,
  search_channel text NOT NULL,
  search_provider text NOT NULL,
  query_text text NOT NULL,
  surfaced_vendor_name text NOT NULL,
  surfaced_vendor_website text,
  source_url text,
  response_reference text,
  visibility_score double precision,
  PRIMARY KEY (query_signature, run_timestamp, observed_rank)
);

CREATE INDEX IF NOT EXISTS buyer_search_results_run_rank_idx ON public.buyer_search_results (run_timestamp DESC, observed_rank ASC);
CREATE INDEX IF NOT EXISTS buyer_search_results_vendor_idx ON public.buyer_search_results (surfaced_vendor_website, surfaced_vendor_name);
