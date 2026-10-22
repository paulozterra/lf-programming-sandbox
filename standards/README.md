# Reglamento técnico (PG-00) · v0.1

Catálogo de estándares del agente de Programación (niveles L1 y L2). Las reglas propias de cada
proyecto (L3) **no** viven aquí: las tipo A llegan en el paquete de la Fase 1 y las tipo B en el
manifiesto del perfil técnico de cada proyecto.

| Archivo | Para quién | Qué es |
|---|---|---|
| `catalog.json` | Herramientas | **Única fuente.** Reglas, severidad, control y decisiones D1–D17 |
| `CATALOGO.md` | Agente (LLM) y personas | Generado desde `catalog.json`; no se edita a mano |
| `tools/validate_catalog.py` | CI | Valida la estructura del catálogo |
| `tools/render_llm.py` | CI / autor | Regenera `CATALOGO.md` (`--check` verifica que esté al día) |
| `glossary/base.json`, `glossary/projects/*.json` | Herramientas | Glosario ES→EN: base (L1) y por proyecto (L3, candidato hasta que el proyecto lo adopte) |
| `GLOSARIO.md` | Agente (LLM) y personas | Generado desde los JSON del glosario; no se edita a mano |
| `tools/glossary.py` | CI, agente y PG-11 | Valida y genera el glosario, check en sombra del diff (STD-GEN-01) y cobertura positiva por `term_id` |
| `tools/checks.py` | CI y agente | Checks propios: nombres de archivo, supresiones con waiver, rama |
| `tests/` | CI | Cada check falla con su caso negativo (PG-00·C7) |

## Estados de control

- **active:** lo exige el CI y bloquea.
- **shadow:** corre en el CI y reporta, sin bloquear (D11). Pasa a `active` sobre código nuevo cuando la tasa de falsos positivos es aceptable (PG-00·C10).
- **review:** lo verifica el revisor de PG-11 con rúbrica sí/no.
- **planned:** control definido, aún no implementado.

## Cambiar el catálogo

1. Editar `catalog.json` (subir `catalog_version`).
2. `python3 standards/tools/render_llm.py`
3. `python3 -m unittest discover -s standards/tests`
4. PR con el GO del owner de la Fase 2. El circuito completo es PG-00·C9.

Destino canónico: esquema `transversal` de LF, vía Router → Train (pendiente). Este repo es de calificación.

## Waivers · PG-00·C8

El registro `standards/waivers/waivers.json` es la única fuente; `standards/WAIVERS.md` se genera con `python3 standards/tools/waivers.py render`. Sólo el owner `paulozterra` aprueba. **La entrada y el PR proponen la excepción; la aprobación se perfecciona sólo cuando Paulo une el PR.** Que `approved_by` diga su nombre antes del merge no sustituye ese acto humano.

Solicita un waiver mediante un PR con motivo, alcance y vencimiento. Sólo se admiten las reglas marcadas `waiver_policy.allowed` y reglas de linter no incluidas en la denylist. `STD-GEN-05` nunca admite excepciones. Los estados almacenados son `ACTIVE` y `REVOKED`; vencimiento y sustitución se derivan. Para renovar, agrega un ID nuevo que cite `supersedes`; nunca edites `expires_at` de la entrada anterior. Para revocar, conserva la entrada y registra `revoked_at` más `revocation_reason`. Las pruebas usan `--as-of` fijo.

`WAIVER-0001` es exclusivamente un `TEST_FIXTURE` y sólo cubre `standards/tests/fixtures/suppressions/good.ts`. No autoriza supresiones en aplicaciones reales.

Consultas de PG-03/PG-11: `python3 standards/tools/waivers.py list --path standards/tests/fixtures/suppressions/good.ts --linter eslint:no-console --as-of 2026-10-23T00:00:00Z --format json`. Para desviaciones que no son supresión: `Standard-Waiver: WAIVER-NNNN` en descripción del PR y `standard_deviations: [{rule_id, waiver_id, paths}]` en el paquete PG-03 (implementación posterior).

La verificación estructural del registro es bloqueante; el chequeo de citas corre en sombra según D11. El circuito de cambio de reglas pertenece a C9 y la medición de falsos positivos a C10.
