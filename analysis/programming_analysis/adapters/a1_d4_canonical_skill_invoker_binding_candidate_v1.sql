-- SOURCE-ONLY CANDIDATE. NOT a migration. NOT applied to Supabase.
-- Proposed INTERNAL preparation helper for a future fully governed
-- PROGRAMMING_ANALYSIS_LF executor. NOT a registered skill handler.
-- Uses pre-existing private.fn_lf_source_investigation_prepare_v1
-- (D1/D2/planner/D3); does not replace the whole A1-A15 skill.
-- Requires whole-skill dispatcher, authorized binding, review and readback
-- before a real call; this source-only file is not wired.
-- DO NOT call directly from Router, A1, a GPT session, or a profile worker running llama.
-- Existing skill asset PROGRAMMING_ANALYSIS_LF is CANDIDATE_READ_ONLY.
-- Existing operation EJECUCION_SKILL_LF is OP_CANDIDATE.
-- DO NOT register PROGRAMMING_ANALYSIS_LF with this partial D4 helper.
-- No additional GRANT to supabase_read_only_user, anon or authenticated.
--
-- Proposed source must be governed/migrated only AFTER exact-source review.

CREATE OR REPLACE FUNCTION public.lf_skill_h_programming_analysis_inventory_prepare_v1(
    p_input jsonb
) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path TO pg_catalog, public, private
AS $$
DECLARE
    v_raw text;
    v_digest text;
    v_ambiguities jsonb;
    v_preparation jsonb;
    v_action text;
