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

## Circuito de cambio C9

La fuente es `standards/changes/CHG-NNNN.json` y la vista derivada es
`standards/CAMBIOS.md`. El proceso obligatorio es **hallazgo → CHG →
PR → CI → revisión por Claude → merge de Paulo → versión vigente**.
`approved_by: paulozterra` es un aprobador previsto, **no prueba un GO**:
la aprobación efectiva se acredita luego con los metadatos del merge de GitHub.
No existe estado mutable en el CHG.

Un PR lleva **un CHG**, clase más restrictiva según diff.
`EDITORIAL` sube patch; `ADDITIVE`, `TIGHTENING`,
`RELAXING` y `SECURITY` suben minor durante 0.x.
RELAXING exige `risk` y `compensating_control`, nunca permite dispensar
las reglas L1/no dispensables de C8. Mezclar RELAXING y TIGHTENING exige separar PRs.
Un cambio de herramienta que altere veredictos exige CHG, aunque no cambie el
catálogo; su versión queda fijada por Git SHA.

Para SECURITY se requiere `independent_review` de otro chat, fuera del
proyecto LF, con memoria y personalización desactivadas; incluye
`reviewed_sha256`, `reviewer_ref` (hash de referencia privada),
`separation_declaration` del owner y `provider_attested: false`.
El CI valida estructura y huella, **no certifica** que la separación haya ocurrido.

`standards/pins.json` declara mínimos seguros, inicialmente todos null.
PG-01·C4 consumirá el pin; un cambio SECURITY que invalide el pin debe causar
`PIN_INVALIDATED_SECURITY` y revalidación antes de una nueva escritura.
El checker C9 controla coherencia; no ejecuta revalidaciones de PG-01.

`standards/baseline/STD-*.json` captura la deuda D11 por regla:
`count` y fingerprints SHA256(rule_id + path + reason_code + línea normalizada).
El baseline no puede aumentar; la calibración, renombres y falsos positivos
corresponden a C10. Las reglas nuevas bloquean solo lo nuevo/modificado.

Herramientas: `python3 standards/tools/changes.py validate`,
`render --check`, `check --base origin/main`,
`baseline-check --base origin/main` y
`pin-check --artifact catalog --version 0.5.0`.
La política de waivers continúa en `catalog.json`, sin duplicarla
en validadores Python; sus cambios normativos se controlan mediante CHG.

Destino canónico: esquema `transversal` de LF, vía Router → Train (pendiente). Este repo es de calificación.

## Waivers · PG-00·C8

El registro `standards/waivers/waivers.json` es la única fuente; `standards/WAIVERS.md` se genera con `python3 standards/tools/waivers.py render`. Sólo el owner `paulozterra` aprueba. **La entrada y el PR proponen la excepción; la aprobación se perfecciona sólo cuando Paulo une el PR.** Que `approved_by` diga su nombre antes del merge no sustituye ese acto humano.

Solicita un waiver mediante un PR con motivo, alcance y vencimiento. Sólo se admiten las reglas marcadas `waiver_policy.allowed` y reglas de linter no incluidas en la denylist. `STD-GEN-05` nunca admite excepciones. Los estados almacenados son `ACTIVE` y `REVOKED`; vencimiento y sustitución se derivan. Para renovar, agrega un ID nuevo que cite `supersedes`; nunca edites `expires_at` de la entrada anterior. Para revocar, conserva la entrada y registra `revoked_at` más `revocation_reason`. Las pruebas usan `--as-of` fijo.

`WAIVER-0001` es exclusivamente un `TEST_FIXTURE` y sólo cubre `standards/tests/fixtures/suppressions/good.ts`. No autoriza supresiones en aplicaciones reales.

Consultas de PG-03/PG-11: `python3 standards/tools/waivers.py list --path standards/tests/fixtures/suppressions/good.ts --linter eslint:no-console --as-of 2026-10-23T00:00:00Z --format json`. Para desviaciones que no son supresión: `Standard-Waiver: WAIVER-NNNN` en descripción del PR y `standard_deviations: [{rule_id, waiver_id, paths}]` en el paquete PG-03 (implementación posterior).

La verificación estructural del registro es bloqueante; el chequeo de citas corre en sombra según D11. El circuito de cambio de reglas pertenece a C9 y la medición de falsos positivos a C10.
