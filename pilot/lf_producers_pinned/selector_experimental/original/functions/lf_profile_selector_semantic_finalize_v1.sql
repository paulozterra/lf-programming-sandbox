CREATE OR REPLACE FUNCTION public.lf_profile_selector_semantic_finalize_v1(p_request jsonb, p_draft jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public', 'extensions'
AS $function$
DECLARE
  v_result jsonb;
  v_receipt text;
  v_validation jsonb;
BEGIN
  IF jsonb_typeof(p_draft)<>'object' THEN
    RETURN jsonb_build_object(
      'status','BLOCKED',
      'blocking_code','PROFILE_SELECTOR_DRAFT_NOT_OBJECT'
    );
  END IF;

  IF p_draft ?| ARRAY[
       'schema_version','request_sha256','catalog_sha256','catalog_profile_count',
       'semantic_receipt_sha256','operation_code','action_code','candidate_action_code',
       'executor','executor_mode','router_action_binding',
       'route_authority','effect_authority','downstream_execution_allowed'
     ]
  THEN
    RETURN jsonb_build_object(
      'status','BLOCKED',
      'blocking_code','PROFILE_SELECTOR_DRAFT_CONTROL_FIELD_FORBIDDEN'
    );
  END IF;

  v_result:=jsonb_build_object(
    'schema_version','LF_PROFILE_SELECTOR_SEMANTIC_RESULT_V1',
    'request_sha256',p_request->>'request_sha256',
    'catalog_sha256',p_request->>'catalog_sha256',
    'catalog_profile_count',coalesce((p_request->>'catalog_profile_count')::integer,0),
    'decision',upper(coalesce(p_draft->>'decision','')),
    'selected_profile_code',case
      when nullif(btrim(coalesce(p_draft->>'selected_profile_code','')),'') is null
        then null
      else p_draft->>'selected_profile_code'
    end,
    'ambiguous_profile_codes',coalesce(p_draft->'ambiguous_profile_codes','[]'::jsonb),
    'reason',p_draft->>'reason',
    'evidence_refs',coalesce(p_draft->'evidence_refs','[]'::jsonb),
    'material_ambiguities',coalesce(p_draft->'material_ambiguities','[]'::jsonb)
  );

  v_receipt:=encode(
    extensions.digest(convert_to(v_result::text,'UTF8'),'sha256'),
    'hex'
  );
  v_result:=v_result||jsonb_build_object('semantic_receipt_sha256',v_receipt);

  v_validation:=public.lf_profile_selector_semantic_validate_v1(
    p_request,v_result
  );

  RETURN jsonb_build_object(
    'schema_version','LF_PROFILE_SELECTOR_SEMANTIC_FINALIZE_V1',
    'status',v_validation->>'status',
    'result',v_result,
    'validation',v_validation
  );
END
$function$

