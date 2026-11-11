# A2 Golden — Lote 15 | Preparación del caller/invocador READ_ONLY

**Estado:** `SOURCE_ONLY_CANDIDATE`; sin activación, migración SQL, cambio de permisos ni RUN real. PR #3624. El objetivo es **conectar mediante el invocador y el reservador existentes**, no crear otro Router/engine.

## Hallazgos verificados (Supabase y Main, 2026-11-06)

1. `ACT-0001 / SKILL_EXECUTION` resuelve a `EJECUCION_SKILL_LF` con `write_allowed=false`. La operación tiene **9 pasos**: 0,10,...,80 y está `SANDBOX_ACTIVE / OP_CANDIDATE`.
2. `lf_skill_invoke_v1` tiene una rama SQL `READ_ONLY` que invoca el handler y guarda `COMPLETED` **sin** `child_execution_id`; solo crea RUN hijo cuando `effect=WRITE_GOVERNED`. No usar `COMPLETED` como dictamen de A2.
3. `lf_skill_catalog_v1` exige `handler_fn`, permite `child_caller` (método/repositorio/workflow), `effect` = READ_ONLY/PROPOSE_ONLY/WRITE_GOVERNED. Falta una entrada READY para `PROGRAMMING_ANALYSIS_LF` y no existe autorización activa en `lf_profile_write_authority_v1` para `EJECUCION_SKILL_LF`.
4. `fn_lf_operation_reserve_execution_v1` (readback MD5 `311a0377c43c0698ec12826c1a7f6a78`) valida idempotencia, request hash y target; **no autentica Router/caller y no coteja el manifiesto en replay**. Solo `service_role` tiene permiso EXECUTE; el rol de lectura no. Lo debe invocar el host autorizado después de validar identidad y negocio.
5. El paso `init_execution` (0) exige `execution_id_created` y utiliza `JUDGE-EJECUCION-SKILL-LF-v0.1`, valor limpio `STEP_PASS_WITH_EVIDENCE`. **Reservar fila sin registrar paso 0 no completa apertura gobernada**.
6. El Edge `profile_continuation.ts::invokeSkill` elimina `_trusted` del usuario y usa `e.execution_id` del RUN autenticado: base reutilizable. No obstante, su respuesta actual es `SKILL_INVOKED` aun cuando un RPC devuelva un `status=BLOCKED` en JSON; **se requiere normalizar resultados antes de exponer éxito o continuar**.
7. `PROGRAMMING_ANALYSIS_LF` mantiene `CANDIDATE_READ_ONLY`/binding false, con 0 invocaciones y 0 RUN. Ninguno de los RUN históricos `ACT-0057`/`ACT-0046` demuestra ejecución de esta skill.

## Contrato técnico — propuesta, no despliegue

```text
Perfil (RUN autorizado; negocio exacto)
  → profile_native_skill_invoke_v1 (Edge existente)
     → autenticación OIDC + readback servidor del RUN/Router/skill/fuente Main
     → autorización perfil → operación SKILL_EXECUTION + catálogo READY
     → lf_skill_invoke_v1 (rama opt-in READ_ONLY, no ejecutar handler SQL prematuramente)
       → reserva por fn_lf_operation_reserve_execution_v1
       → vincula skill_run_id y child_execution_id por identidad/idempotencia exactas
       → registra init_execution (0) usando registrador gobernado y recibo
       → SELECT/readback del RUN, paso 0 y manifiesto completo
       → devuelve CONTINUATION_REQUIRED, **nunca COMPLETED**
  → ejecutor nativo de la skill, mismo RUN:
        A1 → A2 → juez existente → A3 (únicamente con PASS/readback)
  → validación 60, juez operación 70, reporte 80
  → respuesta final al perfil, con evidencia terminal
```

**Sin new Router, sin nuevos grants al modelo, sin convertir la skill a WRITE_GOVERNED**. Las escrituras de RUN/pasos son auditoría del host autorizado, no efectos de negocio de A2.

### Invariantes de la adaptación del invocador/caller

