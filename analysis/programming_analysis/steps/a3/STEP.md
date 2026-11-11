# A3 · Contexto actual mínimo del objetivo

**Estado:** desarrollo fuente A3 implementado en PR #3624; validación runtime, juez independiente y admisión A4 pendientes. **No** equivale a skill en producción.

## Entrada (no modificar A1/A2)
- Dos contratos existentes y exactos: `REQUEST_CONTEXT_V1` + `ANALYSIS_CHANGE_CLASSIFICATION_V1`.
- Sidecar no confiable de lectura autorizada: `LF_SCREEN_SOURCE_READBACK_V1` para business LF, artefacto SCREEN.
- Ruta única: `steps/a3/validators/run.py:run`. Ningún Router, RPC, SQL o modelo nuevo dentro del paso.

## Fuentes preexistentes que debe leer el host
1. `lf_ops.fn_screen_contract_v1` por código exacto de shell/módulo/pantalla; datos de pantalla y secciones `context,metadata,fields,errors,visual,profiles,analytics,evidence`. El host puede pasar estas 8 secciones como `resolved_sources.contract_sections`, sin copiarlas a otro repositorio.
2. `programacion.fn_input_effective_rule_links_v1(pantalla_id,'INPUT_GOVERNANCE')`; reconciliar `LEGACY_EXPLICIT`, `DECLARATIVE_APPLICABILITY_V1` y `DERIVED_GLOBAL` con el inventario directo.
3. Vínculos `lf_ops.pantallas_politicas`, parámetros `lf_ops.reglas.valor_config`, políticas tipadas `lf_ops.politicas_*` y readback de `contract.policies`; ninguna igualdad numérica concede autoridad.
4. GitHub AS-IS con SHA exacto, contrato lógico y binding físico, **si hay evidencia**. Falta de evidencia => UNKNOWN, no NEW.

## Salida fuente A3
`TARGETED_EVIDENCE_SET_V1` preserva:
- `evidence_items`, `excluded_rule_items`, `policy_scope_clear_rule_candidates`, `policy_deferred_rule_items`;
- `inheritance_readback`, `policy_resolution`, `policy_link_items`;
- `material_contract_readback` con las 8 secciones, cada status rastreable al JSON pointer del contrato y `implementation_approved=false`;
- `as_is_baseline_or_new_implementation_evidence`, `authority_state`, `implementation_state`, `currentness_refs`, `unresolved_material_gaps` y conteos.

Reglas `VIGENTE` sin decisiones pendientes son **candidatas de alcance**; candidatas, suspendidas o con política sin vínculo vigente se separan y generan alertas, no bloquean reglas independientes. Pueden existir estados `CANDIDATO_VISUAL` y otros estados sin aprobación; no se elevan a `VIGENTE`.

Si `contract_sections` falta, A3 mantiene la clasificación parcial pero registra `CONSOLIDATED_SCREEN_MATERIAL_READBACK_MISSING`. Si se entrega incompleta o mal tipada, **BLOCKED** para evitar falsa completitud.

## Límite de autoridad
Esta implementación no autentica las lecturas: `source_attested=false`, `runtime_qualified=false`, `independent_judge_verified=false`, `a4_allowed=false`. El host gobernado debe verificar versión, SHA, enlaces, identidad y juez **separadamente**. No se invoca A4 desde el módulo.

## Control de desarrollo
- Código: `adapters/policy_readback_v1.py`, `adapters/as_is_projection_v1.py`, `validators/run.py`.
- Pruebas nuevas: `evals/test_a3_development_scope_v1.py` (6 verificaciones); pruebas previas de política: 12/12 en paquete local de referencia, **no** recibo runtime de este HEAD.
- No se alteran A1/A2. El ejemplo B2B-AUTH-001 prueba el contrato genérico, no constituye hardcoding del consumidor.
- Próximo paso de **desarrollo**, cuando corresponda: A4 `CALCULATE_CHANGE_IMPACT`, consumiendo el contrato A3; certificación/admisión operativa de A3 se tramita en paralelo como deuda separada, nunca se infiere automáticamente.
