-- EXPERIMENT ONLY. Do not deploy to production. The seven original functions remain untouched.
CREATE OR REPLACE FUNCTION public.lf_profile_selector_catalog_v2_exp(p_channel text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path TO 'pg_catalog','public','extensions'
AS $$
DECLARE v_catalog jsonb; v_profiles jsonb; v_blocked jsonb; v_count integer;
BEGIN
 IF p_channel IS NOT NULL AND p_channel NOT IN ('PRODUCTO','PROGRAMACION','OPERACIONES') THEN
   RAISE EXCEPTION 'EXP_CHANNEL_INVALID';
 END IF;
 v_catalog := public.lf_profile_selector_catalog_v1();
 SELECT coalesce(jsonb_agg(p ORDER BY p->>'profile_code'),'[]'::jsonb) INTO v_profiles
 FROM jsonb_array_elements(v_catalog->'profiles') p
 WHERE p_channel IS NULL OR (p->'channels') ? p_channel;
 SELECT coalesce(jsonb_agg(jsonb_build_object('profile_code',p->>'profile_code',
             'descriptor_status',p->>'descriptor_status','reason','DESCRIPTOR_NOT_CURRENT')
             ORDER BY p->>'profile_code'),'[]'::jsonb) INTO v_blocked
 FROM jsonb_array_elements(v_profiles) p
 WHERE p->>'descriptor_status' <> 'CURRENT' OR p->'descriptor' IS NULL;
 SELECT count(*) INTO v_count FROM jsonb_array_elements(v_profiles) p
 WHERE p->>'descriptor_status'='CURRENT'
   AND coalesce((p->>'selection_eligible')::boolean,false)
   AND jsonb_typeof(p->'descriptor')='object';
 RETURN jsonb_build_object('schema_version','LF_PROFILE_SELECTOR_CATALOG_V2_EXP',
  'channel',p_channel,'profiles',v_profiles,'blocked_profiles',v_blocked,
  'selectable_profile_count',v_count,
  'global_descriptor_gate_applied',false,'experiment_only',true);
END $$;

CREATE OR REPLACE FUNCTION public.lf_profile_selector_semantic_prepare_v3_exp(
 p_literal_request text, p_project_ref text, p_area text, p_paths jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path TO 'pg_catalog','public','extensions'
AS $$
DECLARE v_area text:=upper(btrim(coalesce(p_area,'')));
 v_areas text[]:='{}'; v_path text; v_found text; v_matches integer;
 v_paths jsonb; v_catalog jsonb; v_profiles jsonb; v_count integer;
 v_sha text; v_request jsonb; v_classified text; v_rules jsonb;
BEGIN
 IF nullif(btrim(coalesce(p_literal_request,'')),'') IS NULL
  OR nullif(btrim(coalesce(p_project_ref,'')),'') IS NULL
  OR jsonb_typeof(p_paths) IS DISTINCT FROM 'array'
  OR jsonb_array_length(p_paths)=0 THEN
  RETURN jsonb_build_object('status','BLOCKED','blocking_code','LOTE_INPUT_INVALID');
 END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('area',area,'path_prefix',path_prefix)
   ORDER BY area,path_prefix),'[]'::jsonb) INTO v_rules
 FROM public.lf_project_area_pattern_exp WHERE project_ref=p_project_ref;
 IF jsonb_array_length(v_rules)=0 THEN
   RETURN jsonb_build_object('status','BLOCKED','blocking_code','PROJECT_RULES_NOT_FOUND');
 END IF;
 FOR v_path IN SELECT value #>> '{}' FROM jsonb_array_elements(p_paths) LOOP
  IF v_path IS NULL OR btrim(v_path)='' OR v_path LIKE '/%'
    OR position('..' IN v_path)>0 OR position(chr(92) IN v_path)>0
    OR jsonb_typeof(to_jsonb(v_path)) IS DISTINCT FROM 'string' THEN
    RETURN jsonb_build_object('status','BLOCKED','blocking_code','LOTE_PATH_INVALID');
  END IF;
  SELECT count(DISTINCT area),min(area) INTO v_matches,v_found
  FROM public.lf_project_area_pattern_exp
  WHERE project_ref=p_project_ref AND left(v_path,length(path_prefix))=path_prefix;
  IF v_matches=0 THEN
    RETURN jsonb_build_object('status','BLOCKED','blocking_code','LOTE_PATH_UNCLASSIFIED');
  ELSIF v_matches>1 THEN
    RETURN jsonb_build_object('status','BLOCKED','blocking_code','LOTE_PATH_RULE_CONFLICT');
  END IF;
  IF NOT v_found=ANY(v_areas) THEN v_areas:=array_append(v_areas,v_found); END IF;
 END LOOP;
 IF cardinality(v_areas)>1 THEN
   RETURN jsonb_build_object('status','BLOCKED','blocking_code','LOTE_MULTI_AREA_BLOCKED','areas',to_jsonb(v_areas));
 END IF;
 v_classified:=v_areas[1];
 IF v_area<>v_classified OR v_area NOT IN ('BACKEND','FRONTEND','DATA') THEN
   RETURN jsonb_build_object('status','BLOCKED','blocking_code','LOTE_AREA_ROUTE_MISMATCH','classified_area',v_classified);
 END IF;
 SELECT coalesce(jsonb_agg(value ORDER BY value #>> '{}'),'[]'::jsonb) INTO v_paths
 FROM (SELECT DISTINCT value FROM jsonb_array_elements(p_paths) e(value)) q;
 v_catalog:=public.lf_profile_selector_catalog_v2_exp('PROGRAMACION');
 SELECT coalesce(jsonb_agg(p ORDER BY p->>'profile_code'),'[]'::jsonb) INTO v_profiles
 FROM jsonb_array_elements(v_catalog->'profiles') p
 JOIN public.lf_profile_area_policy_exp pol ON pol.profile_code=p->>'profile_code'
 WHERE pol.areas ? v_area
   AND p->>'descriptor_status'='CURRENT'
   AND coalesce((p->>'selection_eligible')::boolean,false)
   AND p->>'entry_policy'='DIRECT';
 v_count:=jsonb_array_length(v_profiles);
 IF v_count=0 THEN
   RETURN jsonb_build_object('status','BLOCKED','blocking_code','NO_PROFILE_FOR_AREA','area',v_area);
 END IF;
 v_sha:=encode(extensions.digest(convert_to(v_profiles::text,'UTF8'),'sha256'),'hex');
 v_request:=jsonb_build_object(
   'schema_version','LF_PROFILE_SELECTOR_SEMANTIC_REQUEST_V3_EXP',
   'selector','PROFILE_SELECTOR_LF_EXP',
   'literal_request',p_literal_request,
   'request_sha256',encode(extensions.digest(convert_to(p_literal_request,'UTF8'),'sha256'),'hex'),
   'project_ref',p_project_ref,'project_rules',v_rules,
   'channel','PROGRAMACION','area',v_area,'file_paths',v_paths,
   'paths_sha256',encode(extensions.digest(convert_to(v_paths::text,'UTF8'),'sha256'),'hex'),
   'catalog_sha256',v_sha,'catalog_profile_count',v_count,
   'candidate_profiles',v_profiles,'route_authority',false,
   'effect_authority',false,'downstream_execution_allowed',false);
 RETURN jsonb_build_object('status','READY','request',v_request,
   'deterministic_area',v_area,'experiment_only',true);
END $$;

CREATE OR REPLACE FUNCTION public.lf_profile_selector_semantic_validate_v2_exp(
 p_request jsonb, p_result jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path TO 'pg_catalog','public','extensions'
AS $$
DECLARE v_fresh jsonb; v_errors jsonb:='[]'::jsonb; v_decision text;
 v_code text; v_evidence jsonb; v_receipt text; v_clean jsonb;
 v_candidate jsonb; v_e jsonb; v_ambiguous jsonb; v_material jsonb;
BEGIN
 IF jsonb_typeof(p_request) IS DISTINCT FROM 'object'
    OR jsonb_typeof(p_result) IS DISTINCT FROM 'object' THEN
  RETURN jsonb_build_object('status','BLOCKED','blocking_codes',jsonb_build_array('EXP_OBJECT_REQUIRED'));
 END IF;
 v_fresh:=public.lf_profile_selector_semantic_prepare_v3_exp(
   p_request->>'literal_request',p_request->>'project_ref',p_request->>'area',p_request->'file_paths');
 IF v_fresh->>'status' IS DISTINCT FROM 'READY'
    OR v_fresh->'request' IS DISTINCT FROM p_request THEN
  v_errors:=v_errors||jsonb_build_array('EXP_REQUEST_STALE_OR_INVALID');
 END IF;
 IF p_result ?| ARRAY['operation_code','action_code','executor','executor_mode',
                     'router_action_binding','route_authority','effect_authority',
                     'downstream_execution_allowed','authority_asset_type'] THEN
  v_errors:=v_errors||jsonb_build_array('EXP_AUTHORITY_FIELD_FORBIDDEN');
 END IF;
 IF p_result->>'schema_version' IS DISTINCT FROM 'LF_PROFILE_SELECTOR_SEMANTIC_RESULT_V2_EXP'
   OR p_result->>'request_sha256' IS DISTINCT FROM p_request->>'request_sha256'
   OR p_result->>'catalog_sha256' IS DISTINCT FROM p_request->>'catalog_sha256'
   OR p_result->>'paths_sha256' IS DISTINCT FROM p_request->>'paths_sha256'
   OR p_result->>'area' IS DISTINCT FROM p_request->>'area' THEN
   v_errors:=v_errors||jsonb_build_array('EXP_RESULT_BINDING_INVALID');
 END IF;
 v_clean:=p_result-'semantic_receipt_sha256';
 v_receipt:=encode(extensions.digest(convert_to(v_clean::text,'UTF8'),'sha256'),'hex');
 IF p_result->>'semantic_receipt_sha256' IS DISTINCT FROM v_receipt THEN
   v_errors:=v_errors||jsonb_build_array('EXP_SEMANTIC_RECEIPT_INVALID');
 END IF;
 v_decision:=upper(coalesce(p_result->>'decision',''));
 v_code:=nullif(btrim(coalesce(p_result->>'selected_profile_code','')),'');
 v_evidence:=coalesce(p_result->'evidence_refs','[]'::jsonb);
 v_ambiguous:=coalesce(p_result->'ambiguous_profile_codes','[]'::jsonb);
 v_material:=coalesce(p_result->'material_ambiguities','[]'::jsonb);
 IF v_decision NOT IN ('SELECTED','AMBIGUOUS','NO_MATCH')
  OR jsonb_typeof(v_evidence) IS DISTINCT FROM 'array'
  OR jsonb_typeof(v_ambiguous) IS DISTINCT FROM 'array'
  OR jsonb_typeof(v_material) IS DISTINCT FROM 'array'
  OR nullif(btrim(coalesce(p_result->>'reason','')),'') IS NULL THEN
   v_errors:=v_errors||jsonb_build_array('EXP_RESULT_SHAPE_INVALID');
 ELSE
  IF v_decision='SELECTED' THEN
   SELECT p INTO v_candidate FROM jsonb_array_elements(p_request->'candidate_profiles') p
   WHERE p->>'profile_code'=v_code;
   IF v_code IS NULL OR v_candidate IS NULL OR NOT EXISTS (SELECT 1 FROM public.lf_profile_area_policy_exp pol
     WHERE pol.profile_code=v_code AND pol.areas ? (p_request->>'area'))
    OR jsonb_array_length(v_ambiguous)<>0 OR jsonb_array_length(v_material)<>0 THEN
    v_errors:=v_errors||jsonb_build_array('EXP_AREA_PROFILE_MISMATCH');
   END IF;
  ELSIF v_decision='NO_MATCH' THEN
   IF v_code IS NOT NULL OR jsonb_array_length(v_ambiguous)<>0 THEN
     v_errors:=v_errors||jsonb_build_array('EXP_NO_MATCH_INVALID');
   END IF;
  ELSE
   IF v_code IS NOT NULL OR jsonb_array_length(v_ambiguous)<2
     OR jsonb_array_length(v_material)=0
     OR (SELECT count(DISTINCT item #>> '{}') FROM jsonb_array_elements(v_ambiguous) z(item)) <> jsonb_array_length(v_ambiguous)
     OR EXISTS (
       SELECT 1 FROM jsonb_array_elements(v_ambiguous) z(item)
       WHERE NOT EXISTS (
         SELECT 1 FROM jsonb_array_elements(p_request->'candidate_profiles') c
         WHERE c->>'profile_code'=z.item #>> '{}'
       )
     ) THEN
     v_errors:=v_errors||jsonb_build_array('EXP_AMBIGUOUS_INVALID');
   END IF;
  END IF;
  IF v_decision='SELECTED' AND NOT EXISTS (
    SELECT 1 FROM jsonb_array_elements(v_evidence) ev
    JOIN LATERAL jsonb_array_elements(coalesce(v_candidate#>'{descriptor,selection_evidence}','[]'::jsonb)) e ON true
    WHERE ev->>'profile_code'=v_code AND ev->>'kind'=e->>'kind'
     AND ev->>'source_section'=e->>'source_section'
  ) THEN
    v_errors:=v_errors||jsonb_build_array('EXP_EVIDENCE_INVALID');
  END IF;
  IF EXISTS (
    SELECT 1 FROM jsonb_array_elements(v_evidence) ev
    WHERE NOT EXISTS (
       SELECT 1 FROM jsonb_array_elements(p_request->'candidate_profiles') p,
         LATERAL jsonb_array_elements(coalesce(p#>'{descriptor,selection_evidence}','[]'::jsonb)) e
       WHERE p->>'profile_code'=ev->>'profile_code'
         AND e->>'kind'=ev->>'kind' AND e->>'source_section'=ev->>'source_section'
    )
  ) THEN
    v_errors:=v_errors||jsonb_build_array('EXP_EVIDENCE_INVALID');
  END IF;
 END IF;
 RETURN jsonb_build_object('schema_version','LF_PROFILE_SELECTOR_SEMANTIC_VALIDATION_V2_EXP',
   'status',CASE WHEN jsonb_array_length(v_errors)=0 THEN 'VALID' ELSE 'BLOCKED' END,
   'blocking_codes',v_errors,'selected_profile_code',v_code,
   'route_authority',false,'effect_authority',false,'downstream_execution_allowed',false);
END $$;

CREATE OR REPLACE FUNCTION public.lf_profile_selector_semantic_finalize_v2_exp(
 p_request jsonb, p_draft jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path TO 'pg_catalog','public','extensions'
AS $$
DECLARE v_result jsonb; v_receipt text; v_valid jsonb;
BEGIN
 IF jsonb_typeof(p_draft) IS DISTINCT FROM 'object'
 OR p_draft ?| ARRAY['schema_version','request_sha256','catalog_sha256',
  'paths_sha256','semantic_receipt_sha256','operation_code','action_code',
  'executor','executor_mode','route_authority','effect_authority',
  'downstream_execution_allowed','authority_asset_type','router_action_binding'] THEN
  RETURN jsonb_build_object('status','BLOCKED','blocking_code','EXP_DRAFT_CONTROL_FIELD_FORBIDDEN');
 END IF;
 v_result:=jsonb_build_object('schema_version','LF_PROFILE_SELECTOR_SEMANTIC_RESULT_V2_EXP',
 'request_sha256',p_request->>'request_sha256','catalog_sha256',p_request->>'catalog_sha256',
 'paths_sha256',p_request->>'paths_sha256','area',p_request->>'area',
 'decision',upper(coalesce(p_draft->>'decision','')),
 'selected_profile_code',p_draft->>'selected_profile_code',
 'ambiguous_profile_codes',coalesce(p_draft->'ambiguous_profile_codes','[]'::jsonb),
 'reason',p_draft->>'reason','evidence_refs',coalesce(p_draft->'evidence_refs','[]'::jsonb),
 'material_ambiguities',coalesce(p_draft->'material_ambiguities','[]'::jsonb));
 v_receipt:=encode(extensions.digest(convert_to(v_result::text,'UTF8'),'sha256'),'hex');
 v_result:=v_result||jsonb_build_object('semantic_receipt_sha256',v_receipt);
 v_valid:=public.lf_profile_selector_semantic_validate_v2_exp(p_request,v_result);
 RETURN jsonb_build_object('status',v_valid->>'status','validation',v_valid,'result',v_result);
END $$;
