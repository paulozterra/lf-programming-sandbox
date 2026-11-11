# A2 Golden — Reutilizar patrón nativo EJECUCION_PERFIL_LF (pre-admisión)

**Fuente verificada el 2026-11-06:** Supabase `pg_get_functiondef` en `public`, Main del repo y EKB. **Estado:** propuesta técnica acotada, NO migración/despliegue ni autorización de ejecución. Negocio/skill: `LF` / `PROGRAMMING_ANALYSIS_LF`.

## A. Comparación del patrón real

| Función de ejecución de perfiles (real) | Equivalente de skills | Decisión |
|---|---|---|
| `lf_profile_execution_begin_from_handoff_v1` valida handoff y admisión antes de abrir | Extensión acotada de la acción existente `profile_native_skill_invoke_v1` y de su caller autorizado | REUTILIZAR el transporte GitHub OIDC → Edge → Supabase, sin segundo Router |
| `lf_profile_execution_begin_v1` invoca `fn_lf_operation_reserve_execution_v1`, después materializa `init_execution` / 0 | Wrapper mínimo propuesto `lf_skill_execution_begin_from_profile_v1` | MISMO reservador y paso 0, usando operación `EJECUCION_SKILL_LF` y target `SKILL` |
| `lf_record_profile_execution_step_v1` invoca `lf_profile_execution_trust_validation_v2` y `lf_record_operation_step_core_v1` | Wrapper mínimo propuesto `lf_record_skill_execution_step_v1` y validador gobernado `lf_skill_execution_trust_validation_v1` | REUTILIZAR núcleo; NO usar registrador de CREACION_SKILL |
| Pasos 0,10,20,30,40,45,47,50,60,70,80 | Pasos 0,10,20,30,40,50,60,70,80 | NO copiar pasos adicionales de perfiles a la skill |
| Paso 70: `semantic_judge` con binding y recibo de la misma ejecución | Paso 70: `semantic_judge` de `EJECUCION_SKILL_LF` | Debe acreditar juez independiente; NO reemplaza por sí solo la revisión interna de A2 antes de A3 |
| Paso 80 cierra después de todos los pasos limpios | Paso 80 cierra tras 9 pasos limpios | NO cerrar invocación al producir un output SQL; esperar juez, readback y reporte |

**Verificaciones de fuentes actuales:** `lf_profile_execution_begin_from_handoff_v1` MD5 `e0396d73d0a4652a47cc5dfc3206b19f`; `lf_profile_execution_begin_v1` MD5 `7a9129c31fd11443c2ed92107bcb7d8b`; `lf_record_profile_execution_step_v1` MD5 `7cf717887006e278356a716f3fd80182`; `lf_profile_execution_trust_validation_v2` MD5 `4a14fef959203b9b41212862877585f0`; `lf_record_operation_step_core_v1` MD5 `fe08a25c8e3c023d7181194d2dfdee0d`. Son huellas de lectura, no autorizaciones de escritura.

## B. Flujo mínimo propuesto

```text
Router ACT-0001 → EJECUCION_PERFIL_LF (RUN padre, negocio y recibo)
   → perfil pide PROGRAMMING_ANALYSIS_LF mediante la ACCIÓN existente
   → Edge caller vigente valida OIDC, RUN padre activo, negocio y origen exacto
   → invocador/adaptador nativo:
       1. admite sólo skill READY, READ_ONLY, binding habilitado y authority ACTIVE
       2. resuelve fuente Main exacta y digest
       3. reserva RUN hijo con fn_lf_operation_reserve_execution_v1 (idempotente)
       4. crea / verifica init_execution (0) según binding nativo
       5. readback RUN hijo + paso 0 + parent/skill identity
       6. retorna RUN_OPENED_PENDING_EXECUTION, NO COMPLETED
   → 10 Router → 20 skill_resolve → 30 source_read → 40 input_validate
   → 50 execute_skill: A1 → A2 → [juez nativo existente antes de A3]
         ├ PASS con SHA/recibo y mismo negocio/RUN → A3
         ├ FAIL reparable → feedback exacto a A2, máximo 3 entregas
         └ 3 FAIL → no A3, expediente terminal al perfil
   → 60 output_validate → 70 semantic_judge (juicio global del RUN)
   → 80 report_output + cierre gobernado solo con todos los pasos limpios
   → recibo terminal; recién aquí se considera COMPLETED
```

## C. Contrato del ajuste sin nuevo motor

