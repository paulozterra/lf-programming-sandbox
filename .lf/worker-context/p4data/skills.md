# LF pinned stack skills / CANDIDATE_SANDBOX_ONLY
Standards source: paulozterra/lf-programming-sandbox@f18b2d96b7e1a8263749d35a7afcc9c043521cb8:standards/catalog.json
Catalog SHA-256: 26ca9cf9936ef01b50f9af504e4a9b796ee7d7d538d5724ff388c9fb90e8ddb3

## FLYWAY_EXP@1 priority 1
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


### Source-bound expert rules
{
  "schema_version": "LF_STACK_EXPERT_RULES_EXP_V1",
  "skill_code": "FLYWAY_EXP",
  "version": "1",
  "area": "DATA",
  "standard_family": "STD-DB",
  "rules": [
    {
      "rule_id": "FW-01",
      "text": "Respetar convenciones efectivas de nombre, orden y versionado de migraciones versionadas y repetibles.",
      "source_url": "https://documentation.red-gate.com/flyway/flyway-concepts/migrations"
    },
    {
      "rule_id": "FW-02",
      "text": "Ejecutar flyway validate para contrastar checksum, versión, tipo y descripción de scripts aplicados, registrando fallas.",
      "source_url": "https://documentation.red-gate.com/flyway/reference/commands/validate"
    },
    {
      "rule_id": "FW-03",
      "text": "Exigir evaluación de pérdida de datos antes de DROP/DELETE/TRUNCATE y evidencia de backup y recuperación.",
      "source_url": "https://documentation.red-gate.com/flyway/flyway-concepts/migrations/undo-migrations"
    },
    {
      "rule_id": "FW-04",
      "text": "No asumir que undo existe ni recupera información eliminada; verificar edición, soporte del motor y límites.",
      "source_url": "https://documentation.red-gate.com/flyway/flyway-concepts/migrations/undo-migrations"
    },
    {
      "rule_id": "FW-05",
      "text": "Para cambios incompatibles planear etapas de compatibilidad entre versión de esquema y aplicación y validar restauración.",
      "source_url": "https://documentation.red-gate.com/fd/implementing-a-roll-back-strategy-138347142.html"
    }
  ]
}


### Literal PG00 STD-DB rules
- STD-DB-01 [APROBADO]: Tablas y columnas en snake_case minúscula y en inglés (D4); tablas en plural (`debts`, `offers`)
- STD-DB-02 [APROBADO]: PK y FK según D5
- STD-DB-03 [APROBADO]: Constraints e índices con el nombre por defecto de Postgres (D6)
- STD-DB-04 [APROBADO]: `created_at`/`updated_at` `timestamptz not null default now()` en tablas nuevas; `updated_at` lo mantiene un trigger común del kit base, nunca la aplicación
- STD-DB-05 [APROBADO]: Booleanos `is_`/`has_`; enums con tabla catálogo o `CHECK`, sin valores inventados
- STD-DB-06 [APROBADO]: RLS activo en toda tabla nueva expuesta, con políticas explícitas
- STD-DB-07 [APROBADO]: `SECURITY DEFINER` con EXECUTE revocado de PUBLIC, grants mínimos y `search_path` fijo
- STD-DB-08 [APROBADO]: Migración: apply, reapply, rollback y reapply conservando datos; expand/contract para cambios incompatibles
- STD-DB-09 [APROBADO]: Nombre de migración: plataforma LF; producto `V<n>__<descripcion_snake>.sql` (Flyway)
- STD-DB-10 [APROBADO]: Funciones de la plataforma LF según D7
