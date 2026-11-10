# Flyway — stack skill de ENSAYO
**Estado:** CANDIDATE_SANDBOX_ONLY. **Área declarada:** DATA. **Código:** FLYWAY_EXP. **Versión:** 1.

## Vinculación
La skill se obtiene exclusivamente de project_stack_binding_exp por proyecto, área y versión con prioridad explícita. No la elige la IA.

## Reglas expertas verificables
- **FW-01:** Respetar convenciones efectivas de nombre, orden y versionado de migraciones versionadas y repetibles. **Fuente oficial:** https://documentation.red-gate.com/flyway/flyway-concepts/migrations
- **FW-02:** Ejecutar flyway validate para contrastar checksum, versión, tipo y descripción de scripts aplicados, registrando fallas. **Fuente oficial:** https://documentation.red-gate.com/flyway/reference/commands/validate
- **FW-03:** Exigir evaluación de pérdida de datos antes de DROP/DELETE/TRUNCATE y evidencia de backup y recuperación. **Fuente oficial:** https://documentation.red-gate.com/flyway/flyway-concepts/migrations/undo-migrations
- **FW-04:** No asumir que undo existe ni recupera información eliminada; verificar edición, soporte del motor y límites. **Fuente oficial:** https://documentation.red-gate.com/flyway/flyway-concepts/migrations/undo-migrations
- **FW-05:** Para cambios incompatibles planear etapas de compatibilidad entre versión de esquema y aplicación y validar restauración. **Fuente oficial:** https://documentation.red-gate.com/fd/implementing-a-roll-back-strategy-138347142.html

## L1/L2 y L3
Familia `STD-DB` referenciada en `supabase/migrations/20261028160000_lf_programming_pg00_standards_checkpoints_decisions_v2.sql`, que NO contiene el texto normativo completo. `PG00_STANDARD_TEXT_UNAVAILABLE` hasta recuperar fuente canónica versionada con huella. Las reglas de stack no sustituyen la política LF.

## Salida
Emitir a Worker visible las reglas de la skill identificadas por ID y fuente (mínimo tres), sin autoridad ni oráculo. `production_authority=false`; `runtime_enabled=false`; `promotion_allowed=false`.