**Wrapper de apertura de skill (PROPUESTO, no existe):**
- Entrada: actor/caller autenticado y RUN padre obtenidos **server-side**; no aceptar `_trusted` ni `expected_business` como autorización.
- Verificar `EJECUCION_PERFIL_LF` en `IN_PROGRESS`, perfil/negocio `LF`, `request_sha256` y recibo Router; `PROGRAMMING_ANALYSIS_LF` en `lf_activos`, `lf_skill_catalog_v1` y `lf_profile_write_authority_v1`, además de revisión Main y OIDC.
- El catálogo actual **no** contiene esta skill y hoy faltan filas de autoridad para `EJECUCION_SKILL_LF`; fail closed. **No modificar autorizaciones por este lote.**
- Reservar con el reservador existente, luego materializar paso 0 únicamente si es una reserva nueva; en replay readback y jamás duplicar el paso. Revalidar manifiesto exacto porque el reservador NO lo compara íntegro.
- Guardar en `lf_skill_invocation_v1` el vínculo al RUN hijo **sin declarar `COMPLETED` antes de ejecutar el modelo y el juez**; cualificar los estados permitidos por la tabla y su consumidor antes de cambiar código oficial.
- Return: `RUN_OPENED_PENDING_EXECUTION`, `execution_id` real, recibo exacto, `step0` comprobado, `a3_allowed=false`. Bloquear si falta cualquiera.

**Wrapper de pasos (PROPUESTO, no existe):**
- Operación/target fijados a `EJECUCION_SKILL_LF` / `SKILL`, contratos/judge bindings `ACTIVE_ENFORCEMENT`.
- `init_execution` se materializa solo en el inicio, es inmutable en recorder.
- `lf_skill_execution_trust_validation_v1` propuesto debe resolver identidad desde BD, exigencia de fuente Main, actor OIDC y evidence binding; **no** reutilizar directamente `lf_profile_execution_trust_validation_v2`, que valida documentos/contratos del perfil.
- Reutilizar `lf_record_operation_step_core_v1`; `p_close_on_report_output=true` solo con PASS comprobado en 0..80 y juicio real; bloquear duplicado, mala secuencia y missing evidence.
- Las 12 dimensiones/59 elementos se evalúan dentro de A2 según activación; la falta de evidencia que le corresponde recopilar a A3 no es automáticamente FAIL de A2.

## D. Pruebas obligatorias antes de cualquier admisión

| ID | Escenario | Expectativa |
|---|---|---|
| PP01 | Skill sin catálogo READY / binding activo | BLOCKED, sin RUN |
| PP02 | Perfil sin authority ACTIVE para `EJECUCION_SKILL_LF` | BLOCKED |
| PP03 | Negocio raíz LF vs recibo Router SALY / negocio ausente | BLOCKED |
| PP04 | Caller distinto del OIDC admitido, source Main cambiado | BLOCKED |
| PP05 | Reserva inicial autorizada | RUN hijo IN_PROGRESS + paso 0 limpio y readback real |
| PP06 | Mismo request/idempotency key | REPLAY exacto sin crear segundo RUN o duplicar paso 0 |
| PP07 | Replay con distinta source revision/manifest/negocio | BLOCKED antes de avanzar |
| PP08 | Paso 50 antes de 0..40, o pasos fuera de orden | BLOCKED |
| PP09 | Output SQL no es juicio; no marcar la invocación COMPLETED antes de 70/80 | PENDING |
| PP10 | A2 falla (con feedback) dos veces y aprueba en tercera | A3 solo luego del PASS real y recibo |
| PP11 | A2 falla tres entregas | Bloquear A3; reporte terminal al perfil; ticket solo con closure receipt |
| PP12 | Paso 70 sin juez independiente acreditado, o con digest distinto | BLOCKED |
| PP13 | Paso 80 sin todos los pasos limpios | No cierre |
| PP14 | Todo limpio con readback post-write | COMPLETED con recibo exacto |
| PP15 | Invocación READ_ONLY SQL sin RUN hijo | `RUN_GOVERNED_CHILD_ABSENT_READ_ONLY_INVOKER`, no A3 |

## E. Ruta de implementación gobernada

1. **Sin cambio de autoridad**, revisar ruta del caller Edge existente (`profile_native_skill_invoke_v1`); proponer una rama de transporte para skill nativa, conservando la ejecución SQL vigente de otras skills.
2. Preparar fuentes SQL candidatas (no desplegables) para apertura + wrapper de pasos + validación de confianza con firma contractual. No duplicar el core ni editar Router.
3. Ejecutar pruebas negativas/invariantes y comparación funcional con perfiles; revisión independiente/PASE sobre HEAD exacto.
4. Solo con admisión aprobada y authority/binding acreditados, llevar la migración al proceso gobernado; readback RUN/0..80/juez; después cerrar.

**Estado:** diseño basado en fuentes CURRENT, NO `READY`, NO runtime integrado, NO juez real y NO RUN abierto. Ninguna mutación de Main/Supabase ni ampliación de alcance de producción.
