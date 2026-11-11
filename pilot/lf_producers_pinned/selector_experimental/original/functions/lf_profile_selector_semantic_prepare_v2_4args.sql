CREATE OR REPLACE FUNCTION public.lf_profile_selector_semantic_prepare_v2(p_literal_request text, p_channel text, p_derivation jsonb, p_stage1 jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public', 'extensions'
AS $function$
declare
  v_catalog jsonb; v_all jsonb; v_profiles jsonb; v_request_sha text; v_catalog_sha text;
  v_channel text:=nullif(btrim(coalesce(p_channel,'')),'');
  v_src text:=nullif(btrim(coalesce(p_derivation->>'source_execution_id','')),'');
  v_ok boolean; v_deriv jsonb:=NULL;
  v_asset text:=upper(nullif(btrim(coalesce(p_stage1#>>'{alcance,target_type}','')),''));
  v_entry text[]:='{}';
begin
  if nullif(btrim(coalesce(p_literal_request,'')),'') is null then
    raise exception 'LF_PROFILE_SELECTOR_LITERAL_REQUEST_REQUIRED';
  end if;
  if v_channel is not null and v_channel not in ('PRODUCTO','PROGRAMACION','OPERACIONES') then
    raise exception 'LF_PROFILE_SELECTOR_CHANNEL_INVALID';
  end if;
  v_catalog:=public.lf_profile_selector_catalog_v1();
  if coalesce((v_catalog->>'all_canonical_descriptors_complete')::boolean,false) is not true
     or coalesce((v_catalog->>'selectable_profile_count')::integer,0)<=0
     or v_catalog->>'selection_mode'<>'DETERMINISTIC_DISCOVERY_ONLY'
     or coalesce((v_catalog->>'semantic_selection_performed')::boolean,true) is true
  then
    raise exception 'LF_PROFILE_SELECTOR_CATALOG_NOT_READY:%',left(v_catalog::text,1200);
  end if;
  v_request_sha:=encode(extensions.digest(convert_to(p_literal_request,'UTF8'),'sha256'),'hex');
  if v_src is not null then
    select true into v_ok
    from public.lf_operation_execution e
    join public.lf_profile_selector_policy_v1 sp on sp.profile_code=e.target_code
    where e.execution_id=v_src and e.operation_code='EJECUCION_PERFIL_LF' and e.status='COMPLETED'
      and e.request_sha256=v_request_sha and sp.entry_policy='DIRECT';
    if v_ok is true then v_deriv:=jsonb_build_object('source_execution_id',v_src); end if;
  end if;
  select coalesce(jsonb_agg(p order by p->>'profile_code'),'[]'::jsonb) into v_all
  from jsonb_array_elements(v_catalog->'profiles') p
  where coalesce((p->>'selection_eligible')::boolean,false) is true
    and p->>'descriptor_status'='CURRENT' and jsonb_typeof(p->'descriptor')='object'
    and nullif(btrim(coalesce(p#>>'{descriptor,description}','')),'') is not null;
  if jsonb_array_length(v_all)<>coalesce((v_catalog->>'selectable_profile_count')::integer,-1) then
    raise exception 'LF_PROFILE_SELECTOR_PREPARE_CARDINALITY_DRIFT';
  end if;
  -- Perfiles que entran por AUTORIDAD: el tipo de activo que pide la solicitud tiene operaciones de escritura
  -- activas en la tabla de rutas, y NINGUN perfil de entrada directa tiene esa operacion en la matriz de autoridad.
  -- Entonces se ofrecen los perfiles de solo derivacion que si la tienen.
  if v_asset is not null and v_deriv is null then
    select coalesce(array_agg(distinct a.profile_code),'{}') into v_entry
    from public.lf_profile_write_authority_v1 a
    join public.lf_router_action_registry r on r.operation_code=a.operation_code
    join public.lf_profile_selector_policy_v1 sp on sp.profile_code=a.profile_code
    where a.status='ACTIVE' and r.status='ACTIVE' and r.write_allowed is true
      and r.asset_type=v_asset and sp.entry_policy='DERIVATION_ONLY'
      and not exists (
        select 1 from public.lf_profile_write_authority_v1 a2
        join public.lf_profile_selector_policy_v1 sp2 on sp2.profile_code=a2.profile_code
        where a2.operation_code=a.operation_code and a2.status='ACTIVE' and sp2.entry_policy='DIRECT');
  end if;
  select coalesce(jsonb_agg(p order by p->>'profile_code'),'[]'::jsonb) into v_profiles
  from jsonb_array_elements(v_all) p
  where (v_channel is null or (p->'channels') ? v_channel)
    and (p->>'entry_policy'='DIRECT' or v_deriv is not null or (p->>'profile_code')=any(v_entry));
  v_catalog_sha:=encode(extensions.digest(convert_to(v_profiles::text,'UTF8'),'sha256'),'hex');
  return jsonb_build_object(
    'schema_version','LF_PROFILE_SELECTOR_SEMANTIC_REQUEST_V1','selector','PROFILE_SELECTOR_LF',
    'literal_request',p_literal_request,'request_sha256',v_request_sha,'channel',v_channel,'derivation',v_deriv,
    'catalog_schema_version',v_catalog->>'schema_version','catalog_sha256',v_catalog_sha,
    'catalog_profile_count',jsonb_array_length(v_profiles),'candidate_profiles',v_profiles,
    'authority_entry_profiles',to_jsonb(v_entry),'authority_asset_type',v_asset,
    'allowed_decisions',jsonb_build_array('SELECTED','AMBIGUOUS','NO_MATCH'),
    'semantic_rules',jsonb_build_array('COMPARE_LITERAL_REQUEST_AGAINST_ALL_CANDIDATE_DESCRIPTORS','DO_NOT_PRESELECT_BY_KEYWORD_OR_PROFILE_NAME','USE_ONLY_DECLARED_DESCRIPTOR_EVIDENCE','SELECTED_REQUIRES_ONE_PROFILE','AMBIGUOUS_REQUIRES_TWO_OR_MORE_MATERIAL_CANDIDATES','NO_MATCH_WHEN_NO_DECLARED_PROFILE_CAPABILITY_FITS','NO_ROUTE_OR_EFFECT_AUTHORITY','CANDIDATES_ALREADY_FILTERED_BY_CHANNEL_AND_ENTRY_POLICY','MUTATION_REQUESTS_SELECT_ANALYSIS_PROFILE_FIRST'),
    'semantic_output_contract',jsonb_build_object('decision','SELECTED|AMBIGUOUS|NO_MATCH','selected_profile_code','string|null','ambiguous_profile_codes','array<string>','reason','non-empty string',
      'evidence_refs',jsonb_build_array(jsonb_build_object('profile_code','candidate profile code','kind','selection_evidence.kind','source_section','selection_evidence.source_section')),'material_ambiguities','array<object>'),
    'route_authority',false,'effect_authority',false,'downstream_execution_allowed',false);
end $function$

