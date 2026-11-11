CREATE OR REPLACE FUNCTION public.lf_profile_selector_catalog_v1()
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
WITH p AS (
  SELECT
    a.codigo_activo AS profile_code,
    a.nombre_canonico AS profile_name,
    a.subtipo_activo AS profile_subtype,
    a.estado_documental AS document_status,
    a.estado_operativo AS operational_status,
    a.runtime_estado AS runtime_status,
    a.version,
    a.metadata->>'canonical_profile_key' AS canonical_profile_key,
    a.metadata->>'profile_slug' AS profile_slug,
    r.descriptor,
    r.source_kind,
    r.source_ref,
    r.source_revision,
    sp.channels,
    sp.entry_policy,
    CASE
      WHEN nullif(a.metadata->>'canonical_profile_key','') IS NULL
        THEN 'NONCANONICAL_PROFILE_RECORD'
      WHEN r.profile_code IS NULL
        THEN 'DESCRIPTOR_MISSING'
      ELSE r.descriptor_status
    END AS descriptor_status,
    coalesce((src.info->>'eligible')::boolean,false) AS execution_source_eligible,
    src.info AS execution_source_eligibility,
    (
      nullif(a.metadata->>'canonical_profile_key','') IS NOT NULL
      AND r.profile_code IS NOT NULL
      AND r.descriptor_status='CURRENT'
      AND coalesce((src.info->>'eligible')::boolean,false)
      AND sp.profile_code IS NOT NULL
    ) AS selection_eligible
  FROM public.lf_activos a
  LEFT JOIN public.lf_profile_selection_registry_v1 r
    ON r.profile_code=a.codigo_activo
  LEFT JOIN public.lf_profile_selector_policy_v1 sp
    ON sp.profile_code=a.codigo_activo
  CROSS JOIN LATERAL (
    SELECT public.lf_profile_execution_source_eligibility_v1(a.codigo_activo) AS info
  ) src
  WHERE a.tipo_activo='PERFIL'
    AND a.archived_at IS NULL
),
agg AS (
  SELECT
    count(*)::integer AS total_profile_records,
    count(*) FILTER (WHERE canonical_profile_key IS NOT NULL)::integer AS canonical_profile_count,
    count(*) FILTER (WHERE selection_eligible)::integer AS selectable_profile_count,
    bool_and(
      CASE WHEN canonical_profile_key IS NULL THEN true
           ELSE descriptor_status='CURRENT' AND descriptor IS NOT NULL
      END
    ) AS all_canonical_descriptors_complete,
    coalesce(
      jsonb_agg(
        jsonb_build_object(
          'profile_code',profile_code,
          'profile_name',profile_name,
          'profile_subtype',profile_subtype,
          'canonical_profile_key',canonical_profile_key,
          'profile_slug',profile_slug,
          'document_status',document_status,
          'operational_status',operational_status,
          'runtime_status',runtime_status,
          'version',version,
          'channels',to_jsonb(channels),
          'entry_policy',entry_policy,
          'selection_eligible',selection_eligible,
          'execution_source_eligible',execution_source_eligible,
          'execution_source_eligibility',execution_source_eligibility,
          'descriptor_status',descriptor_status,
          'descriptor',descriptor,
          'descriptor_source_kind',source_kind,
          'descriptor_source_ref',source_ref,
          'descriptor_source_revision',source_revision
        )
        ORDER BY profile_code
      ),
      '[]'::jsonb
    ) AS profiles
  FROM p
)
SELECT jsonb_build_object(
  'schema_version','LF_PROFILE_SELECTOR_CATALOG_V1',
  'selection_mode','DETERMINISTIC_DISCOVERY_ONLY',
  'semantic_selection_performed',false,
  'total_profile_records',total_profile_records,
  'canonical_profile_count',canonical_profile_count,
  'selectable_profile_count',selectable_profile_count,
  'all_canonical_descriptors_complete',all_canonical_descriptors_complete,
  'profiles',profiles
)
FROM agg
$function$

