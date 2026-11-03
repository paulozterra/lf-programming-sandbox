# PG-04_C1/C2 — Partición semántica candidata por resultado y atomicidad (2026-11-03)

## Resultado y límites de autoridad

Se implementó **generación de particiones candidatas** a partir de obligaciones tipadas que ya declaran resultado de negocio, fuente, riesgo, dependencias y `implementation_state`: `standards/tools/pg04_semantic_partition_candidate_v1.py`. No se crea orquestador, juez semántico ni clasificador por texto libre.

Estado correcto: `PG04_SEMANTIC_PARTITION_LOCAL_PASS / TYPED_OUTCOME_INPUT_UNATTESTED / INDEPENDENT_SEMANTIC_JUDGE_NOT_RUN / NO_RUNTIME_AUTHORITY`.

## Fuentes reutilizadas

- PR #1912, contrato `PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1`: `sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/programming_solution_partition_contract_v1.json`, blob `54ea02669c2f9ad199ac6fde154ec5dd30d6decb`. Define SOLUTION, semántica primero, dependencia/riesgo/write scope, 100% cobertura y no partición por tokens/archivos.
- Migración canónica de checkpoints `20261028160000_lf_programming_pg00_standards_checkpoints_decisions_v2.sql`, blob `93c46714bd1f71910064fa55c571ffc23ddd39db`.
- J02 real: `J02_SCREEN_DECOMPOSITION`, protocolo blob `7bff646b586457c8d4fced4b8b0b36ae8591f621`. Reutiliza **principios** de unidad por resultado observable, fuente por objeto, evidencia y duplicados; **no copia** código de descomposición visual a Programming.
- `standards/tools/pg04_partition_admission_probe_v1.py` ya existente en sandbox: se ejecuta desde una regresión para confirmar que las soluciones generadas cumplen el mínimo estructural de la frontera. No reemplaza este productor.

## Algoritmo implementado, sin inferencia semántica no autorizada

1. Verifica el SHA interno de la estrategia PG03 y el contrato canónico de partición, con activación false.
2. Recibe `outcome_registry` con identificadores estables, resultado de negocio y `evidence_ref`. Cada `obligation` declara `atom_id`, `source_ref`, scope, `outcome_id`, `semantic_rationale`, riesgo, `write_scope`, referencias de contratos compartidos, `implementation_state`, requisitos, aceptación y relaciones.
3. Agrupa únicamente obligaciones del **mismo resultado identificado y binding de implementación compatible**; separa riesgo HIGH. Permite grupos que abarquen BE/BD/FE **si** comparten el resultado, el estado y evidencia de cohesión.
4. `depends_on` **ordena** grupos: una dependencia NO fusiona automáticamente soluciones. `coimplement_with` puede forzar co-ubicación entre resultados diferentes solo si es recíproco y referenciado; conflicto de estado o riesgo alto bloquea.
5. Conserva todas las referencias de cada átomo; asigna ownership único a requisitos/aceptaciones, recalcula cobertura total y valida DAG. Prohíbe definiciones inline de contratos compartidos y pérdida de delta/reuse.
6. Devuelve lista determinista de soluciones `SOL-001..N` con alcance, dependencias, obligaciones y source bindings; estado `CANDIDATE_NOT_ADMITTED`, `semantic_judge_executed=false`, `source_authenticity=UNVERIFIED`, sin despacho ni handoff autorizado.

Ejemplo sintético en la prueba: API y BD sirven el resultado `PAY` y se agrupan; UI sirve `HISTORY` y queda separado, dependiente de API/BD. No se construyeron tareas reales ni código de aplicación.

## Ejecución y evidencia

Copia local de desarrollo: `/mnt/data/pg04_candidate`.

```sh
cd /mnt/data/pg04_candidate
python -m unittest -v test_pg04_semantic_partition_candidate_v1.py
# 21/21 PASS inicial
# luego de separar explícitamente riesgo HIGH:
python -m unittest -q test_pg04_semantic_partition_candidate_v1.py
# Ran 22 tests in 0.004s
# OK
```

Pruebas: determinismo, independencia del orden, resultado multinivel y dependencia, compatibilidad con el inspector previo; ausencia de autoridad; SHA de estrategia; resultado fuente inexistente, procedencia ausente, huérfanos, duplicados, contratos inline, estados EXISTING/NEW incompletos, dependencia desconocida/ciclo, coimplementación no recíproca, mezcla de estados, conflicto de riesgos, drift de política, separación HIGH.

**Aclaración de exactitud:** la ejecución local se hizo sobre una versión funcional del productor con la misma lógica y 22 casos. Los archivos publicados en el sandbox pueden diferir en detalles editoriales. La prueba reproducible del **HEAD exacto publicado** corresponde al CI GitHub; no atribuirle resultados de CI no observados.

## Brecha técnica restante

La calidad de la decisión `outcome_id`/cohesión proviene de datos tipados que debe aportar una fuente auténtica y un **juez semántico independiente**. Este productor **no entiende por sí solo texto libre** ni puede certificar que dos obligaciones pertenezcan al mismo objetivo funcional real. `semantic_boundary_reason` es explicación de criterio, **no evidencia de juicio independiente**.

C1 sigue parcialmente pendiente: la adaptación J02 está demostrada por principios, no por extracción byte a byte de un núcleo de partición anteriormente existente. C2 tiene **generación candidata reproducible**, pero su semántica depende de entrada tipada. Faltan A9/PG03 real, fuente vigente y assurance C7/PG04, además de C5/C6.

No tocar repo de Cristhian, Supabase, main, writer, dispatcher ni merges.
