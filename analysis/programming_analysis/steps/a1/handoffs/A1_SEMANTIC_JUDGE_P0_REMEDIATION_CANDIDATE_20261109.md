# A1 — Juez semántico: brecha de enforcement y corrección mínima candidata

**Fuente consultada:** Supabase / `public.lf_operation_judges`, `public.lf_operation_step_judge_bindings`, `public.lf_operation_step_contracts` y `pg_get_functiondef(public.lf_record_operation_step_core_v1)`, 2026-11-09.
**Skill:** `PROGRAMMING_ANALYSIS_LF` (asset 414, CANDIDATO READ_ONLY, runtime_binding_enabled=false).
**Operación existente:** `EJECUCION_SKILL_LF` (9 pasos, SANDBOX_ACTIVE, 0 RUN de esta skill).
**Estado:** P0 confirmado como riesgo de enforcement en fuente; NO existe prueba de explotación ni autorización runtime. No cambia política oficial, Router, privilegios, PASE, producción ni A3.

## Hallazgo verificable

- El paso `semantic_judge` está vinculado a `JUDGE-EJECUCION-SKILL-LF-v0.1`, status `ACTIVE_ENFORCEMENT`. Exige campos `semantic_judge_result` y `unsupported_claims`, pero la política contiene `pass_if=[]`, `fail_if=[]`.
- El núcleo existente (`public.lf_record_operation_step_core_v1`, pg_get_functiondef MD5 `fe08a25c8e3c023d7181194d2dfdee0d`, 21411 caracteres) itera `pass_if` y `fail_if`; si falta cero elementos positivos y ningún fallo anterior fue detectado, deriva el valor `clean_result_value`.
- **Riesgo condicionado:** un wrapper autorizado que suministrara `p_trust_validation.valid=true` con `server_assertions=[]`, `server_hard_fails=[]` y campos estructurales completos no probaría independencia del juez por las listas actuales. Ello no equivale a una ejecución real verificada; el núcleo requiere otras condiciones de trust, orden, contrato y binding.
- No se debe inferir `semantic_judge PASS` por `ACTIVE_ENFORCEMENT` ni por PASE verde.
- Ver recibo: `steps/a1/evals/results/a1_judge_policy_enforcement_p0_readback_20261109.json`; guard candidato `steps/a1/adapters/judge_policy_gap_readback_v1.py` y 14 regresiones Python negativas PASS contra los Git blobs exactos.

## Corrección mínima propuesta — conservar la arquitectura existente

```text
Router ACT-0001 (autoridad una sola vez)
    ↓
Perfil consumidor autorizado
    ↓
EJECUCION_SKILL_LF · mismo RUN, mismos 9 pasos
    ↓
Ejecutor con OIDC/autoridad server-side verificada
    ├─ Productor semántico: invocación real + recibo host
    └─ Juez semántico INDEPENDIENTE: invocación distinta,
       mismo candidato/hash y negaciones, verdict, unsupported_claims
    ↓
Juez de paso especializado [PROPUESTA]:
    pass_if POSITIVO / fail_if NEGATIVO no vacíos,
    servidor deriva assertions/hard_fails; cliente no los impone
    ↓
Registrador restringido de EJECUCION_SKILL_LF → core común
    ↓
Persistencia + readback mismo execution_id/commit/source/judge receipt
    ↓
Perfil evalúa continuación A2 → A3 (aún bloqueado)
```

Reutilizar el **binding por paso** existente para `semantic_judge`; una política dedicada a ese paso evitaría modificar el juez v0.1 compartido por los nueve pasos. El wrapper autorizado debe construir y verificar `trust_validation` del lado servidor. No aceptar `valid` ni afirmaciones de independencia del payload del usuario.

**No recomendado:** editar `pass_if/fail_if` del juez compartido sin análisis transversal: afectaría los otros ocho pasos. **Prohibido:** invocar el core desde usuario read-only, usar `lf_record_creacion_skill_step_v1` para ejecución o reemplazar los nueve pasos por `lf_skill_invoke_v1`.

## Pruebas exigidas antes de modificar fuente oficial o habilitar runtime

1. Positivo: dos invocaciones reales separadas, recibos de proveedor y hashes idénticos al candidato revisado, fuente y autoridad CURRENT.
2. Negativo: juez `FAIL` provoca bloqueo persistido; nunca `STEP_PASS_WITH_EVIDENCE`.
3. Negativo: `unsupported_claims` no vacíos bloquean, aunque el productor autodeclare `PASS`.
4. Negativo: mismo identificador de invocación productor/juez o recibo inventado bloquea.
5. Negativo: revisión sobre hash distinto, evidencia stale o repo/negocio/ejecución diferente bloquea.
6. Negativo: falta `server_assertions` o `server_hard_fails`, trust autodeclarado, arrays vacíos o autoridad no verificada bloquea.
7. Negativo: falla de operación/binding/step, replay fuera del RUN y readback sin coincidencia rechazan.
8. Regresión: ejecución normal de los otros ocho pasos y cero bypass de Input Governance/Profile Updater/Skill Creator.
9. Verificación de 74 pruebas A1/A2 en un checkout EXACT HEAD mediante `evals/run_a1_a2_exact_head_candidate_v1.py` y sandbox de confianza externo. Un PASS local no reemplaza recibo nativo de juez.

## Autoridad y límites

La propuesta queda en **PR DRAFT**. Cambios de juez oficial, binding, RPC, servicio autorizado o activación runtime **requieren la aprobación y transporte gobernado que corresponda**. Mientras tanto, el guard source-only puede advertir del defecto, pero no sustituye la calificación server-side.

**Cierre:** `P0_JUDGE_INDEPENDENCE_ENFORCEMENT_NOT_QUALIFIED`; `a3_allowed=false`.
