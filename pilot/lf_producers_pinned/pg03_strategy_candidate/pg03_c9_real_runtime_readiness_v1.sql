-- PG-03_C9: actual Supabase readiness probe for the EXISTING assurance route.
-- READ ONLY: no function invocation, no reservation, no status transition.
-- Never treat a green source-only CI as a provider-bound subject receipt.
WITH
checkpoints AS (
  SELECT c.checkpoint_code,c.status,c.assertion_receipt_sha256,c.evidence_ref
  FROM programacion.engineering_work_checkpoints c
  JOIN programacion.engineering_plan_units u ON u.work_item_id=c.work_item_id
  WHERE u.plan_code='PROGRAMMING_AGENT_PROGRAMMING_REMEDIATION_V1'
    AND ((u.unit_code='PG-01' AND c.checkpoint_code='PG-01_C6')
      OR (u.unit_code='PG-03' AND c.checkpoint_code IN ('PG-03_C2','PG-03_C3','PG-03_C9')))
),
source AS (
  SELECT count(*)::int AS verified_subjects
  FROM private.lf_evidence_ledger_v1 l
  WHERE l.subject_type='PG03_TECHNICAL_STRATEGY'
    AND l.capability_code='EVIDENCE_LEDGER'
    AND l.receipt_kind='SOURCE_SNAPSHOT'
    AND l.verification_state='VERIFIED'
    AND l.receipt_sha256 ~ '^[0-9a-f]{64}$'
    AND l.subject_sha256 ~ '^[0-9a-f]{64}$'
    AND l.source_head_sha ~ '^[0-9a-f]{40}$'
    AND l.resolver_id IN ('LF_GITHUB_SOURCE_READBACK_V1','LF_SUPABASE_READBACK_V1')
),
current_assurance AS (
  SELECT count(*)::int AS n,
         bool_and(v.release_state='RELEASED'
                  AND v.manifest#>>'{contract,subject_contract,mode}'='CONTRACT_DRIVEN_ANY_SUBJECT'
                  AND v.manifest#>>'{contract,subject_contract,subject_type_whitelist}'='false') AS contract_ok
  FROM public.lf_capability_current c
  JOIN public.lf_capability_version_registry v
    ON v.capability_code=c.capability_code AND v.version=c.version
  JOIN public.lf_capability_registry r ON r.capability_code=c.capability_code
  WHERE c.capability_code='INDEPENDENT_ASSURANCE' AND r.status='ACTIVE'
),
review_operation AS (
  SELECT count(*)::int AS n FROM public.lf_operation_registry
  WHERE operation_code='REVISION_INDEPENDIENTE_ESTRATEGIA_LF'
    AND lifecycle_state_code='OP_OPERATIONAL'
),
review_runs AS (
  SELECT count(*)::int AS n FROM public.lf_operation_execution
  WHERE operation_code='REVISION_INDEPENDIENTE_ESTRATEGIA_LF'
    AND target_type='PG03_TECHNICAL_STRATEGY'
),
resolver AS (
  SELECT count(*)::int AS n FROM private.lf_evidence_resolver_registry_v1
  WHERE active AND trust_level='TRUSTED_PROVIDER_BOUND'
    AND ((resolver_id='LF_GITHUB_SOURCE_READBACK_V1'
          AND provider='GITHUB' AND verification_method='GITHUB_API_READBACK_PLUS_OFFLINE_HASH')
      OR (resolver_id='LF_SUPABASE_READBACK_V1'
          AND provider='SUPABASE' AND verification_method='SUPABASE_SQL_READBACK_PLUS_DB_DIGEST'))
),
bindings AS (
  SELECT count(*)::int AS n FROM programacion.programming_checkpoint_bindings
  WHERE checkpoint_code IN ('PG-03_C3','PG-03_C9') AND enabled
)
SELECT
  'PG03_C9_REAL_RUNTIME_CONNECTIVITY_V1' AS probe,
  (SELECT status FROM checkpoints WHERE checkpoint_code='PG-01_C6') AS pg01_c6_status,
  (SELECT status FROM checkpoints WHERE checkpoint_code='PG-03_C2') AS pg03_c2_status,
  (SELECT status FROM checkpoints WHERE checkpoint_code='PG-03_C3') AS pg03_c3_status,
  (SELECT status FROM checkpoints WHERE checkpoint_code='PG-03_C9') AS pg03_c9_status,
  source.verified_subjects,
  current_assurance.n AS assurance_current_count,
  coalesce(current_assurance.contract_ok,false) AS generic_contract_current,
  review_operation.n AS operational_review_count,
  review_runs.n AS actual_pg03_review_runs,
  resolver.n AS trusted_resolver_count,
  bindings.n AS enabled_pg03_c3_c9_bindings,
  CASE
    WHEN (SELECT status FROM checkpoints WHERE checkpoint_code='PG-01_C6') IS DISTINCT FROM 'DONE'
      THEN 'BLOCK_PG01_C6_NO_GOVERNED_REAL_HANDOFF'
    WHEN (SELECT status FROM checkpoints WHERE checkpoint_code='PG-03_C2') IS DISTINCT FROM 'DONE'
      THEN 'BLOCK_PG03_C2_REAL_RULES_SKILLS_AUTHORITY'
    WHEN (SELECT status FROM checkpoints WHERE checkpoint_code='PG-03_C3') IS DISTINCT FROM 'DONE'
      THEN 'BLOCK_PG03_C3_REAL_STRATEGY_NOT_APPROVED'
    WHEN source.verified_subjects<>1
      THEN 'BLOCK_PG03_C9_EXACT_VERIFIED_SOURCE_SUBJECT_MISSING_OR_AMBIGUOUS'
    WHEN current_assurance.n<>1 OR NOT coalesce(current_assurance.contract_ok,false)
      THEN 'BLOCK_GENERIC_ASSURANCE_NOT_CURRENT'
    WHEN review_operation.n<>1 OR resolver.n<>2
      THEN 'BLOCK_GOVERNED_OPERATION_OR_RESOLVER_NOT_CURRENT'
    WHEN bindings.n<>2
      THEN 'BLOCK_PG03_C3_C9_CHECKPOINT_BINDINGS_NOT_ACTIVE'
    ELSE 'SOURCE_READINESS_PRECHECK_ONLY_NOT_EXECUTION_AUTHORIZATION'
  END AS first_blocker,
  false AS runtime_authorized_by_this_probe
FROM source
CROSS JOIN current_assurance
CROSS JOIN review_operation
CROSS JOIN review_runs
CROSS JOIN resolver
CROSS JOIN bindings;
