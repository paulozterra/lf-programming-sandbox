CREATE OR REPLACE FUNCTION public.lf_profile_selector_semantic_validate_v1(p_request jsonb, p_result jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public', 'extensions'
AS $function$
DECLARE
  v_current jsonb;
  v_decision text;
  v_selected text;
  v_ambiguous jsonb;
  v_evidence jsonb;
  v_material jsonb;
  v_reason text;
  v_expected_receipt text;
  v_blocking jsonb:='[]'::jsonb;
  v_bad integer:=0;
BEGIN
  IF jsonb_typeof(p_request)<>'object'
     OR jsonb_typeof(p_result)<>'object'
  THEN
    RETURN jsonb_build_object(
      'schema_version','LF_PROFILE_SELECTOR_SEMANTIC_VALIDATION_V1',
      'status','BLOCKED',
      'blocking_codes',jsonb_build_array('PROFILE_SELECTOR_SEMANTIC_OBJECT_REQUIRED'),
      'route_authority',false,
      'effect_authority',false,
      'downstream_execution_allowed',false
    );
  END IF;

  BEGIN
    v_current:=public.lf_profile_selector_semantic_prepare_v2(p_request->>'literal_request', nullif(p_request->>'channel',''), p_request->'derivation', case when nullif(p_request->>'authority_asset_type','') is null then NULL::jsonb else jsonb_build_object('alcance',jsonb_build_object('target_type',p_request->>'authority_asset_type')) end);
  EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object(
      'schema_version','LF_PROFILE_SELECTOR_SEMANTIC_VALIDATION_V1',
      'status','BLOCKED',
      'blocking_codes',jsonb_build_array('PROFILE_SELECTOR_CURRENT_CATALOG_UNAVAILABLE'),
      'route_authority',false,
      'effect_authority',false,
      'downstream_execution_allowed',false
    );
  END;

  IF p_request->>'schema_version'<>'LF_PROFILE_SELECTOR_SEMANTIC_REQUEST_V1'
     OR p_request->>'selector'<>'PROFILE_SELECTOR_LF'
     OR p_request->>'request_sha256' IS DISTINCT FROM v_current->>'request_sha256'
     OR p_request->>'catalog_sha256' IS DISTINCT FROM v_current->>'catalog_sha256'
     OR p_request->'candidate_profiles' IS DISTINCT FROM v_current->'candidate_profiles'
     OR p_request->>'catalog_profile_count' IS DISTINCT FROM v_current->>'catalog_profile_count'
  THEN
    v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_REQUEST_STALE_OR_INVALID');
  END IF;

  IF p_result ?| ARRAY[
       'operation_code','action_code','candidate_action_code',
       'executor','executor_mode','router_action_binding',
       'route_authority','effect_authority','downstream_execution_allowed'
     ]
  THEN
    v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_RESULT_AUTHORITY_FIELD_FORBIDDEN');
  END IF;

  IF p_result->>'schema_version'<>'LF_PROFILE_SELECTOR_SEMANTIC_RESULT_V1'
     OR p_result->>'request_sha256' IS DISTINCT FROM p_request->>'request_sha256'
     OR p_result->>'catalog_sha256' IS DISTINCT FROM p_request->>'catalog_sha256'
     OR p_result->>'catalog_profile_count' IS DISTINCT FROM p_request->>'catalog_profile_count'
  THEN
    v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_RESULT_BINDING_INVALID');
  END IF;

  v_decision:=upper(coalesce(p_result->>'decision',''));
  v_selected:=nullif(btrim(coalesce(p_result->>'selected_profile_code','')),'');
  v_ambiguous:=coalesce(p_result->'ambiguous_profile_codes','[]'::jsonb);
  v_evidence:=coalesce(p_result->'evidence_refs','[]'::jsonb);
  v_material:=coalesce(p_result->'material_ambiguities','[]'::jsonb);
  v_reason:=nullif(btrim(coalesce(p_result->>'reason','')),'');

  IF v_decision NOT IN ('SELECTED','AMBIGUOUS','NO_MATCH')
     OR jsonb_typeof(v_ambiguous)<>'array'
     OR jsonb_typeof(v_evidence)<>'array'
     OR jsonb_typeof(v_material)<>'array'
     OR v_reason IS NULL
  THEN
    v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_RESULT_SHAPE_INVALID');
  END IF;

  IF v_selected IS NOT NULL AND NOT EXISTS(
    SELECT 1
    FROM jsonb_array_elements(p_request->'candidate_profiles') p
    WHERE p->>'profile_code'=v_selected
      AND coalesce((p->>'selection_eligible')::boolean,false) IS TRUE
      AND p->>'descriptor_status'='CURRENT'
  ) THEN
    v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_SELECTED_OUTSIDE_CATALOG');
  END IF;

  IF jsonb_typeof(v_ambiguous)='array' THEN
    SELECT count(*) INTO v_bad
    FROM jsonb_array_elements(v_ambiguous) x(item)
    WHERE jsonb_typeof(x.item)<>'string'
       OR NOT EXISTS(
          SELECT 1
          FROM jsonb_array_elements(p_request->'candidate_profiles') p
          WHERE p->>'profile_code'=x.item#>>'{}'
            AND coalesce((p->>'selection_eligible')::boolean,false) IS TRUE
            AND p->>'descriptor_status'='CURRENT'
       );

    IF v_bad>0 THEN
      v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_AMBIGUOUS_OUTSIDE_CATALOG');
    END IF;

    IF (
      SELECT count(*) FROM (
        SELECT DISTINCT x.item#>>'{}' AS code
        FROM jsonb_array_elements(v_ambiguous) x(item)
      ) q
    ) <> jsonb_array_length(v_ambiguous)
    THEN
      v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_AMBIGUOUS_DUPLICATE');
    END IF;
  END IF;

  IF jsonb_typeof(v_evidence)='array' THEN
    SELECT count(*) INTO v_bad
    FROM jsonb_array_elements(v_evidence) e(item)
    WHERE jsonb_typeof(e.item)<>'object'
       OR nullif(e.item->>'profile_code','') IS NULL
       OR nullif(e.item->>'kind','') IS NULL
       OR nullif(e.item->>'source_section','') IS NULL
       OR NOT EXISTS(
          SELECT 1
          FROM jsonb_array_elements(p_request->'candidate_profiles') p,
               LATERAL jsonb_array_elements(p#>'{descriptor,selection_evidence}') se(item)
          WHERE p->>'profile_code'=e.item->>'profile_code'
            AND se.item->>'kind'=e.item->>'kind'
            AND se.item->>'source_section'=e.item->>'source_section'
       );

    IF v_bad>0 THEN
      v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_EVIDENCE_REF_INVALID');
    END IF;
  END IF;

  IF v_decision='SELECTED' THEN
    IF v_selected IS NULL
       OR jsonb_array_length(v_ambiguous)<>0
       OR jsonb_array_length(v_material)<>0
       OR NOT EXISTS(
          SELECT 1
          FROM jsonb_array_elements(v_evidence) e(item)
          WHERE e.item->>'profile_code'=v_selected
       )
    THEN
      v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_SELECTED_CONTRACT_INVALID');
    END IF;
  ELSIF v_decision='AMBIGUOUS' THEN
    IF v_selected IS NOT NULL
       OR jsonb_array_length(v_ambiguous)<2
       OR jsonb_array_length(v_material)=0
       OR EXISTS(
          SELECT 1
          FROM jsonb_array_elements(v_ambiguous) x(item)
          WHERE NOT EXISTS(
            SELECT 1
            FROM jsonb_array_elements(v_evidence) e(item)
            WHERE e.item->>'profile_code'=x.item#>>'{}'
          )
       )
    THEN
      v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_AMBIGUOUS_CONTRACT_INVALID');
    END IF;
  ELSIF v_decision='NO_MATCH' THEN
    IF v_selected IS NOT NULL OR jsonb_array_length(v_ambiguous)<>0 THEN
      v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_NO_MATCH_CONTRACT_INVALID');
    END IF;
  END IF;

  v_expected_receipt:=encode(
    extensions.digest(
      convert_to((p_result-'semantic_receipt_sha256')::text,'UTF8'),
      'sha256'
    ),
    'hex'
  );

  IF coalesce(p_result->>'semantic_receipt_sha256','') !~ '^[0-9a-f]{64}$'
     OR p_result->>'semantic_receipt_sha256' IS DISTINCT FROM v_expected_receipt
  THEN
    v_blocking:=v_blocking||jsonb_build_array('PROFILE_SELECTOR_SEMANTIC_RECEIPT_INVALID');
  END IF;

  RETURN jsonb_build_object(
    'schema_version','LF_PROFILE_SELECTOR_SEMANTIC_VALIDATION_V1',
    'status',case when jsonb_array_length(v_blocking)=0 then 'VALID' else 'BLOCKED' end,
    'decision',v_decision,
    'selected_profile_code',v_selected,
    'ambiguous_profile_codes',v_ambiguous,
    'blocking_codes',v_blocking,
    'request_sha256',p_request->>'request_sha256',
    'catalog_sha256',p_request->>'catalog_sha256',
    'catalog_profile_count',p_request->>'catalog_profile_count',
    'route_authority',false,
    'effect_authority',false,
    'downstream_execution_allowed',false,
    'next_action',case
      when jsonb_array_length(v_blocking)>0 then 'STAY_BLOCKED'
      when v_decision='SELECTED' then 'PROFILE_SELECTION_READY_FOR_GATE2'
      when v_decision='AMBIGUOUS' then 'HUMAN_OR_CALLER_DECISION_REQUIRED'
      else 'NO_PROFILE_MATCH_BLOCKED'
    end
  );
END
$function$

