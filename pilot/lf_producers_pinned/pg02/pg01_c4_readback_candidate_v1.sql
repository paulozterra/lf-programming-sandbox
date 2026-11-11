-- PG-01_C4 READBACK CANDIDATE, NOT A MIGRATION. No deployment or grants authorized.
-- Dedicated migration and PG01 owner review required before installation.
-- Reuse V2 exact binding for context; no second receipt ledger or source of authority.
CREATE OR REPLACE FUNCTION private.fn_lf_programming_pg01_c4_framework_readback_candidate_v1(p_binding jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path TO 'pg_catalog','private' AS $fn$
DECLARE
  v_receipt jsonb;
  v_record jsonb;
BEGIN
  -- SECURITY INVOKER must run only from a separately governed caller with execute privilege.
  v_receipt := private.fn_lf_programming_context_handoff_receipt_resolve_v2(p_binding);
  IF (v_receipt->>'admissible')::boolean IS DISTINCT FROM true
     OR (v_receipt->>'hashes_verified')::boolean IS DISTINCT FROM true THEN
    RETURN jsonb_build_object('verified',false,'reason','PG01_C4_UPSTREAM_NOT_ADMITTED',
      'upstream_reason',coalesce(v_receipt->>'reason','UNKNOWN'));
  END IF;
  v_record := v_receipt->'record';
  IF jsonb_typeof(v_record) IS DISTINCT FROM 'object'
     OR v_record->>'context_id' IS DISTINCT FROM p_binding->>'context_id'
     OR v_record->>'context_sha256' IS DISTINCT FROM p_binding->>'context_sha256' THEN
    RETURN jsonb_build_object('verified',false,'reason','PG01_C4_CONTEXT_MISMATCH');
  END IF;
  -- Deliberate hard block: no authoritative L3 manifest, D15 architecture
  -- currentness or D17 budget/optimization readback is wired to PG-01 yet.
  -- Never infer those from unverified caller JSON or the PG-00 candidate map.
  RETURN jsonb_build_object('verified',false,
    'reason','PG01_C4_FRAMEWORK_PROVENANCE_NOT_IMPLEMENTED',
    'context_id',v_record->>'context_id');
EXCEPTION WHEN OTHERS THEN
  RETURN jsonb_build_object('verified',false,'reason','PG01_C4_READBACK_UNDETERMINED');
END $fn$;
-- No grants, no SECURITY DEFINER, no deployment in this candidate file.
