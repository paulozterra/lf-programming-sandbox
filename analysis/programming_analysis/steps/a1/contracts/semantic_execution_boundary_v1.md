# A1 — contrato de ejecución semántica (candidato)

A1 es una habilidad; el consumidor administra permisos, tickets, llamadas al modelo, juez independiente, RUN y recibos. **Este paquete no crea un modelo ni un ejecutor nuevo.**

## Etapa 1 — Preparación

Entrada: `business=LF`, `original_request` literal, `request_identity`, códigos y nombres ya transportados con sus `source_refs`, hechos y restricciones.

`semantic/semantic_boundary_v1.py:prepare` construye un paquete inmutable de referencia para el consumidor. No interpreta todavía el lenguaje natural; preserva literal y hash.

## Etapa 2 — Interpretación por modelo

El consumidor autorizará una llamada real a modelo con `prompts/semantic_interpretation_v1.md`. El productor debe devolver `A1_SEMANTIC_MODEL_RESULT_V1`:
- `objective.problem_statement` y `objective.desired_outcome` sin cambiar el alcance;
- códigos, hechos, fuentes y restricciones recibidos, sin pérdida ni invención;
- `ambiguities` y `declared_intent_kind` (no clasifica A2);
- `observed_actions[]` con `id`, `literal_span` tomado literalmente y `normalized_action`. Para el Login B2B: evaluar + implementar deben conservarse como acciones separadas.

`evaluate_model_candidate` valida procedencia, igualdad del literal y conservación de contexto. Usa el ejecutor determinista A1 y genera `REQUIRES_INDEPENDENT_SEMANTIC_REVIEW`; **no crea ticket ni llama A2**.

## Etapa 3 — Revisión por juez independiente

El juez recibirá el literal original y la interpretación, **sin depender exclusivamente de la lista de acciones que declara el productor**. Debe producir:
- hashes exactos de literal e interpretación,
- `independently_observed_actions[]` con tramos literales y significado normalizado,
- `covered_action_ids[]`, `unsupported_claims[]`, `omitted_actions[]`, `scope_expansions[]`,
- `status` y `review_ref` de su invocación.

`validate_review` comprueba estructura, hashes, completitud respecto a acciones declaradas, reconciliación de las observaciones independientes y ausencia de hallazgos materiales.

El máximo resultado **local** es `REVIEW_STRUCTURAL_PASS_ONLY` con `independence_verified=false`, `operationally_verified=false`, `next_capability=null`. Un objeto JSON autodeclarado no acredita una llamada independiente; la autoridad está fuera de A1 y deberá ser certificada por el estándar común.

## Riesgos y pendientes

- Sin proveedor semántico real conectado, `fixtures/semantic_model_candidate_fixture_v1.json` es solo un stand-in; no es un recibo de modelo.
- Ningún control determinista demuestra que el juez descubrió todas las acciones que existen en el texto original. Es una obligación de su prueba semántica independiente.
- Las referencias conservadas todavía pueden requerir currentness en A3.
- Las 34 pruebas de esta frontera usan stand-ins: 34/34 PASS sobre los mismos archivos publicados (Git blob SHA), no constituyen prueba operativa del modelo ni de independencia.
