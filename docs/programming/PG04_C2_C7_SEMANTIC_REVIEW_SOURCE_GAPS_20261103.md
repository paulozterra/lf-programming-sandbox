# PG-04_C2/C7 — auditoría adversarial semántica y revisión independiente (2026-11-03)

**Estado:** `PG04_SEMANTIC_NEGATIVES_REPRODUCED / INDEPENDENT_REVIEW_NOT_EXECUTED / NO_GO_RUNTIME`.

## Qué se reutiliza

- Productor local existente `standards/tools/pg04_semantic_partition_candidate_v1.py`: genera particiones candidatas desde `outcome_id`, dependencias y obligación tipada. Concede cero autoridad: `CANDIDATE_NOT_ADMITTED`, `semantic_judge_executed=false`, `source_authenticity=UNVERIFIED`.
- Sonda de admisión previa `standards/tools/pg04_partition_admission_probe_v1.py`: checks deterministas, no comprensión semántica.
- Contrato #1912 `PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1`.
- Mecanismo gobernado LF `INDEPENDENT_ASSURANCE` / `REVISION_INDEPENDIENTE_ESTRATEGIA_LF` utilizado en C9 de PG03 (PRs #3523 y #3524). **No existe evidencia aquí de subject binding/operación PG04 activados**. Prohibido inventar revisor, juez, ledger, operación o receipts para cubrirlo.

## Dos negativos ejecutados sobre productor local

```text
BASE_SOLUTIONS [('SOL-001', ['API', 'DB']), ('SOL-002', ['UI'])]
BASE_CANDIDATE CANDIDATE_NOT_ADMITTED False
FORGED_OUTCOME_ACCEPTED [('SOL-001', ['API', 'DB', 'UI'])] CANDIDATE_NOT_ADMITTED False
UNVERIFIED_COIMPLEMENT_ACCEPTED [('SOL-001', ['API', 'DB', 'UI'])] UNVERIFIED False
```

- **NEG-01:** se cambia `UI.outcome_id` de `HISTORY` a `PAY` sin alterar la veracidad del pedido original. El algoritmo genera un único lote. No es fallo de autoridad (sigue candidato), sí demuestra que la clasificación semántica de un caller puede ser incorrecta.
- **NEG-02:** se declara unión API↔UI recíproca con `coimplement_evidence_ref='analysis://invented'`. La forma pasa, la procedencia no está autenticada. No puede aceptarse como decisión de diseño.

Las pruebas locales existentes del productor: 22/22 PASS comunicadas antes; los dos negativos son *sondas de limitación*, no pruebas de que el modelo semántico pase. No hay revisión modelo independiente ejecutada.

## Solicitud para la revisión REAL cuando el runtime la admita

Congelar y autenticar: `subject_sha256` de partición, `strategy_ref` PG03 admitido, A9 CURRENT, `requirement_ids/acceptance_ids`, inventario `outcome_id` con evidencia original, relaciones `coimplement_with` y referencias resolubles, perfil de riesgo, write scope, commit y run. Verificar productor≠revisor, identidad de proveedor, currentness de todas las fuentes y recibos gobernados.

El juez semántico independiente debe comparar contra **A9 original**: fidelidad de resultados, atomicidad y ausencia de merges injustificados, dependencias reales, referencias de contratos compartidos, conservación de delta EXISTING y ausencia de construcción duplicada, cobertura material bidireccional y riesgo/write scope. Debe producir hallazgos por `solution_id`/ `atom_id` con evidencia verificable. Un string `PASS` o SHA interno no equivale a `EVIDENCE_LEDGER VERIFIED`.

Pruebas adversariales futuras: falsificación outcome; `coimplement_evidence_ref` falso; candidate SHA drift; A9/PG03 run drift; self-review; PASS sin receipt; huérfano oculto bajo cobertura de IDs; remerge por presupuesto sin cierre de reparaciones.

## Bloqueo real / próxima decisión

PG01_C6 carece de un A9 real admitido en el último readback documentado por el PR #3524. No hay ejecución semántica independiente sobre PG04. El adaptador preflight PG03_C9 **no debe reutilizarse como si ya reconociera el sujeto PG04**, porque valida explícitamente `PG03_TECHNICAL_STRATEGY`. Lo reutilizable es la *capacidad gobernada genérica* solo tras demostrar la admisión contractual para PG04.

**No reclamar C2/C7 DONE.** Sin Supabase writes, merges ni cambios al repositorio de Cristhian.
