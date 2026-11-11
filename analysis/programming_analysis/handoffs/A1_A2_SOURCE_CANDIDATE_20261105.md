# Agente de Programación — Lote A1→A2 · Integración interna candidata

**Estado:** SOURCE_CANDIDATE / NOT_MERGED / NOT_RUNTIME_QUALIFIED.
**Skill única:** `PROGRAMMING_ANALYSIS_LF` (activo ID 414; CANDIDATO/READ_ONLY).
**Operación canónica de cambio de fuente:** `ACTUALIZACION_SKILL_LF` — `PRODUCCION_CONTROLADA`.
**Operación futura de ejecución:** `EJECUCION_SKILL_LF` — `SANDBOX_ACTIVE`.

## Alcance conservado
- A1 conserva código/contratos; no se permite desplazar semántica pendiente al paso A2.
- A2 es un **módulo interno**, no un nuevo perfil/skill ni motor paralelo.
- Usa los **23 predicados** existentes de la política canónica `analysis_change_classification_contract_v1.json`, evaluados desde el propio JSON (L3 primero, L2 después, L1 solo con todos sus requisitos).
- `steps/a2/validators/run.py` recibe el sobre validado de A1 más señales tipadas externas y produce únicamente `ANALYSIS_CHANGE_CLASSIFICATION_V1` como candidato no atestado.
- `adapters/a1_a2_candidate_bridge_v1.py` verifica continuidad local sin ejecutar el perfil, modelo, juez o A3.
- Entrada/salida tipadas: `steps/a2/schemas/input.schema.json` y `output.schema.json`.
- `steps/a2/evals/test_a2.py`: 28 pruebas sintéticas **definidas, todavía NO ejecutadas con intérprete Python sobre el HEAD vigente** (25 preexistentes + 3 negativos de esquema de salida).
- Control de reglas analizadas desde Git: 23/23 expresiones reconocidas; escenarios de L1, L2, L3, riesgo alto, especialista pendiente y evidencia desconocida comprobados con una evaluación estática independiente en JavaScript. **No sustituye tests Python.**

## Controles de riesgo
1. A1 `REQUIRES_SEMANTIC_REVIEW` → A2 `BLOCKED`. No aceptar un juez declarado dentro del payload.
2. A1 estructurado válido → A2 puede proyectar profundidad local, pero `source_attested=false`, `independent_judge_verified=false`, `next_step=null`.
3. Sin señales tipadas, target en A1, padre de target anidado o evidencia declarada, A2 bloquea. Fuente declarada no equivale a fuente CURRENT.
4. `required_specialist_count>0` no selecciona ni inventa especialistas; `CAPABILITY_SELECTOR` queda como dependencia real futura.
5. No declarar A3 habilitado, READY, freeze, producción, escritura o E2E de perfil.

## Precondiciones de integración gobernada
- Router ACT-0001 consultado para UPDATE de SKILL; devolvió `BLOCK_EXPLICIT_TARGET_INTENT_ATTESTATION_REQUIRED` y `ROUTER_ACTION_BINDING_REGISTRY_MISSING`; no es permiso de escritura.
- La operación `ACTUALIZACION_SKILL_LF` exige **14 pasos**: init_execution, router, skill_resolve, baseline_read, change_scope, regression_plan, pre_write_execution_binding_gate, github_write, github_readback, deterministic_validation, semantic_judge, regression_after, close, report_output. **No hay recibos de esos pasos para este lote.** Se escribió solo fuente candidata en branch. No presentarlo como actualización oficial.
- Requiere ejecución autorizada vinculada ANTES del merge; no sustituir con `CREACION_SKILL_LF`.
- El activo `lf_activos` mantiene source blob `9abb2ce0513bcb3241dec459420c394e2c93a03c` y manifest blob `b778f5ce1c510cd91d13cf0584080837e2fc84ea`. **Si se integran cambios a SKILL.md/manifiesto, actualizar fuente canónica por ruta gobernada y verificar readback exacto; no dejar drift.**
- Pruebas Python A1, A2, paquete + semánticas independientes, negativos, holdout fresco y comparación BEFORE/AFTER pendientes de evidencia.
- PR candidato **no debe etiquetarse `ready-to-merge`** ni alterar catalogación del activo hasta completar las precondiciones.

## Próximo cursor
Resolver admisión tipada de ACT-0001/ACTUALIZACION_SKILL_LF para el activo registrado, abrir ejecución antes del write definitivo, reproducir el patch gobernado y correr tests reales. Luego ejecutar juez independiente, comparar BEFORE/AFTER y actualizar hash de activo por la autoridad de DB antes de habilitar consumidor.

## Lote correctivo P1 — 2026-11-05 (fuente candidata, sin calificación)
- Hallazgo: validación de esquema de salida situada después de `return` y por tanto inalcanzable en `steps/a2/validators/run.py`.
- Corrección candidata: antes de exponer clasificación L1/L2/L3, validar todo el `result` contra `output.schema.json`; ante resultado inválido, devolver `BLOCKED/A2_CANDIDATE_OUTPUT_SCHEMA_DRIFT`. El propio sobre `BLOCKED` se valida y, si no satisface el esquema, se produce error terminal `A2_BLOCKED_OUTPUT_SCHEMA_DRIFT` (fail closed).
- Evidencia de fuente: runner blob `243e1e6ccdd494caa5a60407e07c4f5c10a39a60`; test blob `7f43f21d9f6017903802a307cf30a1a49efbaad2`.
- Nuevas pruebas: emisión con predicados vacíos, nivel fuera del enum (`L4`) y sobre `BLOCKED` malformado (debe elevar error). Conteo definido **28 tests**; no afirmar que están ejecutados o PASS.
- CI: PASE exitoso al HEAD correctivo previo `4ee0876a433c245a57e420acb750846c55c52505`, run `42150656025`. Este control NO acredita ejecución Python ni consumidor real.
- Cambios acotados a fuente de candidata, tests y este handoff. PR #3624 permanece `DRAFT`; **no** merge, no alta de otro activo, no escritura Supabase, no activation, no bypass de ACTUALIZACION_SKILL_LF.
- Pendientes de cierre P1: ejecutar tests Python exact-HEAD, comprobar errores negativos y regresiones A1/A2, juez independiente y admisión/recibos de actualización gobernada.
