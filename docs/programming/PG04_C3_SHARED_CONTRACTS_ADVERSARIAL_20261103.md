# PG-04_C3 — prueba adversarial contra handoff existente, contratos compartidos (2026-11-03)

## Fuente exacta y propósito

Se ejecutó **la función original** `prepare_pg04_handoff()` de `cristhianlujan/claude-persona-lf-patch`, PR #3509 HEAD `6067db67e39cd0d29fdda7205b206f250f7ed8bf`, sobre la copia local `/mnt/data/pg03_c8_audit/original.py`; `git hash-object` local `d824f3c61021ada7ebb6aec2e6b1fa984f69ec57` coincide con el Git blob original. No se usó la copia parcheada para este ensayo.

Fuente del requisito PG04_C3: `supabase/migrations/20261028160000_lf_programming_pg00_standards_checkpoints_decisions_v2.sql` (blob `93c46714bd1f71910064fa55c571ffc23ddd39db`) pide cobertura bidireccional 100%, sin huérfanos, ni ownership duplicado, dependencias explícitas y **contratos compartidos referenciados, no copiados**.

El contrato declarativo existente #1912, `programming_solution_partition_contract_v1.json` (blob `54ea02669c2f9ad199ac6fde154ec5dd30d6decb`) exige `partition_policy.shared_contracts_referenced_not_copied=true`. Su validador comprueba la declaración, pero no se observó una materialización de soluciones en su función `validate_pg04_partition`.

## Ensayo ejecutado

Fixture sintético de estrategia C3 candidata con dos requisitos `R1/R2`, dos aceptaciones `A1/A2`, scope `S1`, dos soluciones `SOL1/SOL2` con owner único, dependencia SOL2→SOL1, C6 candidata suficiente y C7 sin excepciones. No hay autoridad productiva.

Comando: `python` importando `original.py` desde `/mnt/data/pg03_c8_audit` mediante `importlib.util`; cada variante usa `copy.deepcopy` de la entrada y llama la misma función original.

Salida:
```text
baseline ACCEPTED CANDIDATE_NOT_ADMITTED authority False
contract_inline_copy ACCEPTED CANDIDATE_NOT_ADMITTED authority False
contract_ref_absent ACCEPTED CANDIDATE_NOT_ADMITTED authority False
contract_policy_false ACCEPTED CANDIDATE_NOT_ADMITTED authority False
```

- `contract_inline_copy`: `SOL1` contiene `shared_contracts=[{"id":"API-1","definition":{"request":"duplicated","response":"duplicated"}}]` — la copia inline llega a un handoff candidato sin detección.
- `contract_ref_absent`: se agrega `shared_contracts=[]` en SOL1 — se acepta sin evaluar si la solución requiere una referencia material.
- `contract_policy_false`: cambia `shared_contracts_referenced_not_copied=false` en el contrato entregado — el handoff C8 acepta pese a que el esquema canónico de #1912 lo exige.

**Interpretación delimitada:** no se demuestra que la arquitectura real copie contratos ni que PG03_C8 tuviera obligación contractual completa de comprobar C3. C8 ya verifica requerimientos/aceptaciones y DAG; faltan **checks del conjunto de soluciones PG04** contra las referencias canónicas compartidas y una validación previa exacta del contrato de política. No añadir estos controles como segundo motor dentro de PG03_C8 sin decidir el punto propietario. El estado es **`PG04_C3_SHARED_CONTRACTS_UNVERIFIED`**, no PASS ni ejecución productiva.

## PG04_C1 — rastreo J02

La fuente real `J02_SCREEN_DECOMPOSITION v0.8`, en `skills/creating-integral-user-stories/judges/screen-decomposition.yaml` (blob `1f5c57349163dceeb5b59807bed51a4750ceb5ee`), es un juez de pantallas. Reutilizables **como principios**: unidades por resultado observable, cobertura por referencias, duplicados semánticos, separación ante riesgo/estado/actor. **No es un algoritmo ya adaptado a PG04**. Detalle en `PG04_C1_J02_SOURCE_TRACE_AUDIT_20261103.md`.

## Bloqueo y paso admisible

- **C1:** extraer un núcleo adaptable de descomposición funcional (separación semántica + trazabilidad), definiendo contrato PG04; la extracción no está demostrada por PR #1912 o #3387.
- **C3:** verificar la política contra el contrato canónico y asegurar que cada solución tiene `shared_contract_refs` vinculadas a fuentes auténticas cuando aplican; rechazar payloads `shared_contracts` inline no autorizados.
- Los checks PG03_C8 ya presentes no se deben eliminar ni duplicar. Los jueces de J02 o C9 no conceden autoridad PG04.
- Sin cambios al repositorio propietario, Supabase ni `main`. No se ha ejecutado el handoff real.

**Dictamen:** `PG04_C1_SOURCE_CONTRACT_IDENTIFIED_J02_EXTRACTION_MISSING / PG04_C3_SHARED_CONTRACTS_NEGATIVE_REPRODUCED / PG04_OFFLINE_INTEGRATION_PENDING`.
