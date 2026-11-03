# PG-04 — Inventario de reutilización y ejecución de circuito original (2026-11-03)

**Modo:** ruta crítica técnica; no confundir `SOURCE_ONLY_CANDIDATE` con autorización operativa.

## Fuente original probada

- Propietario: `cristhianlujan/claude-persona-lf-patch` PR #3387 (DRAFT), HEAD `c410dd06fc7f1c9fc735b6b63868806f28dcd6b9`.
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_materialization_order_candidate/materialization_circuit.py` Git blob `b0d832c663051fb8cbfac16061098ac943355ed1`.
- `.../test_materialization_circuit.py` Git blob `98ec0c4baa9392c32b6e52dc8c79050be1eef3ee`.
- Ambos reconstruidos en `/mnt/data/pg04_order_audit`, hashes `git hash-object` coinciden exactamente con GitHub.

Comando ejecutado:
```sh
cd /mnt/data/pg04_order_audit
python -m unittest -v test_materialization_circuit.py
```
Resultado `Ran 6 tests in 0.001s / OK`, todos los casos existentes PASS.

## Qué sí demuestra

El circuito `Circuit.advance()` conserva el orden obligatorio:
`PG01_ADMITTED → TASK_DRAFT_CREATED → TASK_SEALED_BY_DB → BLIND_TEST_CONTRACT_DRAFT → BLIND_TEST_CONTRACT_SEALED_BY_DB → DELIVERY_CONTRACT_DRAFT → DELIVERY_CONTRACT_SEALED_BY_DB → DB_READINESS_CONFIRMED`.

Las pruebas rechazan saltear sellado, adelantar entrega, invocar dispatch luego de readiness sintético y cualquier transición sin `authenticated=True`; una transición rechazada no cambia estado. `dispatch_allowed=false` y `production_authority=false` en todo el circuito.

## Qué NO demuestra

`authenticated` es un **booleano proporcionado por caller**: no valida firma, ledger, origen real ni permisos. El PASS local no acredita que tarea/contrato de pruebas/entrega estén sellados por DB real. No se ejecutó `fn_task_readiness`, ningún writer ni Worker; no se completó handoff de PG03_C8 admitido. Esto no permite cierre de checkpoint oficial o entrada a PG05 real.

## Reutilización antes de más código

- PR #1912 ya define contrato canónico de partición por solución `PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1`.
- PR #3509 ya protege cobertura de requisitos/aceptación por solución y DAG en candidato; su parche de `strategy_ref` está preparado en sandbox.
- PR #3387 ya implementa circuito de orden de materialización; **no crear otro orquestador, particionador ni circuito**.
- Siguiente esfuerzo técnico aconsejado: inventariar checkpoints individuales PG04 contra el plan maestro, identificar el primer punto sin prueba o cobertura, y agregar **solo una regresión o enlace existente**, sin elevar `authenticated` a prueba productiva.

**Dictamen:** `PG04_MATERIALIZATION_ORDER_ORIGINAL_6_PASS / CROSS_COMPONENT_BINDING_NOT_VERIFIED / RUNTIME_NOT_ADMITTED`. No merges, no Supabase writes, no cambio en Cristhian.
