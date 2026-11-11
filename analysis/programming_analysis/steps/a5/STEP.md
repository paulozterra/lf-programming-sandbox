# A5 — Resolver decisiones y ADR sobre evidencia A1–A4

**Estado:** desarrollo candidato local sin RUN gobernado, decisión humana, escritura ASOF ni autorización A6.

## Entradas deterministas

Cuatro contratos existentes: `REQUEST_CONTEXT_V1` (A1), `ANALYSIS_CHANGE_CLASSIFICATION_V1` (A2), `TARGETED_EVIDENCE_SET_V1` (A3) y `SHARED_CHANGE_IMPACT_ANALYSIS` (A4). El sidecar opcional `A5_GOVERNED_DECISION_READBACK_V1` contiene una revisión tipada de siete disparadores de ADR, vinculada a una referencia exacta previamente emitida por A3/A4.

Reutiliza solo los proveedores canónicos existentes:
- `transversal.decision_log` y `programacion.fn_engineering_current_adr_assert_v1(p_adr)` para verificar vigencia de un ADR identificado; A5 no inventa ni busca ADR.
- `public.fn_lf_decision_context_asof_resolve_v1(consumer_code,subject_ref,as_of)` para contexto histórico, que **nunca** equivale a autoridad actual.
- `DECISION_CONTEXT_ASOF` / `public.fn_lf_decision_context_asof_record_v1` para persistencia gobernada fuera de este consumidor; A5 no escribe.
- `CURRENTNESS_AUTHORITY` para la certificación del host; el candidato no se autoconcede currentness.

## Decisión ADR

| Condición sustentada | Disposición | Comportamiento |
|---|---|---|
| Siete disparadores revisados, todos falsos | `NOT_REQUIRED` | No genera ADR humano; HOW local reservado a PG-03 |
| Disparador verdadero + ADR exacto vigente (assert PASS) | `REUSE_CURRENT_ADR` | Reutiliza referencia del ADR sin modificarlo |
| Disparador verdadero + ausencia de ADR vigente acreditada por fuente | `NEW_ADR_REQUIRED` | `REQUIRES_DECISION`; A5 no aprueba un ADR |
| Disparador desconocido, readback incompleto o no hay prueba de ADR | `ADR_BLOCKED` | `UNRESOLVED` o `BLOCKED`, sin inventar una decisión |

Las reglas CANDIDATO/PENDIENTE excluidas en A3 no abren una decisión humana ni impiden trabajar sobre reglas independientes. Los gaps de dependencias A4 se muestran como requerimiento de evidencia, no como aprobación/denegación ejecutiva.

## Salida

`ANALYSIS_DECISION_CONTEXT_V1` con `decision_context` completo: `decision_id`, `subject_ref`, `scope_refs`, `material_question`, `status`, `options_considered`, `selected_option_ref`, `rationale`, `authority_refs`, `evidence_refs`, `currentness_refs`, `unresolved_questions`, `adr_disposition`, `adr_ref`, `persistence_ref` y `decision_fingerprint_sha256`. Fingerprint SHA256 calculado de JSON canónico, excluyendo la huella misma.

El paso **no selecciona estrategias técnicas ni opciones no elegidas por owner**, no convierte la intención A2 en autorización y no afirma `STABLE` sin fuente decisional vigente verificada. En este consumidor fuente los resultados son candidatos; `source_attested=false`, `independent_judge_verified=false`, `a6_allowed=false`, `no_write_performed=true`.

## Salida granular por elemento — corrección

Además del `decision_context` canónico y el motor ADR existente, A5 emite `material_ledger`, `decision_items[]`, `pending_evidence_items[]`, `pending_owner_decisions[]`, `architecture_decision_items[]`, `material_coverage` y `scope_disposition`. Contrato aditivo: `contracts/a5_material_decision_output_v1.json`.

**Lectura sin pérdida:** recopila individualmente las listas A3 (reglas aprobadas, diferidas, excluidas, herencia en evidencia, políticas), A4 (impactos directos/indirectos, consumidores, rutas, exclusiones, brechas) y elementos materiales; conserva cada payload exacto, título, descripción, referencia, acción, estado y SHA-256. `material_ledger.upstream_contract_snapshot` conserva además los contratos A3/A4 **completos** y detecta cualquier colección no suministrada (ausente ≠ vacía).

**Distinción decisional:** `IMPLEMENTATION_OBLIGATION` → no exige decisión humana nueva; `EXCLUDED_PENDING` → excluido, sin bloquear el alcance independiente; `EVIDENCE_REQUIRED` → solicitud focalizada de lectura, no escalación humana; decisiones humanas solo con pregunta, owner y referencia de elemento material explícitos en el readback. El objetivo nuevo no necesita código o destino.

**ADR:** sus siete disparadores siguen siendo el contrato existente. Si requiere nuevo ADR pero no existe una pregunta material sustentada, `architecture_decision_items[].material_question=null` y `semantic_review_needed=true`; nunca inventar una pregunta ni autoadjudicar.

