# PG-04 C1/C2 — candidato de inspección de particiones, no motor (2026-11-03)

## Fuentes y alcance

- Contrato **existente**: `cristhianlujan/claude-persona-lf-patch` PR #1912, `programming_solution_partition_contract_v1.json`, blob `54ea02669c2f9ad199ac6fde154ec5dd30d6decb` — `SOURCE_ONLY_CANDIDATE`.
- J02 encontrado: `J02_SCREEN_DECOMPOSITION`, `screen-decomposition-protocol.md` blob `7bff646b586457c8d4fced4b8b0b36ae8591f621`. Reutilizables **principios** de atomicidad semántica, referencias y trazabilidad; no afirmar que ese juez de pantallas fue convertido en un particionador PG04.
- Checkpoints canónicos PG04_C1/C2 definidos en `20261028160000_lf_programming_pg00_standards_checkpoints_decisions_v2.sql`, blob `93c46714bd1f71910064fa55c571ffc23ddd39db`.
- Reutilizar el validador de *contrato* `validate_pg04_partition` de #1912. Reutilizar `prepare_pg04_handoff` de #3509 para cobertura/dag donde corresponda. Este ensayo no los reemplaza.

## Entregable del sandbox

`standards/tools/pg04_partition_admission_probe_v1.py`: función pura `inspect_candidate` que **inspecciona** una lista de soluciones propuesta externamente. **No produce soluciones**, no decide semánticamente si son óptimas, no llama modelo, no despacha ni lee ledger y no otorga autoridad.

La sonda verifica que se declare:
1. política fuente PG04 y sin activación;
2. SHA interno de la estrategia PG03 y `strategy_ref` igual en cada solución;
3. frontera semántica, resultado observable, razón de riesgo y write scope;
4. prohibición de particionar solo por archivos/tokens;
5. `shared_contract_refs` en vez de definición inline;
6. `implementation_state` explícito: EXISTING requiere AS-IS+DELTA; NEW requiere evaluación de reutilización referenciada;
7. cobertura única de requisitos/aceptación y DAG sin dependencias desconocidas/cíclicas.

`standards/tests/test_pg04_partition_admission_probe_v1.py`: 17 tests (2 positivos/determinismo y 15 negativos) con fixtures sintéticos. Un resultado positivo sigue siendo `CANDIDATE_NOT_ADMITTED`, `production_authority=false`, `dispatch_allowed=false`, `handoff_allowed=false`.

## Ejecución local previa a commit

Antes de crear los archivos se implementó una versión funcional equivalente en `/mnt/data/pg04_candidate`. Su suite:
```
python -m unittest discover -s /mnt/data/pg04_candidate -v
Ran 17 tests in 0.003s
OK
```
La versión subida al repositorio conserva el comportamiento y los 17 casos pero incluye cambios editoriales; **la ejecución anterior no es una prueba exact-HEAD de los bytes subidos**. Esperar el job de catálogo/tests del CI de GitHub para verificar esa versión exacta.

## Lo que sigue pendiente (no ocultarlo)

- **PG04_C1 NO DONE**: `source_refs` lo entrega el caller, sin pin actual ni atestación. Una ruta J02 en el fixture no acredita extracción o adaptación productiva. Debe localizarse o implementarse con gobernanza el núcleo semántico verdadero, no copiar el juez de pantallas.
- **PG04_C2 NO DONE**: `partition_basis=SEMANTIC_SOLUTION` y `semantic_boundary_reason` son declaraciones. La sonda evita omisiones estructurales, pero **no comprueba la calidad semántica independiente** ni genera particiones.
- **PG04_C3/C4:** los checks de esta sonda son pruebas de frontera sobre soluciones propuestas, no autoridad ni reemplazo de los validadores de PG03_C8/A9.
- **PG04_C5–C7:** aún requieren DoD por lote, retorno PG07→PG04 y assurance independiente real.
- No hay recibo A9/PG03_C9 real autorizado; no conectar al dispatcher ni writer.

**Dictamen:** `PG04_C1_C2_SOURCE_ONLY_INSPECTION_CREATED / LOCAL_PRECOMMIT_17_PASS / EXACT_HEAD_CI_PENDING / NO_PARTITION_ENGINE / NO_AUTHORITY`.

Sin merge, Supabase write ni cambios al repositorio propietario.
