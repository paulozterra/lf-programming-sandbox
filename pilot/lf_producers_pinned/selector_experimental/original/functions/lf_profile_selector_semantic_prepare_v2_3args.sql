CREATE OR REPLACE FUNCTION public.lf_profile_selector_semantic_prepare_v2(p_literal_request text, p_channel text, p_derivation jsonb)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public', 'extensions'
AS $function$ select public.lf_profile_selector_semantic_prepare_v2(p_literal_request,p_channel,p_derivation,NULL::jsonb) $function$

