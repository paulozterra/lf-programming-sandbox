CREATE OR REPLACE FUNCTION public.lf_profile_selector_descriptor_sync_v1(p_profile_code text, p_descriptor jsonb, p_source_kind text, p_source_ref text, p_source_revision text, p_actor_execution_id text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
  a public.lf_activos%rowtype;
  v_slug text;
  v_key text;
BEGIN
  IF nullif(btrim(coalesce(p_profile_code,'')),'') IS NULL
     OR jsonb_typeof(p_descriptor) IS DISTINCT FROM 'object'
     OR p_descriptor->>'schema_version' IS DISTINCT FROM 'LF_PROFILE_SELECTION_DESCRIPTOR_V1'
     OR nullif(btrim(coalesce(p_descriptor->>'description','')),'') IS NULL
     OR jsonb_typeof(p_descriptor->'selection_evidence') IS DISTINCT FROM 'array'
     OR jsonb_array_length(p_descriptor->'selection_evidence')=0
     OR p_source_kind NOT IN ('GITHUB_SKILL','LF_ACTIVOS_RAW_PAYLOAD')
     OR nullif(btrim(coalesce(p_source_ref,'')),'') IS NULL
     OR nullif(btrim(coalesce(p_source_revision,'')),'') IS NULL
     OR nullif(btrim(coalesce(p_actor_execution_id,'')),'') IS NULL
  THEN
    RAISE EXCEPTION 'LF_PROFILE_SELECTOR_DESCRIPTOR_SYNC_INPUT_INVALID';
  END IF;

  IF p_source_kind='GITHUB_SKILL'
     AND p_source_revision !~ '^[0-9a-f]{40}$'
  THEN
    RAISE EXCEPTION 'LF_PROFILE_SELECTOR_DESCRIPTOR_GITHUB_REVISION_INVALID';
  END IF;

  IF p_source_kind='LF_ACTIVOS_RAW_PAYLOAD'
     AND p_source_revision !~ '^sha256:[0-9a-f]{64}$'
  THEN
    RAISE EXCEPTION 'LF_PROFILE_SELECTOR_DESCRIPTOR_RAW_REVISION_INVALID';
  END IF;

  SELECT * INTO a
  FROM public.lf_activos
  WHERE codigo_activo=p_profile_code
    AND tipo_activo='PERFIL'
    AND archived_at IS NULL
  LIMIT 1;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'LF_PROFILE_SELECTOR_DESCRIPTOR_PROFILE_NOT_FOUND';
  END IF;

  v_slug:=a.metadata->>'profile_slug';
  v_key:=a.metadata->>'canonical_profile_key';

  IF nullif(v_slug,'') IS NULL OR nullif(v_key,'') IS NULL THEN
    RAISE EXCEPTION 'LF_PROFILE_SELECTOR_DESCRIPTOR_PROFILE_NOT_CANONICAL';
  END IF;

  IF p_source_kind='GITHUB_SKILL' THEN
    IF nullif(a.metadata->>'repo_path','') IS NULL
       OR position('/'||(a.metadata->>'repo_path')||'/SKILL.md' IN p_source_ref)=0
    THEN
      RAISE EXCEPTION 'LF_PROFILE_SELECTOR_DESCRIPTOR_SOURCE_BINDING_INVALID';
    END IF;
  ELSE
    IF p_source_ref IS DISTINCT FROM
       'supabase://public/lf_activos/'||p_profile_code||'#raw_payload'
    THEN
      RAISE EXCEPTION 'LF_PROFILE_SELECTOR_DESCRIPTOR_RAW_SOURCE_BINDING_INVALID';
    END IF;
  END IF;

  INSERT INTO public.lf_profile_selection_registry_v1(
    profile_code,canonical_profile_key,profile_slug,descriptor,
    source_kind,source_ref,source_revision,descriptor_status,
    stale_reason,synced_at,synced_by_execution_id
  ) VALUES (
    p_profile_code,v_key,v_slug,p_descriptor,
    p_source_kind,p_source_ref,p_source_revision,'CURRENT',
    NULL,clock_timestamp(),p_actor_execution_id
  )
  ON CONFLICT(profile_code) DO UPDATE SET
    canonical_profile_key=excluded.canonical_profile_key,
    profile_slug=excluded.profile_slug,
    descriptor=excluded.descriptor,
    source_kind=excluded.source_kind,
    source_ref=excluded.source_ref,
    source_revision=excluded.source_revision,
    descriptor_status='CURRENT',
    stale_reason=NULL,
    synced_at=clock_timestamp(),
    synced_by_execution_id=excluded.synced_by_execution_id;

  RETURN jsonb_build_object(
    'outcome','SYNCED',
    'profile_code',p_profile_code,
    'canonical_profile_key',v_key,
    'profile_slug',v_slug,
    'descriptor_status','CURRENT',
    'source_kind',p_source_kind,
    'source_ref',p_source_ref,
    'source_revision',p_source_revision
  );
END
$function$

