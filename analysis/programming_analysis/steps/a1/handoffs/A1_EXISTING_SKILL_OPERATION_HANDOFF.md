> **ACTUALIZACIÓN DE READBACK 2026-11-09 — prevalece sobre el diagnóstico histórico de 2026-11-03/04:** `PROGRAMMING_ANALYSIS_LF` **sí está registrada** en `public.lf_activos` (exactamente una fila, ID 414). `estado_documental=CANDIDATO`, `estado_operativo=READ_ONLY`, `runtime_estado=CANDIDATE_READ_ONLY`, `metadata.runtime_binding_enabled=false`. El blob registrado `9abb2ce0513bcb3241dec459420c394e2c93a03c` coincide con GitHub **main**; no acredita que el nuevo HEAD de PR #3624 esté en main ni que la skill esté RELEASED. `EJECUCION_SKILL_LF` conserva 9 pasos/contratos/bindings, `SANDBOX_ACTIVE`, sin ejecución registrada para la skill y sin prueba negativa de juez independiente. **No volver a crear/registrar la skill ni cambiar permisos; ejecutar solo por autoridad gobernada después de calificar el binding.** La afirmación histórica «no registrada (0)» abajo no es CURRENT. Fuente: readback Supabase+GitHub 2026-11-09; `adapters/governed_step_homology_v1.json` y `adapters/existing_skill_operation_binding_v1.json` corregidos en PR candidata.

> **Nota de arquitectura 2026-11-04:** A1 es un paso **interno** de la única skill `PROGRAMMING_ANALYSIS_LF`. Este artefacto procede del antiguo candidato individual; sus referencias a ejecución/registro deben interpretarse a nivel de la **skill completa**. No documenta una habilidad A1 registrable ni recibos operativos.

# A1 — Handoff de integración con EJECUCION_SKILL_LF

**Tipo:** preparación source-only. **Estado:** `BLOCKED_NOT_WIRED`. No implica ejecución real ni modificación de Router.

## Lectura canónica (Supabase, 2026-11-03)

- `public.lf_operation_registry`: `EJECUCION_SKILL_LF` v0.1, `SANDBOX_ACTIVE`.
- `public.lf_router_action_registry`: `SKILL_EXECUTION`, `ACTIVE`, exige target existente, `write_allowed=false`.
- `public.lf_operation_step_contracts`: `init_execution → router → skill_resolve → skill_source_read → input_validate → execute_skill → output_validate → semantic_judge → report_output`.
- `public.lf_operation_judges`: `JUDGE-EJECUCION-SKILL-LF-v0.1` tiene `pass_if=[]` y `fail_if=[]`; eso no acredita por sí mismo enforcement server-side de resultados `FAIL`.
- `public.lf_activos`: A1 `PROGRAMMING_ANALYSIS_LF` no registrada (0).
- `public.lf_operation_execution`: A1 bajo `EJECUCION_SKILL_LF` (0); 414 ejecuciones históricas de skills ajenas, no prueban A1.

## Integración propuesta

Perfil consumidor ya seleccionado → handoff autorizado → operación EXISTENTE `EJECUCION_SKILL_LF` → resolver fuente A1 CURRENT → `prepare` → invocar modelo por dueño del runtime → `evaluate_model_candidate` → juez realmente independiente → `validate_review` → recorder/ledger → lectura del recibo → perfil consumidor decide A2.

El paso `router` de la operación deberá **reutilizar/validar la autoridad del handoff existente**, no disparar un segundo encaminamiento; este comportamiento está **pendiente de comprobar** en el runtime real.

Contrato de mapeo: `adapters/existing_skill_operation_binding_v1.json`.

## Gates de integración

1. Registrar y liberar gobernadamente A1 como SKILL, con fuente y hash exactos.
2. Verificar autoridad y modo habilitado de la operación para consumir A1; no convertir `SANDBOX_ACTIVE` en `CURRENT RELEASED` por inferencia.
3. Demostrar dos invocaciones de modelo efectivas y separadas para productor y juez, ambas con recibos del proveedor/host y hashes. No aceptar `PASS` auto declarado.
4. Confirmar enforcement negativo: `semantic_judge=FAIL` y `unsupported_claims` no vacíos producen rechazo real; la existencia de llaves no basta.
5. Registrar/leer los recibos en el mismo RUN gobernado y solo entonces retornar resultado al perfil. Sin direct-call Router→skill y sin `service_role` en Router.

**No cerrar A1 como `SKILL_READY` ni `SKILL_INTEGRATED` con este handoff.** Ninguno de estos gates operativos se ejecutó aquí.

## Homologación del transporte y ACL (readback 2026-11-04)

Ver `handoffs/A1_STEP_HOMOLOGY_DECISION_20261104.md` y `adapters/governed_step_homology_v1.json`. Input Governance cuenta con RPC pública OIDC bajo autoridad de worker; Profile Updater/Creator utilizan workflow GitHub OIDC → Edge con `service_role` restringido al servidor y registradores por operación. **Ningún conector de lectura debe ejecutar RPC de escritura directamente.**

La función `public.lf_record_creacion_skill_step_v1` registra **pasos de creación**, no la ejecución A1. La operación `EJECUCION_SKILL_LF` tiene 9/9 contratos y bindings, pero **no se identificó en `pg_proc` un wrapper público de registro de sus pasos**. Su núcleo común disponible no admite confianza autodeclarada desde el usuario. El patrón de transporte puede reutilizarse; no está conectado a destino SKILL.

La unidad histórica `A1` y su `A1Q` permanecen DONE y no se reciclarán como nuevo RUN. La habilidad `PROGRAMMING_ANALYSIS_LF` permanece sin registro oficial.
