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
