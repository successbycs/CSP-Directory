CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.cs_vendors (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  website TEXT UNIQUE NOT NULL,
  source TEXT,
  mission TEXT,
  usp TEXT,
  pricing TEXT[],
  icp_buyer JSONB DEFAULT '[]'::jsonb,
  free_trial BOOLEAN,
  soc2 BOOLEAN,
  compliance TEXT[] DEFAULT '{}'::text[],
  founded TEXT,
  products JSONB DEFAULT '[]'::jsonb,
  leadership JSONB DEFAULT '[]'::jsonb,
  ceo_name TEXT,
  hq_address TEXT,
  phone_numbers TEXT[] DEFAULT '{}'::text[],
  contact_emails TEXT[] DEFAULT '{}'::text[],
  company_hq TEXT,
  contact_email TEXT,
  contact_page_url TEXT,
  demo_url TEXT,
  help_center_url TEXT,
  support_url TEXT,
  about_url TEXT,
  team_url TEXT,
  developer_docs_url TEXT,
  integration_categories TEXT[] DEFAULT '{}'::text[],
  integrations TEXT[] DEFAULT '{}'::text[],
  integration_taxonomy JSONB DEFAULT '[]'::jsonb,
  external_enrichment JSONB DEFAULT '[]'::jsonb,
  support_signals TEXT[] DEFAULT '{}'::text[],
  use_cases TEXT[] DEFAULT '{}'::text[],
  lifecycle_stages TEXT[] DEFAULT '{}'::text[],
  case_study_details JSONB DEFAULT '[]'::jsonb,
  case_study_signals TEXT[] DEFAULT '{}'::text[],
  testimonials JSONB DEFAULT '[]'::jsonb,
  blog_posts JSONB DEFAULT '[]'::jsonb,
  source_urls TEXT[] DEFAULT '{}'::text[],
  directory_fit TEXT,
  directory_category TEXT,
  include_in_directory BOOLEAN DEFAULT FALSE,
  llm_directory_fit TEXT,
  llm_directory_category TEXT,
  llm_include_in_directory BOOLEAN,
  directory_decision_source TEXT,
  directory_reasoning TEXT[] DEFAULT '{}'::text[],
  raw_description TEXT,
  confidence TEXT,
  first_seen DATE DEFAULT CURRENT_DATE,
  last_enriched_at TIMESTAMPTZ,
  last_enriched_pipeline TEXT,
  enrichment_count INTEGER DEFAULT 0,
  enrichment_pipeline_counts JSONB DEFAULT '{}'::jsonb,
  last_updated TIMESTAMPTZ DEFAULT NOW(),
  is_new BOOLEAN DEFAULT TRUE
);

ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS icp TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS case_studies TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS case_study_signals TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS customers TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS value_statements TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS evidence_urls TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS directory_fit TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS directory_category TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS include_in_directory BOOLEAN DEFAULT FALSE;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_fit TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_category TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS llm_include_in_directory BOOLEAN;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS directory_decision_source TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS directory_reasoning TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS raw_description TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS mission TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS usp TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS pricing TEXT[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS icp_buyer JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS free_trial BOOLEAN;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS soc2 BOOLEAN;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS compliance TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS founded TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS products JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS leadership JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS ceo_name TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS hq_address TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS phone_numbers TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS contact_emails TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS company_hq TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS contact_email TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS contact_page_url TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS demo_url TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS help_center_url TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS support_url TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS about_url TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS team_url TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS developer_docs_url TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS integration_categories TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS integrations TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS integration_taxonomy JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS external_enrichment JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS support_signals TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS use_cases TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS lifecycle_stages TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS case_study_details JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS testimonials JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS blog_posts JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS source_urls TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS confidence TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS last_enriched_at TIMESTAMPTZ;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS last_enriched_pipeline TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS enrichment_count INTEGER DEFAULT 0;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS enrichment_pipeline_counts JSONB DEFAULT '{}'::jsonb;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS last_updated TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS is_new BOOLEAN DEFAULT TRUE;

CREATE TABLE IF NOT EXISTS public.discovery_candidates (
  candidate_domain TEXT PRIMARY KEY,
  candidate_title TEXT,
  candidate_description TEXT,
  source_query TEXT,
  source_engine TEXT,
  source_rank INTEGER,
  discovered_at TIMESTAMPTZ NOT NULL,
  candidate_status TEXT NOT NULL,
  drop_reason TEXT,
  updated_at TIMESTAMPTZ NOT NULL
);

ALTER TABLE public.discovery_candidates ADD COLUMN IF NOT EXISTS candidate_title TEXT;
ALTER TABLE public.discovery_candidates ADD COLUMN IF NOT EXISTS candidate_description TEXT;
ALTER TABLE public.discovery_candidates ADD COLUMN IF NOT EXISTS source_query TEXT;
ALTER TABLE public.discovery_candidates ADD COLUMN IF NOT EXISTS source_engine TEXT;
ALTER TABLE public.discovery_candidates ADD COLUMN IF NOT EXISTS source_rank INTEGER;
ALTER TABLE public.discovery_candidates ADD COLUMN IF NOT EXISTS discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.discovery_candidates ADD COLUMN IF NOT EXISTS candidate_status TEXT NOT NULL DEFAULT 'new';
ALTER TABLE public.discovery_candidates ADD COLUMN IF NOT EXISTS drop_reason TEXT;
ALTER TABLE public.discovery_candidates ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.pipeline_runs (
  run_id TEXT PRIMARY KEY,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  queries_executed TEXT,
  candidate_count INTEGER,
  queued_count INTEGER,
  skipped_existing_count INTEGER,
  enriched_count INTEGER,
  dropped_count INTEGER,
  llm_success_count INTEGER,
  llm_fallback_count INTEGER,
  run_status TEXT,
  error_summary TEXT
);

ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS queries_executed TEXT;
ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS candidate_count INTEGER;
ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS queued_count INTEGER;
ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS skipped_existing_count INTEGER;
ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS enriched_count INTEGER;
ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS dropped_count INTEGER;
ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS llm_success_count INTEGER;
ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS llm_fallback_count INTEGER;
ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS run_status TEXT;
ALTER TABLE public.pipeline_runs ADD COLUMN IF NOT EXISTS error_summary TEXT;

CREATE TABLE IF NOT EXISTS public.buyer_search_queries (
  query_signature TEXT PRIMARY KEY,
  source_vendor_name TEXT NOT NULL,
  source_vendor_website TEXT NOT NULL,
  buyer_role TEXT NOT NULL,
  search_channel TEXT NOT NULL,
  search_provider TEXT NOT NULL,
  query_text TEXT NOT NULL,
  persona_confidence TEXT,
  evidence TEXT[] DEFAULT '{}'::text[],
  query_generation_version TEXT,
  query_generation_context JSONB DEFAULT '{}'::jsonb,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.buyer_search_queries ADD COLUMN IF NOT EXISTS source_vendor_name TEXT;
ALTER TABLE public.buyer_search_queries ADD COLUMN IF NOT EXISTS source_vendor_website TEXT;
ALTER TABLE public.buyer_search_queries ADD COLUMN IF NOT EXISTS buyer_role TEXT;
ALTER TABLE public.buyer_search_queries ADD COLUMN IF NOT EXISTS search_channel TEXT;
ALTER TABLE public.buyer_search_queries ADD COLUMN IF NOT EXISTS search_provider TEXT;
ALTER TABLE public.buyer_search_queries ADD COLUMN IF NOT EXISTS query_text TEXT;
ALTER TABLE public.buyer_search_queries ADD COLUMN IF NOT EXISTS persona_confidence TEXT;
ALTER TABLE public.buyer_search_queries ADD COLUMN IF NOT EXISTS evidence TEXT[] DEFAULT '{}'::text[];
ALTER TABLE public.buyer_search_queries ADD COLUMN IF NOT EXISTS query_generation_version TEXT;
ALTER TABLE public.buyer_search_queries ADD COLUMN IF NOT EXISTS query_generation_context JSONB DEFAULT '{}'::jsonb;
ALTER TABLE public.buyer_search_queries ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.buyer_search_results (
  query_signature TEXT NOT NULL REFERENCES public.buyer_search_queries(query_signature) ON DELETE CASCADE,
  run_timestamp TIMESTAMPTZ NOT NULL,
  observed_rank INTEGER NOT NULL,
  buyer_role TEXT NOT NULL,
  search_channel TEXT NOT NULL,
  search_provider TEXT NOT NULL,
  query_text TEXT NOT NULL,
  surfaced_vendor_name TEXT NOT NULL,
  surfaced_vendor_website TEXT,
  source_url TEXT,
  response_reference TEXT,
  visibility_score DOUBLE PRECISION,
  PRIMARY KEY (query_signature, run_timestamp, observed_rank)
);

ALTER TABLE public.buyer_search_results ADD COLUMN IF NOT EXISTS buyer_role TEXT;
ALTER TABLE public.buyer_search_results ADD COLUMN IF NOT EXISTS search_channel TEXT;
ALTER TABLE public.buyer_search_results ADD COLUMN IF NOT EXISTS search_provider TEXT;
ALTER TABLE public.buyer_search_results ADD COLUMN IF NOT EXISTS query_text TEXT;
ALTER TABLE public.buyer_search_results ADD COLUMN IF NOT EXISTS surfaced_vendor_name TEXT;
ALTER TABLE public.buyer_search_results ADD COLUMN IF NOT EXISTS surfaced_vendor_website TEXT;
ALTER TABLE public.buyer_search_results ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE public.buyer_search_results ADD COLUMN IF NOT EXISTS response_reference TEXT;
ALTER TABLE public.buyer_search_results ADD COLUMN IF NOT EXISTS visibility_score DOUBLE PRECISION;
ALTER TABLE public.buyer_search_results ADD COLUMN IF NOT EXISTS run_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.buyer_search_results ADD COLUMN IF NOT EXISTS observed_rank INTEGER NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS buyer_search_queries_generated_at_idx
  ON public.buyer_search_queries (generated_at DESC);

CREATE INDEX IF NOT EXISTS buyer_search_queries_vendor_role_idx
  ON public.buyer_search_queries (source_vendor_website, buyer_role, search_channel);

CREATE INDEX IF NOT EXISTS buyer_search_results_run_rank_idx
  ON public.buyer_search_results (run_timestamp DESC, observed_rank ASC);

CREATE INDEX IF NOT EXISTS buyer_search_results_vendor_idx
  ON public.buyer_search_results (surfaced_vendor_website, surfaced_vendor_name);

CREATE TABLE IF NOT EXISTS public.lead_captures (
  lead_id TEXT PRIMARY KEY,
  capture_version TEXT,
  lead_name TEXT NOT NULL,
  lead_email TEXT NOT NULL,
  company_name TEXT NOT NULL,
  lead_intent TEXT NOT NULL,
  intent_category TEXT NOT NULL,
  follow_up_priority TEXT,
  notes TEXT,
  entry_page TEXT,
  entry_url TEXT,
  cta_surface TEXT,
  cta_variant TEXT,
  cta_label TEXT,
  vendor_name TEXT,
  vendor_website TEXT,
  vendor_category TEXT,
  referrer TEXT,
  utm_source TEXT,
  utm_medium TEXT,
  utm_campaign TEXT,
  utm_term TEXT,
  utm_content TEXT,
  attribution_context JSONB DEFAULT '{}'::jsonb,
  follow_up_status TEXT NOT NULL DEFAULT 'new',
  follow_up_owner TEXT,
  recommended_handoff_channel TEXT,
  recommended_next_step TEXT,
  follow_up_notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.integration_catalog (
  integration_name TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  aliases TEXT[] DEFAULT '{}'::text[],
  source TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS integration_catalog_category_idx
  ON public.integration_catalog (category);

CREATE INDEX IF NOT EXISTS integration_catalog_active_idx
  ON public.integration_catalog (active);

ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS capture_version TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS lead_id TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS lead_name TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS lead_email TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS company_name TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS lead_intent TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS intent_category TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS follow_up_priority TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS entry_page TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS entry_url TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS cta_surface TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS cta_variant TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS cta_label TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS vendor_name TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS vendor_website TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS vendor_category TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS referrer TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS utm_source TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS utm_medium TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS utm_campaign TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS utm_term TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS utm_content TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS attribution_context JSONB DEFAULT '{}'::jsonb;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS follow_up_status TEXT DEFAULT 'new';
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS follow_up_owner TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS recommended_handoff_channel TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS recommended_next_step TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS follow_up_notes TEXT;
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.lead_captures ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS lead_captures_created_at_idx
  ON public.lead_captures (created_at DESC);

CREATE INDEX IF NOT EXISTS lead_captures_status_idx
  ON public.lead_captures (follow_up_status, created_at DESC);

CREATE INDEX IF NOT EXISTS lead_captures_email_idx
  ON public.lead_captures (lead_email);
