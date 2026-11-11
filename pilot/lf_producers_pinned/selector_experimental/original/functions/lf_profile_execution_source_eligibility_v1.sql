CREATE OR REPLACE FUNCTION public.lf_profile_execution_source_eligibility_v1(p_profile_code text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
  a public.lf_activos%rowtype;
  r public.lf_profile_selection_registry_v1%rowtype;
  v_repo_path text;
  v_expected text;
  v_entrypoint text;
  v_eligible boolean:=false;
  v_reason text;
BEGIN
  IF nullif(btrim(coalesce(p_profile_code,'')),'') IS NULL THEN
    RETURN jsonb_build_object(
      'eligible',false,
      'reason','PROFILE_CODE_REQUIRED'
    );
  END IF;

  SELECT * INTO a
  FROM public.lf_activos
  WHERE codigo_activo=p_profile_code
    AND tipo_activo='PERFIL'
    AND archived_at IS NULL
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN jsonb_build_object(
      'eligible',false,
      'profile_code',p_profile_code,
      'reason','PROFILE_NOT_CURRENT'
    );
  END IF;

  SELECT * INTO r
  FROM public.lf_profile_selection_registry_v1
  WHERE profile_code=p_profile_code
  LIMIT 1;

  v_repo_path:=nullif(btrim(coalesce(a.metadata->>'repo_path','')),'');
  v_expected:=nullif(btrim(coalesce(a.ruta_esperada,'')),'');
  v_entrypoint:=case
    when v_expected is null then null
    when v_expected like '%.md' then v_expected
    when right(v_expected,1)='/' then v_expected||'SKILL.md'
    else v_expected||'/SKILL.md'
  end;

  v_eligible:=
       nullif(a.metadata->>'canonical_profile_key','') IS NOT NULL
   AND nullif(a.metadata->>'profile_slug','') IS NOT NULL
   AND r.profile_code IS NOT NULL
   AND r.descriptor_status='CURRENT'
   AND v_repo_path IS NOT NULL
   AND v_repo_path ~ '^profiles/[a-z0-9][a-z0-9_/-]{1,180}$'
   AND v_entrypoint IS NOT NULL
   AND v_entrypoint = v_repo_path||'/SKILL.md';

  v_reason:=case
    when nullif(a.metadata->>'canonical_profile_key','') IS NULL
      or nullif(a.metadata->>'profile_slug','') IS NULL
      then 'PROFILE_IDENTITY_NOT_CANONICAL'
    when r.profile_code IS NULL or r.descriptor_status<>'CURRENT'
      then 'PROFILE_DESCRIPTOR_NOT_CURRENT'
    when v_repo_path IS NULL or v_entrypoint IS NULL
      then 'PROFILE_EXECUTION_SOURCE_UNRESOLVED'
    when v_repo_path !~ '^profiles/[a-z0-9][a-z0-9_/-]{1,180}$'
      or v_entrypoint <> v_repo_path||'/SKILL.md'
      then 'PROFILE_EXECUTION_SOURCE_BINDING_INVALID'
    else 'PROFILE_EXECUTION_SOURCE_READY'
  end;

  RETURN jsonb_build_object(
    'eligible',v_eligible,
    'profile_code',a.codigo_activo,
    'profile_slug',a.metadata->>'profile_slug',
    'repo_path',v_repo_path,
    'entrypoint_path',v_entrypoint,
    'descriptor_status',coalesce(r.descriptor_status,'MISSING'),
    'runtime_status',a.runtime_estado,
    'reason',v_reason
  );
END
$function$

