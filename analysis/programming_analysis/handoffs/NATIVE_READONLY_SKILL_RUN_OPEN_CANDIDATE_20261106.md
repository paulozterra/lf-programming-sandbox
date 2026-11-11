# A2 Golden — Apertura nativa del RUN de skill READ_ONLY (candidato, preadmisión)

**Estado:** INVESTIGATED / NOT_OPERATIONALLY_WIRED. **No ejecutar ni admitir por esta fuente**. Objetivo: reutilizar el Router `ACT-0001`, la operación `EJECUCION_SKILL_LF` y su reservador nativo sin crear otro motor, sin cambiar permisos del modelo y sin ZIP.

## Evidencia consultada (Supabase, 2026-11-06)

| Fuente actual | Readback | Alcance |
|---|---|---|
| `lf_router_action_registry` SKILL / SKILL_EXECUTION | ACTIVE, `write_allowed=false`, `operation_code=EJECUCION_SKILL_LF` | Deriva a la operación existente; no autoriza un writer arbitrario |
| `lf_operation_registry` | `EJECUCION_SKILL_LF` SANDBOX_ACTIVE / OP_CANDIDATE | No producción |
| `lf_operation_step_contracts` | 0 init; 10 Router; 20 resolve; 30 source; 40 input; 50 execute; 60 output; 70 judge; 80 report. `execution_sql=null`; `resolver_ref=GPT_RUNTIME_WITH_SUPABASE_CONTEXT` | No RPC específico de apertura identificada en el contrato |
| `public.fn_lf_operation_reserve_execution_v1` | 10 argumentos; MD5 de cuerpo `311a0377c43c0698ec12826c1a7f6a78` | Reserva genérica con idempotencia; **NO valida autorización del negocio / Router por sí misma** |
| Permisos del reservador | `supabase_read_only_user: EXECUTE=false`, `service_role: EXECUTE=true` | Solo llamar por host autorizado con control previo |
| `public.lf_skill_invoke_v1` | MD5 `289ef129239ba1a4cbb33314f4484f4b` | En `READ_ONLY` registra `lf_skill_invocation_v1`, **sin** RUN hijo. Crear RUN hijo solo en rama `WRITE_GOVERNED` |
| `lf_skill_catalog_v1` | 1 skill READY READ_ONLY (`SCREEN_RULES_SNAPSHOT`), sin `opener_fn`; ningún `PROGRAMMING_ANALYSIS_LF` READY | No reutilizar una skill ajena ni convertir el análisis a WRITE_GOVERNED |
| `public.lf_activos` | `PROGRAMMING_ANALYSIS_LF` CANDIDATE_READ_ONLY, binding deshabilitado | No admisión |
| `lf_operation_execution` | 0 RUN para `PROGRAMMING_ANALYSIS_LF` | Sin evidencia E2E del objetivo |
| Históricos `EJECUCION_SKILL_LF` | RUN de `ACT-0057`/ `ACT-0046`. Los ACT-0057 recientes consultados no tenían filas de los pasos 0–80 | **No** reutilizar como prueba de 9 pasos ni de A2 |

El caller `public.lf_pre_ekb_child_dispatch_v1` reutiliza legítimamente el reservador, **pero está limitado a escritura EKB y target ACT-0057**: prohibido reutilizarlo para A2. El reservador genérico no permite por sí solo saltarse la verificación de identidad/autoridad.

## Contrato de enlace mínimo, no activado

```text
Perfil autorizado → invocación de PROGRAMMING_ANALYSIS_LF
     → Caller nativo autorizado valida actor/perfil + Router SKILL_EXECUTION
     → verifica negocio del RUN padre, handoff y recibo ACT-0001
     → verifica asset SKILL, fuente Main y runtime permitido
     → reserva RUN hijo por fn_lf_operation_reserve_execution_v1
     → init_execution (0) con evidencia REAL en el mismo RUN
     → SELECT/readback del RUN hijo + vínculo con invocación del perfil
     → A1 → A2 → juez existente (máximo 3 intentos)
           ├─ PASS/readback → A3
           └─ 3 FAIL → informe terminal al perfil
     → pasos gobernados 60 → 70 → 80, sin reordenar ni autoacreditar
```

