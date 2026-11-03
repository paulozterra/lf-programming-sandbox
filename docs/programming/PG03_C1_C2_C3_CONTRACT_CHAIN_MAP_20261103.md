# PG-03 C1/C2 → C3 — frontera de integración, sin duplicar ejecutores

**Corte:** 2026-11-03 · **Modo:** TECHNICAL · **Estado:** SOURCE_CONTRACT_MAPPED / CHAIN_NOT_EXECUTED

## Fuentes existentes (revisadas, no copiadas)

| Función propietaria | PR y HEAD exacto | Salida pertinente |
|---|---|---|
| `pg03_stack_source_v1.resolve_stack` (C1) | `cristhianlujan/claude-persona-lf-patch#3497` · `e51b2a20a00e46fa30ef78f7d53fc37687505002` | `status=CANDIDATE_NOT_ADMITTED`, `authority=false`, `repo_full_name`, `commit_sha`, `sources:[{path,kind,sha256,bytes}]` |
| `standards/tools/skills.py::select_and_assemble` (C2) | `paulozterra/lf-programming-sandbox#19` · source previo `3bdedf43575cde773e1a958bd0fcc75a3fda1dae` | `selection_status=CANDIDATE_NOT_ADMITTED`, `production_authority=false`, `pg02_source_verified=false`, `catalog_sha256`, `skills` con digests; **no** run/source/selector commit |
| `pg03_c2_skill_receipt_binding_v1.validate_skill_selection_receipt` (C2) | `cristhianlujan/claude-persona-lf-patch#3519` · `171028e3f382e173efe249c9a630b299dc3d53d3` | Exige `status`, `run_id`, `stack_commit`, `catalog_sha256`, `selector_repo/path/commit`, `active_domains`, skill versions/digests; rechaza drift, pero `selector_execution_verified=false` |
| `pg03_strategy_v1.prepare_strategy` (C3) | `cristhianlujan/claude-persona-lf-patch#3498` · `1a3dfe22a8ceaed4306a719e9391694d122342a2` | Consume `classification`, `stack_evidence`, partition contract, requirements/acceptance, etc.; produce `PG03_STRATEGY_CANDIDATE_V1` con `handoff_allowed=false` |

## Conexión mínima sin crear otro componente

1. Obtener `classification` de PG-02 existente, incluyendo scopes READY y `candidate_domains`; **no regenerar** esa clasificación a partir del recibo de Skills.
2. Obtener `stack_evidence` de **C1**: `resolve_stack` produce precisamente `status`, `authority`, `commit_sha`, `sources` que espera C3. Mantener `stack_profile_verified=false` y comprobar el commit común en la prueba de frontera.
3. Ejecutar el selector C2 `select_and_assemble` sobre dominios activos concretos y pin de catálogo. No mapear el resultado directamente a `stack_evidence`.
4. **Para usar el binding C2 #3519:** el recibo de ensamblado debe acompañarse de campos externos `run_id`, `stack_commit`, `selector_repo/path/commit`, `active_domains` y versiones de Skills, obtenidos de fuente/traza propietaria. El test de #3519 usa un fixture manual; eso **no verifica la ejecución real del selector**. No rellenar campos con cadenas arbitrarias y declarar autenticación.
5. Consumir C3 con la evidencia C1 independiente y las decisiones de estrategia ya existentes. La función C3 **no** consume directamente la salida de #3519; por tanto el PASS de C3 aislado **no demuestra** que el contexto C2 se utilizó. Se necesita prueba de igualdad de run/commit/dominios y referencia del recibo C2 antes de declarar cadena C1/C2/C3 integrada.
6. La corrección de `scope_id` de C3 está preparada como parche en este sandbox, no instalada upstream.

## Evidencias en el sandbox

- `standards/tests/test_pg03_c2_c3_contract_boundary_v1.py`: cuatro pruebas de frontera; se ejecuta en el job estándar por `python3 -m unittest discover -s standards/tests -v`.
- GitHub CI del HEAD `b869f5bc6c4e33f063b390b57dfc83d0fb267de5`: [run #41686037734](https://github.com/paulozterra/lf-programming-sandbox/actions/runs/41686037734) — **cinco jobs SUCCESS**.
- `docs/programming/patches/PG03_C3_SCOPE_ID_GUARD_20261103.patch`: cambio puntual para código propietario en #3498, no copia del estrategizador.

## Criterio de siguiente paso

**C1/C2→C3, prueba encadenada positiva:** con clasificación y stack C1 sintéticos inequívocos, ejecutar funciones originales (sin duplicarlas), obtener recibo de C2 del selector real, ligarlo a la misma identidad de prueba sin elevar autoridad, construir estrategia con C3, y comprobar `scope_ids` / `active_domains` / `stack_commit_sha` / `candidate_sha256`, más adversariales de drift de commit/run, dominio, selección y scope duplicado.

**Bloqueo de esta rama:** el sandbox solo contiene la implementación propietaria C2; las funciones C1, binding y C3 viven en otro repo y no deben copiarse como motores. Si se requiere probarlas juntas, usar checkout aislado de ambos repos en un arnés de prueba por SHA o un workflow previamente autorizado. La falta de ese arnés no autoriza a inventar recibos ni afirmar CHAIN_PASS. No tocar Router/PG-00/Análisis, ni declarar pendiente de autoridad como bloqueo de calificación técnica.

**Próximo estado:** `C2_C3_CONTRACT_BOUNDARY_CI_PASS` / `C1_C2_C3_CHAIN_POR_VERIFICAR`.
