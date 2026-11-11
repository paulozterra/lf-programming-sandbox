# L1 — A1→A2 | ejecución y readback parcial (2026-11-06)

## Alcance autorizado
Continuar el L1 de `PROGRAMMING_ANALYSIS_LF` dentro del PR DRAFT #3624. Reutilizar A1, A2, perfil y operación existentes. Sin nuevo Router, motor, catálogos Golden ni despliegue. **Este handoff registra un parche candidato y un bloqueo operativo; no certifica RUN.**

## EKB consultada directamente (Supabase, solo lectura)
- `PROGRAMMING-ANALYSIS-STAGE-SOURCE-ATTESTATION-GAP-001`: las 9 referencias Git no sustituyen los 9 readbacks CURRENT autenticados antes de modelo.
- `PROGRAMMING-ANALYSIS-A14-EVIDENCE-TIER-FALSE-READY-001`: fixture o PASE PASS no son juicio real ni lectura del consumidor PG-01.
- `PROFILE-JUDGE-INVARIANT-COVERAGE-001`: primero invariantes determinísticos; juez no revierte FAIL ni se contabiliza por número de predicados.

## Readback Supabase del lote
- `lf_activos.id=414`: `PROGRAMMING_ANALYSIS_LF`, `CANDIDATO / READ_ONLY / CANDIDATE_READ_ONLY`.
- `lf_operation_registry`: `EJECUCION_SKILL_LF` = `SANDBOX_ACTIVE / OP_CANDIDATE`.
- `lf_operation_execution`: **0** RUN `EJECUCION_SKILL_LF` de esta skill.
- `lf_skill_invocation_v1`: **0** invocaciones; `lf_skill_catalog_v1`: **0** catálogo; `lf_profile_write_authority_v1`: **0** autoridades para `EJECUCION_SKILL_LF`.
- **0** funciones SQL instaladas de la lista candidata `lf_skill_native_preflight_v1`, `lf_skill_execution_begin_from_handoff_v1`, `lf_record_skill_execution_step_v1`, `lf_skill_execution_status_v1`.
- El conector actual a Supabase es de **solo lectura**. No invocar una reserva ni insertar autoridades/receipts desde ese rol.

## Reparación concreta del flujo candidato
Detectada discrepancia real: `steps/a2/adapters/a2_a3_intake_preview_v1.py` exigía `A1_SOURCE_CANDIDATE_V1` (fixture histórico); el validador A1 actual produce `A1_INTERNAL_STEP_CANDIDATE_RESULT_V1`. La prueba de preview no pasaba por los ejecutores reales A1 y A2, por lo que un PASS sintético podía ocultar la incompatibilidad.

Corregido en rama DRAFT:
1. `steps/a2/adapters/a2_a3_intake_preview_v1.py`: exige el identificador del ejecutor A1 real, manteniendo `a3_allowed=false`, `source_authenticated=false` y `judge_verified=false`.
2. `steps/a2/evals/test_a2_a3_intake_preview_v1.py`: fixture nuevo llama `RUN_A1.run(a1input())` y `RUN_A2.run(a,low())`; comprueba A1→A2→Golden→preview y rechaza el identificador obsoleto.

Commits: `874d4b8f631ba034eb204cad6dd88359295786bd`, `fc0bf53cccf5d8f51bc76afec6242d354af213d3`.
Readback: blobs `0a849184d0ef6bb5c373dbb4893f197054b66516` y `400d54a5bcef0e0ca1f5d23fcf1c21a0ccd1aa6f`.
PASE del commit `fc0bf53`: SUCCESS, run `42323897569`. **No demuestra que los tests Python se ejecutaran**.

## Límites y siguiente bloque operativo
- **A1/A2 código candidato: continuidad real de fixture conectada; pruebas Python exact-HEAD PENDIENTES.**
- **A1/A2 operación: BLOQUEADA**. Sin catálogo READY, autoridad ACTIVE, fuente CURRENT atestada, productor semántico real, RUN/0..80 y recibo del juez independiente. A3 no habilitado.
- PR #3681 existe solo como caller Edge **candidato sandbox y no desplegado**; no asumir que sus RPC propuestas están instaladas ni abrir una ruta paralela.
- Siguiente trabajo legítimo: ejecutar Python A1/A2/Golden/preview sobre HEAD exacto; adaptar la ruta nativa `EJECUCION_SKILL_LF` por gobierno aprobado, admitir la skill solo tras calificación y ejecutar readback RUN + juez. No merger ni activar por este handoff.

## Estado de cierre
`PATCH_CANDIDATE_COMMITTED`; `PASE_SUCCESS_PRE_HANDOFF`; `PYTHON_TESTS_NOT_VERIFIED`; `GOVERNED_RUN_COUNT=0`; `OPERATIONAL_A1_A2=BLOCKED`. Supabase, EKB, Main, Router, producción y PR #3681 sin modificaciones.
