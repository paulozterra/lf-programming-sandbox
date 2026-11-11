> **Nota de arquitectura 2026-11-04:** A1 es un paso **interno** de la única skill `PROGRAMMING_ANALYSIS_LF`. Este artefacto procede del antiguo candidato individual; sus referencias a ejecución/registro deben interpretarse a nivel de la **skill completa**. No documenta una habilidad A1 registrable ni recibos operativos.

# A1 — Homologación de registro de pasos y transporte autorizado

Fecha de consulta: 2026-11-04. Tipo: decisión de integración `SOURCE_ONLY`; **no es un registro de RUN ni un cambio de ACL**.

## 1. Distinción obligatoria de identidades

- Unidad histórica `PROGRAMMING_AGENT_ANALYSIS_REMEDIATION_V1/A1`: `DONE`, con evidencia de PR/merge previa; **no reabrir ni reescribir**.
- Calificación histórica `A1Q`: 3 checkpoints C1/C2/C3 `DONE`; no usarlos como evidencia de una ejecución nueva de skill.
- Habilidad nueva `PROGRAMMING_ANALYSIS_LF`: código en PR #3529, `DRAFT`; **0 activos vigentes** en `public.lf_activos` y **0 ejecución A1** en `EJECUCION_SKILL_LF`. Dos asuntos distintos: dar de alta el activo y registrar la ejecución del skill.

## 2. Patrones ya existentes (readback Supabase + GitHub)

| Consumidor | Inicio/ejecución | Registrador | Transporte y permiso |
|---|---|---|---|
| Input Governance | `programacion.fn_input_governance_direct_step_v1` / Curador → Validador | Su ledger interno; NO `lf_operation_execution_steps` genérico | `public.fn_input_governance_queue_submit_oidc_v1`, `SECURITY DEFINER`, expuesto a principal autorizado; no ejecutable por `supabase_read_only_user` |
| Profile Updater | `lf_profile_update_begin_v1` | `lf_record_profile_operation_step_v1` | Issue/Workflow GitHub OIDC → Edge `run-creacion-perfil-lf` → `service_role` en servidor → RPC; conector RO no autorizado |
| Profile Creator | Operación `CREACION_PERFIL_LF` | `lf_record_creacion_perfil_step_v1` | El mismo patrón de Edge/identidad autorizada; `EXECUTE` concedido a RO no significa `INSERT` concedido |
| Skill Creator | `CREACION_SKILL_LF` | `lf_record_creacion_skill_step_v1` → fábrica → núcleo común | Registra pasos de creación, **no** ejecuta skill ni crea la fila del activo por sí mismo |
| Skill Execution A1 (objetivo) | `EJECUCION_SKILL_LF` 0–80 | **No hay wrapper específico identificado**; núcleo `lf_record_operation_step_core_v1` disponible | Reutilizar patrón de transporte solo tras cualificar caller, operación, confianza server-side y registro de A1 |

`public.lf_skill_invoke_v1` también existe, pero está ligado a una ejecución padre de `EJECUCION_PERFIL_LF`, a `lf_skill_catalog_v1` y a su ledger `lf_skill_invocation_v1`. El catálogo no contiene A1, su ledger tiene 0 invocaciones y **no equivale** al registrador de nueve pasos de `EJECUCION_SKILL_LF`.

## 3. Contrato homologado: entrada → proceso → salida

- **Entrada**: `execution_id` NUEVO, operación/activo/código, `step_id`, `evidence_ref`, `evidence_payload`, `actor_execution_id` y hashes/recibos reales. `input_required` y `required_evidence_keys` se obtienen de contrato canónico vigente, no se reinterpretan desde el lenguaje del usuario.
- **Proceso**: el consumidor de A1 no hace escrituras ni transporta credenciales. Un **único ejecutor autorizado y atado al contexto** comprueba ticket/identidad/RUN/operación/etapa, ejecuta el RPC específico y persiste el estado resultante tras el juez servidor.
- **Salida**: `STEP_RECORDED`, `BLOCKED` o `RETURN_TO_WORKER` + evidencia persistida; lectura posterior de `public.lf_operation_execution_steps` para el MISMO `execution_id`. La salida de Python `VALID_OUTPUT` no es un recibo operativo.
- No usar `lf_record_creacion_skill_step_v1` para `EJECUCION_SKILL_LF`, no llamar núcleo directamente pasando `p_trust_validation` autodeclarado, no modificar grants de RO.

