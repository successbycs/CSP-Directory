ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_fit text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_category text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS llm_include_in_directory boolean;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS directory_decision_source text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS directory_reasoning text[];
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS hq_address text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS source_urls text[];
-- M58: Fix pricing column type from TEXT to TEXT[]
ALTER TABLE public.cs_vendors ALTER COLUMN pricing TYPE TEXT[] USING 
  CASE WHEN pricing IS NULL THEN NULL
       WHEN pricing LIKE '[%' THEN ARRAY(SELECT json_array_elements_text(pricing::json))
       ELSE ARRAY[pricing]
  END;

ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS case_study_signals text[];

-- M59: Rename auto_ fields to llm_ (dual-write: add new columns, backfill from old)
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_fit TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_category TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS llm_include_in_directory BOOLEAN;
UPDATE public.cs_vendors SET 
    llm_directory_fit = auto_directory_fit,
    llm_directory_category = auto_directory_category,
    llm_include_in_directory = auto_include_in_directory
WHERE llm_directory_fit IS NULL;
-- Note: auto_ columns retained for backward compatibility during transition
-- Run DROP after verifying all code reads from llm_ columns
