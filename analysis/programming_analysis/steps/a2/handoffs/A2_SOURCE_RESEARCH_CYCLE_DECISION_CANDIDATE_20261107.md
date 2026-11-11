# A2 — decisión de diseño para resolver investigación antes de admisión (candidato)

**Alcance:** A1/A2/A3 funcional, `PROGRAMMING_ANALYSIS_LF`, PR #3624. Documento de propuesta source-only. No cambia contratos canónicos, Router, D4, SQL, runtime ni permisos. NO autoriza A3.

## Defecto P0 constatado por lectura exacta del código

1. A1 material: `REQUIRES_DECISION`, `next_capability=null`, con `REQUEST_CONTEXT_V1` válido y candidato semántico conservado.
2. A2 `steps/a2/validators/run.py` exige `a1.status=VALID_OUTPUT`, `semantic_review_required=false` y `next_capability=A2`. Rechaza ambos casos CORE_02 y CORE_04 antes de aplicar profundidad.
3. A3 `analysis_targeted_evidence_contract_v1.json` recibe **exactamente** `REQUEST_CONTEXT_V1` + `ANALYSIS_CHANGE_CLASSIFICATION_V1`. El preview nuevo devuelve `a3_canonical_inputs=null` y `a3_dispatch_allowed=false`.
4. Consecuencia: existe un plan de investigación correcto, pero no una ruta elegible para que el A3 canónico obtenga las fuentes requeridas. No declarar integración ni resolución.

## Opciones evaluadas

| Alternativa | Efecto | Riesgo | Decisión |
|---|---|---|---|
| A. Volver a preguntar al propietario ante cada ambigüedad | Evita el ciclo | Duplica preguntas y desconoce definiciones existentes | No |
| B. Ejecutar D4/Inventario desde A1 o crear un tercer input A3 | Facilita búsqueda | Rompe responsabilidad y contrato canónico; se adelanta runtime | No |
| **C. Preclasificación conservadora dentro de A2 (solo diseño)** | Permite generar la clasificación necesaria para solicitar investigación dirigida a A3 | Debe impedir promoción indebida, falsos CURRENT y saltos de juez | **Candidato preferido sujeto a revisión independiente** |

## Contrato funcional propuesto (NO implementado)

**Entradas**: A1 resultado de fuente y semántica conservada; nueve señales tipadas derivadas de evidencia cuando existan; en ausencia de fuentes, señal tipada UNKNOWN/UNRESOLVED con referencias **de solicitud**, marcadas DECLARED_UNATTESTED. No fabricar evidencias de autoridad/currentness.

**Dos fases internas de A2, una sola skill:**

- **A2-P / preclasificación de investigación**: cuando A1 ha interpretado correctamente pero tiene ambigüedad `SOURCE_RESEARCH_REQUIRED` (categoría **conceptual**, no estado canónico nuevo), derivar un candidato `ANALYSIS_CHANGE_CLASSIFICATION_V1` usando la política existente y señales desconocidas explícitas. `L1` nunca permitido con riesgo/currentness/autoridad desconocidos; `L2` si todos los criterios de L3 son falsos y hay desconocidos; `L3` si una señal de alto riesgo satisface la política. Etiquetar siempre `NEED_MORE_EVIDENCE`, `source_attested=false`, `judge_verified=false`, `next_step=null`. El valor `target_ref` es sólo el hint aportado por A1, no identidad CURRENT.
- **A2-F / clasificación confirmable**: solo después de A3 y readback genuino, reconciliar nueve señales, fuentes, vigencias, intención y negaciones, recomputar profundidad mediante la misma política, presentar al juez Native independiente, y decidir progresión. Cualquier decisión material irresoluble con fuentes se encamina al propietario sin autoaprobación.

**A3**: continúa con sus **dos entradas canónicas**; no agregar un tercer input ni tratar un preview como contrato. Se requiere definir un gate explícito que permita *investigación* frente a dudas resolubles por fuentes, pero bloquee decisiones cuyo propietario sea indispensable. Esta política/gate es un pendiente de diseño y no está operacionalmente calificada. No ejecutar A3 al obtener solamente A2-P.

**Reglas de conservación**: vincular por SHA-256 pedido literal, candidato A1 y clasificación; preservar negocio, operación `REUSE`/ `IMPLEMENT`, restricciones con evidencia NEGATION, material_ambiguities y target_hints exactos; `UNKNOWN` no es `N/A` ni `CURRENT`.

## Matriz mínima de aceptación (pendiente de ejecución en candidato)

| Caso | Resultado funcional requerido |
|---|---|
| CORE_02: vista para entrar al portal | Entrada genérica, no forzar AUTH; ambigüedad entre navegación y autenticación; profundidad conservadora; sin A3 automático |
| CORE_04: no crear otra pantalla | `REUSE` preservado; negación completa; identidad pendiente; sin CREATE, MODIFY ni autorización |
| Contraejemplo: riesgo HIGH acreditado | Nunca degradar L3 por resolver otros UNKNOWN |
| Contraejemplo: fuente NO CURRENT | No declarar inventario resuelto ni READY |
| Solicitud sin ambigüedad y fuentes suficientes | Conservar camino de clasificación A2 existente |
| A1 inválido o pérdida de negación | `BLOCKED`, sin clasificación candidata |
| A3 encuentra evidencia contradictoria | Retornar a análisis; no declarar implícitamente RESOLVED |

## Estado y autoridad

**Propuesta de diseño pendiente de juez independiente**, no nueva arquitectura ni aprobación de cambios del contrato. Antes de editar `A2/validators/run.py` o los gates canónicos A3, se exige revisión semántica y técnica de esta decisión, pruebas negativas y de monotonicidad, y readback fuente exacta. No introducir un segundo clasificador ni un motor de inventario.

Referencias de fuente:
- `steps/a1/validators/run.py`
- `steps/a2/validators/run.py`
- `steps/a2/adapters/unresolved_research_preview_v1.py`
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_change_classification_contract_v1.json`
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_targeted_evidence_contract_v1.json`
- EKB: `PROGRAMMING-ANALYSIS-DEPTH-POLICY-UNDEFINED-001`, `PROGRAMMING-ANALYSIS-STAGE-SOURCE-ATTESTATION-GAP-001`.

**Cierre:** `DESIGN_DECISION_PROPOSED_NO_RUNTIME_EXECUTION`. PR DRAFT / NO MERGE.