### Flujo

`ACT-0001 (solo encamina) → Perfil seleccionado → EJECUCION_SKILL_LF (operación existente) → input_validate → execute_skill → output_validate → semantic_judge → report_output → readback → Perfil consumidor`

La autorización de la llamada al modelo y la identidad del juez pertenecen al **consumidor gobernado**, no a Router ni a A1.

## 4. Qué significa resolver el error 42501

Un `42501` al invocar desde el rol de lectura es un error de **canal/identidad**, no prueba de que la operación sea globalmente imposible. La recuperación que ya existe para perfiles usa `LF_PROFILE_NATIVE_BEGIN_REQUEST_V1` → GitHub Issue/label → Workflow OIDC → Edge → `service_role` interno. Input Governance utiliza wrappers `SECURITY DEFINER` y un principal explícitamente autorizado.

Para A1: reutilizar **ese patrón** pero **no invocar directamente el workflow exclusivo de PERFILES o la cola de IG**, ya que ninguna de esas rutas está autorizada para destino `SKILL`. La extensión mínima debe hacerse por el propietario del consumidor existente, sin Router→Skill directo ni servicio paralelo.

`DB_WRITE_TRANSPORT` / Merge Train corresponde a cambios de fuente de DB/migraciones, **no** al RPC operacional ordinario de cada step.

## 5. Gates pendientes (no inferir PASS)

1. Registrar A1 como SKILL y verificar fuente exacta; `EJECUCION_SKILL_LF` está `SANDBOX_ACTIVE / OP_CANDIDATE`, no liberada.
2. Cualificar principal/workflow OIDC y Edge consumidor de `SKILL` con límites de destino/operación; no reusar sin autorización caller de `PERFIL`.
3. Cualificar wrapper de operación **con confianza derivada por servidor**, reutilizando `lf_record_operation_step_core_v1`. Sin crear otro motor.
4. Ejecutar positivo y negativos de: rol RO denegado, ticket incorrecto, `execution_id` de otro run, `step_id` no permitido, hash divergente, juez semántico `FAIL`, evidencia falsa.
5. Registrar y leer recibos del mismo RUN; solo entonces calificar `SKILL_INTEGRATED`.

**Estado:** homologación de contrato y política terminada en candidato GitHub; transporte operacional, wrapper, permisos y registro real no modificados. Ver `adapters/governed_step_homology_v1.json`.

## 6. Lote siguiente: preflight del contrato de transporte, no ejecución

Se creó `adapters/governed_skill_step_preflight_v1.py` con 26 pruebas sintéticas en `evals/test_governed_skill_step_preflight_v1.py`. Esta pieza **solo verifica estructura del sobre A1, operación/destino, identidad de ejecución, claves de evidencia y coincidencia de forma contra una respuesta de readback proporcionada externamente**. No es otro runtime, registrador, juez semántico ni proveedor de autenticación. `PREFLIGHT_ONLY` y `READBACK_SHAPE_MATCH_ONLY` **no autorizan ni prueban una escritura**.

Se rehúsa `init_execution` como llamada normal al registrador (`REQUIRES_CANONICAL_BEGIN`); el núcleo genérico lo prohíbe. `semantic_judge` queda `REQUIRES_SERVER_SIDE_INDEPENDENT_JUDGE` aunque alguien declare `PASS`. En Supabase el juez `JUDGE-EJECUCION-SKILL-LF-v0.1` sigue con `pass_if=[]` y `fail_if=[]`; **no hay enforcement semántico E2E acreditado**.

La prueba negativa con el consumidor/worker y la creación del RUN siguen pendientes. **No se ejecutaron las 26 pruebas Python nuevas en este lote**. La identidad OIDC nunca se acepta desde el JSON enviado por el solicitante.
