# PG-04_C1 — trazabilidad J02 ↔ contrato de partición (2026-11-03)

## Dictamen

**`C1_PARTIAL_CONTRACT_PRESENT / J02_PARTITION_CORE_NOT_EVIDENCED / NO_NEW_ENGINE`**.

El objetivo canónico del checkpoint está literalmente en `supabase/migrations/20261028160000_lf_programming_pg00_standards_checkpoints_decisions_v2.sql` (Git blob `93c46714bd1f71910064fa55c571ffc23ddd39db`): «Base: contrato de partición del PR #1912 + núcleo extraído de J02, rehecho sobre main actual; sin motor paralelo». Salida: «Fuente reutilizada y trazada».

### Fuente 1. Contrato de partición sí existente

PR #1912 (abierto, HEAD `78030d6b8ea51f61807b8bc005ee9386a901a82a`):
- `wave1_boundary_contracts/programming_solution_partition_contract_v1.json`, Git blob `54ea02669c2f9ad199ac6fde154ec5dd30d6decb`. Schema `PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1`, unidad `PG-04`; define partición por solución semántica, dependencias, riesgo, write-scope, 100% requisitos+aceptación, sin duplicar ownership, PG07 RED→PG04 y autoridad desactivada.
- `wave1_boundary_contracts/validate_wave1_boundary_contracts_v1.py`, Git blob `bd8c1b0631772e10c92202e1639b527458ccb206`; `validate_pg04_partition(o)` verifica los flags/valores del **contrato**. No materializa soluciones, no compara semántica de cambios ni entrega un paquete de PG-04.
- PR #3387 DRAFT, HEAD `c410dd06fc7f1c9fc735b6b63868806f28dcd6b9`: `materialization_circuit.py` simula orden de entrega. **6/6 pruebas locales PASS**, no particionador.

### Fuente 2. J02 localizado es un componente de otra finalidad

Búsqueda de código en el repositorio: `J02`, `J02 decomposition`, `J02 partition`, `solution_partition`, `PG-04_C1`.

- `skills/creating-integral-user-stories/judges/screen-decomposition.yaml` (Git blob `1f5c57349163dceeb5b59807bed51a4750ceb5ee`), identifica **`J02_SCREEN_DECOMPOSITION v0.8`**, `CANDIDATO_READ_ONLY`. Función: verificar descomposición de pantalla contra una ingesta visual ciega; no planificar cambios de Programming por solución.
- `skills/creating-integral-user-stories/references/screen-decomposition-protocol.md` (Git blob `7bff646b586457c8d4fced4b8b0b36ae8591f621`). Explicita que se forman unidades funcionales por **resultado observable** (no posición visual), separándolas por actor, permiso, resultado, estado, riesgo y persistencia; exige referencias, cobertura por objeto y detector de duplicados.
- `skills/creating-integral-user-stories/scripts/validate_screen_decomposition.py` (Git blob `79b5de0bb5ce52852cb4f91a5bbb1c654206f66a`): `duplicate_units()` compara código y tupla `actor/goal/observable_output`; `uncovered()` evalúa fuentes por código o source_ref, sin confiar en cardinalidad. El runtime nominal del J02 v0.8 tiene un wrapper distinto, `validate_screen_decomposition_visual.py`. **No reutilizar directamente el juez de pantallas como juez de partición PG04**.
- La búsqueda no encontró evidencia verificable de commit/ruta/test del **«núcleo J02 extraído y rehecho para partición»**. Una búsqueda negativa no demuestra inexistencia en todas las ramas/PRs, pero impide declararlo implementado con las fuentes revisadas.

### Mapeo semántico seguro (conceptual, NO código nuevo)

| Principio fuente J02 | Equivalente exigido PG04 | Trasladable sin conversión automática |
|---|---|---|
| Separación por resultado observable y riesgo | Soluciones coherentes y válidas, considerando dependencias y riesgo | **Sí, como criterio de diseño**, no como función de partición ejecutada |
| `source_ref` por elemento y cobertura explícita | 100% requisitos y aceptación con owner exacto | **Sí, como invariante**, usando el validador de PG03_C8 existente como punto de partida |
| Detectar duplicados por semántica y código | 0 dueños duplicados y no duplicar soluciones | **Conceptualmente**; las identidades de entrada/contratos son diferentes |
| Ingesta visual bloqueada, códigos de pantalla | Paquete A9 / PG03 aprobado, variantes FE/BE/BD | **No**: no sustituir el modelo de fuente de Programming con `screen_ingestion` |
| Juez independiente de pantalla | Aseguramiento PG04_C7 | **No directamente**: conservar mecanismo `INDEPENDENT_ASSURANCE` con sujeto PG04 legítimo |

### Implicación de la auditoría

**C1 NO está terminado.** Sí tiene fuente contractual reutilizable, pero la extracción y prueba concreta «J02→PG04» sigue sin acreditarse. No inventar un motor, importarlo ciegamente del Story Creator ni presentar el contrato como algoritmo. Tampoco pedir cambios al propietario de otro repo: se seguirá trabajando solo en el sandbox de prueba.

Para cerrar técnicamente C1 se necesita identificar un núcleo J02 de partición genuino **o** una adaptación acotada con fuente, SHA, contrato de entrada/salida PG04, tests de partición semántica y evaluación independiente de trazabilidad. Si esto último se implementa, debe ser gobernado como adaptación, no como «reutilización ya hecha».

Para evitar detener todo PG04, **C3** puede comprobar offline la cobertura a través de `prepare_pg04_handoff` de PR #3509, sin convertirla en certificado de PG04. **C2** requiere todavía el particionador por significado; **C5/C6/C7** tienen fuentes de política/infraestructura que se pueden aprovechar independientemente.

## Estado

`PG04_C1_CONTRACT_IDENTIFIED / J02_REUSE_PRINCIPLES_MAPPED / J02_PG04_EXTRACTION_UNVERIFIED / PG04_C1_NOT_DONE`.

Sin escrituras Supabase, cambios main, merges o modificaciones del repositorio ajeno.