**Diferencia esencial:** el efecto de negocio `READ_ONLY` impide escrituras de producto/código/reglas; **el host gobernado sí debe persistir RUN y pasos de auditoría** bajo identidad y permisos canónicos. Esto no otorga escritura al modelo.

### Reserva nativa: precondiciones del caller, no argumentos autodeclarados

El caller autorizado debe comprobar, con datos obtenidos directamente de Supabase:

1. RUN padre `EJECUCION_PERFIL_LF` activo, `execution_id` ligado al actor y perfil exacto.
2. `manifest.business` obligatorio y consistente con `router_profile_handoff.business` y `router_authorization_receipt.business`; `request_sha256` idéntico.
3. Resolución exacta del activo `PROGRAMMING_ANALYSIS_LF` en `lf_activos`, fuente Main vigente, y habilitación solo tras la admisión aprobada. No usar una skill cuyo binding sigue deshabilitado.
4. Router `SKILL_EXECUTION` activo para `SKILL`; recibo autorizado de ejecución (no un JSON producido por A2). Validación de identidad de caller (OIDC/capability admitida).
5. Invocación y nuevo RUN hijo enlazados en **una transición transaccional gobernada**: `skill_run_id`, `parent_execution_id`, `child_execution_id`, `profile_code`, `request_sha256`, `skill_code`, destino `EJECUCION_SKILL_LF`, `target_type=SKILL`, target exacto.
6. Idempotencia estable por solicitud y perfil; la función genérica debe recibir `p_execution_id`, `p_operation_code`, `p_target_type`, `p_target_code`, `p_idempotency_key`, `p_request_sha256`, `p_actor_execution_id`, `p_target_repo`, `p_target_path`, `p_manifest` validados del contexto **servidor**.
7. Registro del paso 0 con el contrato/juez existente; readback del mismo RUN después de reservar. Los pasos 50/60/70/80 deben tener evidencia real; un resultado SQL `COMPLETED` no es PASS del juez semántico.

**P0 arquitectura confirmado:** el invocador `lf_skill_invoke_v1` actual no produce RUN hijo en `READ_ONLY` y ningún `opener_fn` READ_ONLY está registrado. Integrar el enlace requiere una **adaptación mínima gobernada del invocador/caller existente**, no cambiar `effect` a `WRITE_GOVERNED`, no usar EKB dispatch ni crear otro Router. Esa adaptación se ha analizado, **no se implementó ni desplegó**: afecta la fuente SQL oficial y necesita validación independiente, autorización de cambio y pruebas con RPC.

## Reglas de aceptación previas a admisión

- `R01` Router solo reconoce la acción `SKILL_EXECUTION` y destino SKILL exacto; otro negocio/asset bloquea.
- `R02` Falta `business` en el RUN raíz o diferencia con recibo → BLOCKED; nunca autocompletar.
- `R03` Skill READ_ONLY con invocación pero `child_execution_id=NULL` → `RUN_GOVERNED_CHILD_ABSENT_READ_ONLY_INVOKER`; **no A3**.
- `R04` RUN de otra skill (p. ej. ACT-0057), otro actor, solicitud, perfil o source HEAD → BLOCKED.
- `R05` Reserva repetida con misma idempotencia/scope → replay sin duplicar; distinto scope → BLOCKED.
- `R06` Solo host autorizado puede ejecutar reserva y registrar paso 0; consumer/model no puede promover `readback_authenticated`.
- `R07` Gate A2→A3 exige el RUN exacto, el juez real y su recibo; evaluación del paso 70 *posterior* no sustituye revisión previa interna.
- `R08` 3 FAIL → no A3; devolver diagnóstico y cierre solo con ticket y recibo canónico.

## Evidencia de este lote

`adapters/run_business_binding_v1.py`: identifica explícitamente el caso SQL READ_ONLY sin RUN hijo, no lo confunde con un RUN gobernado. `steps/a2/evals/test_run_business_binding_v1.py`: 32 pruebas sintéticas de identidad y bloqueo.

**BLOQUEOS NO RESUELTOS:** caller OIDC específico admitido, enlace transaccional read-only sin crear WRITE_GOVERNED, registro del paso 0, fuente habilitada, revisión nativa de A2 y readback de juicio. **No entregar como integrado ni admitir.**