- **R01 Opt-in explícito:** aplicar solamente a READ_ONLY + `required_operation=EJECUCION_SKILL_LF` con `child_caller` y catálogo READY, no alterar handlers existentes de READ_ONLY simples.
- **R02 Identidad:** negocio de `manifest.business`, Router handoff y recibo, perfil y request_sha256 exactos; nunca inferir LF a partir de la pantalla. Faltar la raíz bloquea.
- **R03 Autoridad:** invocador mantiene validación de `lf_profile_write_authority_v1` y host comprueba caller OIDC; no insertar autorización para pruebas.
- **R04 Fuente:** SHA de Main y blob exactos obtenidos por host, no del payload libre; ante drift bloquea.
- **R05 Idempotencia:** derivar la clave del RUN padre + código de skill + digest de input, no de un `v_run` aleatorio. Repetición exacta → mismo RUN; variación de input → distinta clave.
- **R06 Replay:** `fn_lf_operation_reserve_execution_v1` no compara manifiesto. Después de cualquier reserva, exigir readback de negocio, identidad de origen, sha/commit de fuente, `skill_run_id`, entrada y binding. Si varía, `RESERVATION_MANIFEST_DRIFT`; no nuevo dispatch.
- **R07 Paso 0:** guardar `init_execution` por función/transportador gobernado; comprobar `step_order=0`, juez, evidencia, RUN y estado correcto.
- **R08 Estados:** no insertar una invocación `COMPLETED` sin los pasos y juez. El estado intermedio del ledger invocador requiere homologación con catálogo antes de aplicarlo; **no inventar un estado DB activo**.
- **R09 Edge:** `outcome=SKILL_INVOKED` no significa completar un trabajo; normalizar estados SQL: BLOCKED/FAILED vs CONTINUATION_REQUIRED vs COMPLETED.
- **R10 Juez:** A2 máximo 3 entregas; recibo del juez nativo es condición anterior al handoff A3; el paso externo 70 no convalida retrospectivamente una A3 prematura.
- **R11 Compatibilidad:** preservar el comportamiento SQL de `SCREEN_RULES_SNAPSHOT`, `RULE_UPDATE_PROPOSE` y de skills WRITE_GOVERNED; crear pruebas de regresión en el mismo PR de fuente oficial correspondiente.
- **R12 Cierre:** agotamiento A2 → informar al perfil; cierre de ticket únicamente mediante fuente y recibo canónico.

### Código candidato de preflight/readback

- `adapters/native_readonly_run_plan_v1.py`: genera una **propuesta no ejecutable** de reserva determinística y coteja reserva/child/step0 con la identidad del negocio. Acepta `operation_policy_snapshots` añadidos por gobernanza, no campos arbitrarios.
- `steps/a2/evals/test_native_readonly_run_plan_v1.py`: **39/39 pruebas sintéticas PASS** en `python -m unittest discover`. Código y pruebas cotejados por Git blob con repositorio.
- El módulo **siempre** retorna `host_attested=false`, `reservation_executed=false`, `step0_recorded=false`, `readback_authenticated=false`, `a3_allowed=false`. Un JSON perfecto no autentica un RUN ni habilita A3.

## Criterios de admisión pendientes

| P0 | Evidencia exigida |
|---|---|
| Opt-in invocador nativo READ_ONLY | Diff mínimo de SQL oficial revisado; no rama WRITE_GOVERNED |
| Caller autorizado y readback | Contrato Edge/ODIC, perfil/skill/fuente de Main, idem y negocio |
| Operación 0–80 | RUN nuevo de `PROGRAMMING_ANALYSIS_LF` + paso 0 grabado/recuperado |
| Estado invocación | No `COMPLETED` antes de juicio/steps ni falso `SKILL_INVOKED` |
| Juez real | Recibo independiente A2 y paso 70 vinculados al mismo RUN |
| Regresión | Pruebas negativas y PASE sin ampliar allowlist de workflows |
| Gobernanza | Autorización de perfil y admisión del activo sólo en proceso canónico |

**No modificar SQL/Edge oficial ni aplicar migración por este documento.** Los cambios reales requieren revisión de impactos, fuente Main exacta, pruebas E2E, autoridad de escritura y readback del sistema gobernado; PASE de un PR solo de skills no los acredita.