BEGIN
    IF p_input IS NULL OR pg_catalog.jsonb_typeof(p_input) <> 'object'
       OR p_input->>'schema_version' IS DISTINCT FROM 'A1_INVENTORY_RESEARCH_HANDOFF_CANDIDATE_V1'
       OR p_input->>'business' IS DISTINCT FROM 'LF'
       OR p_input->>'allow_a2' IS DISTINCT FROM 'false'
       OR p_input->>'inventory_source_verified' IS DISTINCT FROM 'false'
    THEN
        RAISE EXCEPTION 'A1_D4_RESEARCH_HANDOFF_NOT_ADMITTED';
    END IF;

    v_raw := p_input->>'original_request';
    IF pg_catalog.jsonb_typeof(p_input->'target_hints') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'A1_D4_RESEARCH_INPUT_INVALID';
    END IF;

    IF pg_catalog.jsonb_typeof(p_input->'original_request') IS DISTINCT FROM 'string'
       OR v_raw IS NULL OR length(pg_catalog.btrim(v_raw)) NOT BETWEEN 3 AND 1000

       OR nullif(pg_catalog.btrim(p_input->>'operation_kind'), '') IS NULL
       OR nullif(pg_catalog.btrim(p_input->>'artifact_kind'), '') IS NULL
       OR pg_catalog.jsonb_typeof(p_input->'constraints') IS DISTINCT FROM 'array'

       OR pg_catalog.jsonb_array_length(p_input->'target_hints') < 1
       OR pg_catalog.jsonb_typeof(p_input->'source_refs') IS DISTINCT FROM 'array'
       OR pg_catalog.jsonb_typeof(p_input->'dimensions_to_investigate') IS DISTINCT FROM 'array'
    THEN
        RAISE EXCEPTION 'A1_D4_RESEARCH_INPUT_INVALID';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_input->'constraints') AS c(item)
        WHERE pg_catalog.jsonb_typeof(c.item) <> 'string'
    )
    OR EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_input->'target_hints') AS t(item)
        WHERE pg_catalog.jsonb_typeof(t.item) <> 'string'
    )
    OR EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_input->'source_refs') AS r(item)
        WHERE pg_catalog.jsonb_typeof(r.item) <> 'string'
    ) THEN
        RAISE EXCEPTION 'A1_D4_RESEARCH_INPUT_INVALID';
    END IF;

    v_digest := pg_catalog.encode(
        extensions.digest(pg_catalog.convert_to(v_raw, 'UTF8'), 'sha256'), 'hex'
    );
    IF p_input->>'request_sha256' IS DISTINCT FROM v_digest THEN
        RAISE EXCEPTION 'A1_D4_RAW_REQUEST_DIGEST_MISMATCH';
    END IF;

    v_ambiguities := p_input->'open_ambiguities';
    IF pg_catalog.jsonb_typeof(v_ambiguities) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'A1_D4_MATERIAL_AMBIGUITY_REQUIRED';
    END IF;
    IF pg_catalog.jsonb_array_length(v_ambiguities) < 1
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(v_ambiguities) AS a(item)
           WHERE pg_catalog.jsonb_typeof(a.item) IS DISTINCT FROM 'object'
              OR a.item->>'resolution_state' IS DISTINCT FROM 'OPEN'
              OR a.item->>'materiality' IS NULL
              OR a.item->>'materiality' NOT IN ('MATERIAL','UNKNOWN')
              OR nullif(pg_catalog.btrim(a.item->>'code'), '') IS NULL
       )
    THEN
        RAISE EXCEPTION 'A1_D4_MATERIAL_AMBIGUITY_REQUIRED';
    END IF;

    -- Future whole-skill governed consumer must supply the trusted cursor.
    -- This helper does not establish a parent/profile receipt on its own.
    -- SECURITY INVOKER preserves the effective role/ACL of the caller.
    v_preparation := private.fn_lf_source_investigation_prepare_v1(v_raw, 12);
    v_action := v_preparation->>'next_action';

    IF v_preparation->>'schema_version' IS DISTINCT FROM 'LF_SOURCE_INVESTIGATION_PREPARATION_V1'
       OR v_preparation->>'business_data_read_authorized' IS DISTINCT FROM 'false'
       OR v_preparation->>'rows_accessed' IS DISTINCT FROM 'false'
       OR v_preparation->>'runtime_dispatched' IS DISTINCT FROM 'false'
       OR v_preparation->>'effects_executed' IS DISTINCT FROM 'false'
       OR v_preparation->>'final_business_answer_allowed' IS DISTINCT FROM 'false'
       OR v_preparation->>'global_discovery_exhausted' IS DISTINCT FROM 'false'
       OR v_preparation->>'planner_stop_is_local_only' IS DISTINCT FROM 'true'
    THEN
        RAISE EXCEPTION 'A1_D4_PREPARATION_CONTRACT_FAILED';
    END IF;
    IF v_action IS NULL OR v_action LIKE 'BLOCK_%' THEN
        RAISE EXCEPTION 'A1_D4_CANONICAL_PREPARATION_BLOCKED';
    END IF;

    RETURN pg_catalog.jsonb_build_object(
        'schema_version','A1_D4_GOVERNED_METADATA_CANDIDATE_V1',
        'status','METADATA_PREPARED_AMBIGUITIES_UNRESOLVED',
        'business','LF',
        'request_sha256',v_digest,
        'operation_kind',p_input->>'operation_kind',
        'target_hints',p_input->'target_hints',
        'constraints',p_input->'constraints',
        'open_ambiguities',v_ambiguities,
        'dimensions_to_investigate',p_input->'dimensions_to_investigate',
        'preparation',v_preparation,
        'next_required_action',v_action,
        'source_attested',false,
        'a2_allowed',false,
        'business_data_read_authorized',false,
        'effects_executed',false
    );
END;
$$;

-- Do not expose this handler as an independently callable API.
REVOKE ALL ON FUNCTION public.lf_skill_h_programming_analysis_inventory_prepare_v1(jsonb)
    FROM PUBLIC, anon, authenticated, supabase_read_only_user, service_role;

-- This is a candidate INTERNAL helper only.
-- Do NOT INSERT PROGRAMMING_ANALYSIS_LF into lf_skill_catalog_v1 here:
-- its whole A1-A15 executor is not yet released and D4 alone is not the skill.
-- No catalog registration, profile authority, grant, release, ticket,
-- worker deployment, SQL invocation or RUN is created by this source.