**Continuidad:** `candidate_independent_scope_available` señala material independiente para futura especificación, pero NO es `a6_allowed`. A5 preserva `a6_allowed=false` y `source_attested=false` hasta que el host gobernado acredite fuentes, autoridad y lectura de juez independiente.

**Jueces reutilizados y ampliados:** `judges/material_parity_v1.py` verifica mecánicamente cobertura 1:1, payloads, duplicados, actuales pendientes y falsa autorización. `judges/semantic_review_packet_v1.py` crea paquetes por lotes con la rúbrica semántica de la familia A5Q existente, sin imponer el mínimo de cinco decisiones humanas del caso histórico. NO ejecuta modelos: `independent_semantic_review=false` hasta recibo externo real.

**Evals:** casos sintéticos complejos con reglas, definiciones, políticas, dependencias y adversariales. No sustituyen una ejecución real A3→A5 ni la revisión semántica independiente.

**Vista humana íntegra:** `evals/render_a5_material_human_v1.py` publica en GitHub Actions un ejemplo de Inicio de sesión B2B sintético, con cada elemento, todos sus campos originales y ambos contratos upstream completos. No es evidencia operativa LF.
## Ficha única por regla — Frontend / Backend / Compartida

`adapters/rule_layer_consolidation_v1.py` consolida por `rule_code + source_ref` exactos; no duplica por ocurrencias A3 `policy_scope_clear_rule_candidates`, `policy_deferred_rule_items`, `excluded_rule_items`, `evidence_items` ni por impactos A4. Conserva título, descripción, estado, `association_ref` y `binding_source` de herencia (nunca infiere GLOBAL a partir de `es_transversal`), referencias y contenidos de políticas **solo por `policy_resolution.rule_policy_dependencies[rule_code]`**, impactos A4 con vínculo exacto, y cada `material_item_id`.

Para cada regla se emite `rule_profiles.rules[]` con `layers.FRONTEND` y `layers.BACKEND`. Cada capa tiene `applicability` (`APPLIES`, `NOT_APPLICABLE`, `UNKNOWN`), responsabilidad concreta **solo cuando está suministrada**, evidencia y estado de verificación. La clasificación derivada es `SHARED_CANDIDATE`, `FRONTEND_ONLY_CANDIDATE`, `BACKEND_ONLY_CANDIDATE`, `NO_APPLICABLE_LAYER_CANDIDATE` o `UNKNOWN`.

**Fuente real verificada:** `lf_ops.reglas` no tiene campo Front/Back específico; `programacion.fn_input_effective_rule_links_v1` devuelve vínculo efectivo con `binding_source`, pero tampoco demuestra responsabilidad por capa. En ausencia de readback de capa vinculado a regla, **ambas capas son UNKNOWN**; está prohibido inferir la capa por título, contexto visual, `es_transversal`, nombre o tecnología. Una sola afirmación positiva **no** permite declarar `FRONTEND_ONLY/BACKEND_ONLY`: la otra debe estar explícitamente marcada `NOT_APPLICABLE`.

El sidecar autorizado `A5_GOVERNED_DECISION_READBACK_V1.rule_layer_bindings[]` es **opcional** y tipado: `rule_code`, `rule_source_ref`, `layer`, `applicability`, `responsibility`, `evidence_ref`, `source_attested=false`. Los vínculos exigen identidad exacta y `evidence_ref == rule_source_ref` dentro de A3; duplicados, referencias falsas y responsabilidades vacías para `APPLIES` bloquean. **Incluso los readbacks plausibles permanecen SOURCE_CANDIDATE_UNATTESTED** hasta acreditación del host y revisión semántica independiente. No se consulta libremente un repositorio ni se crea un resolvedor paralelo.

Reglas excluidas incompletas sin referencia mantienen `unresolved_rule_identities[]`, no entran al alcance de implementación ni bloquean por sí solas el resto aprobado. Una regla vigente sin referencia canónica sí bloquea la ficha. Objetivo nuevo: `code_destination=null` válido.

Pruebas: `evals/test_a5_rule_layer_consolidation_v1.py` y `evals/test_a5_rule_layer_judge_v1.py`. Juez mecánico adicional: `judges/rule_layer_parity_v1.py`. Rúbrica semántica ampliada para roles Front/Back y ninguna inferencia por nombre, pero **veredicto independiente no emitido**. La vista humana íntegra exporta también todas las fichas y sus datos originales.
## Control de calidad

Tests: `steps/a5/evals/test_a5_decision_adr_v1.py` (suite de pruebas A5 ampliada, ver CI exact-HEAD). CI: `.github/workflows/lf-analysis-a5-candidate-tests.yml`, exact-HEAD, sin secretos. No afirmar PASS de nuevo HEAD sin logs.

**Separación:** la implementación candidata A5 no exige cerrar antes PASE de A3/A4, pero tampoco constituye admisión operativa, READY o autorización de ejecución de A6.
