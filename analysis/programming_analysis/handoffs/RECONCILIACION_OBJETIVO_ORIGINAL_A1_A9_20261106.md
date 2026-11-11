# PROGRAMMING_ANALYSIS_LF — Reconciliación con el objetivo original A1–A9
**Fecha de verificación:** 2026-11-06. **Naturaleza:** auditoría documental/read-only + registro candidato en PR #3624. **No habilita runtime, permisos, juez ni programación.**

## 0. Conclusión

**No hay cambio de objetivo.** La skill Análisis debe interpretar el alcance aceptado, recuperar las reglas y definiciones canónicas almacenadas (incluido historial de mejoras), contrastarlas con código real, determinar si hay DELTA y preparar en A9 un paquete **Spec-Driven utilizable sin reinterpretar el QUÉ**, o declarar NO-OP **verificado** si no hay cambio requerido de definiciones ni trabajo técnico pendiente. La documentación material faltante debe ser visible, con decisión gobernada del usuario para un subalcance independiente y seguro, no con una falsa declaración READY.

**Bloqueo principal:** el método y sus nueve contratos están escritos en main, pero la skill única solo implementa localmente A1 y A2; A3–A9 están referenciados sin entrypoints en su manifiesto. El perfil histórico A1–A9 existe **y debe reutilizarse como candidato**, no como runtime operativo ni como sustituto del flujo por pasos.

## 1. Readback de fuentes actuales y situación de las piezas

- GitHub repo: \`cristhianlujan/claude-persona-lf-patch\`; PR #3624 rama \`agent/programming-analysis-a1-a2-candidate-20261105\`, HEAD inicial de esta reconciliación \`bbce17513287ae20ad8ae5cdfdb5a8b48966e60f\`, DRAFT sin merge.
- GitHub PRs antiguos: **#2071, #2145 y #2214 CLOSED/MERGED** al verificar. Algunos README históricos los indicaban Draft en 2026-10-12: referencia cronológica obsoleta, **no** bloqueo de merge actual.
- \`analysis_procedure_v1.json\` está en main, blob \`1291336699b88df5fd11178dc9043d7ec13bc06a\`, con A1–A9, guards y límite de Programación.
- \`profiles/programming_analysis_lf/\` está en main: perfil candidato, \`SKILL.md\`, \`runtime_binding.json\`, validador \`runtime_validate.py\`, schema \`runtime_output.schema.json\`, pruebas \`test_runtime_candidate_v1.py\`. **SOURCE_ONLY / EVALUATION_ONLY**, no liberado ni aprobado por un juez independiente.
- La ficha \`profiles/programming_analysis_lf/contracts/analysis_source_binding.json\` fijó **9 blobs A1–A9**. La lectura actual de main confirma **9/9 blobs coincidentes**. Esto es Git-existencia/version-pin, NO sello de autoridad/currentness ni lectura operativa del modelo.
- \`skills/programming_analysis/contracts/analysis_skill_manifest_v1.json\` declara A1/A2 locales y A3–A9 \`CANONICAL_CONTRACT_REFERENCED_UNWIRED\`, \`module_entrypoint=null\`, \`operationally_verified=false\`.
- Supabase lectura actual de \`PROGRAMMING_ANALYSIS_LF\`: \`analysis_runs=0\`, \`skill_invocations=0\`, \`ready_catalog=0\`, \`skill_profile_authorities=0\`, \`runtime_binding=false\`. Por ello **0/9 etapas operativamente verificadas**.
- EKB consultada: \`PROGRAMMING-ANALYSIS-STAGE-SOURCE-ATTESTATION-GAP-001\` (9 receipts actuales antes de ejecución), \`PROGRAMMING-ANALYSIS-A14-EVIDENCE-TIER-FALSE-READY-001\` (juez real + PG01 readback) y \`PROFILE-JUDGE-INVARIANT-COVERAGE-001\` (gates determinísticos antes del juez, pruebas de invariantes).

### 1.1 Los 9 contratos originales (main, readback exacto)

| Etapa | Git blob exacto | Estado de conexión en la skill única | Reutilización obligatoria |
|---|---|---|---|
| A1 | \`cb6cf1c663da4dc12c1f1a6fabedb6e666836d85\` | \`steps/a1/validators/run.py\` local candidato | A1 canónico + normalizador; revisar intención semántica |
| A2 | \`0f07d3603c1bf3e4d2a4b9de5d6c3a3968bb4051\` | \`steps/a2/validators/run.py\` + Golden/human brief candidato | 9 señales tipadas, L1/L2/L3, plan de investigación, juez |
| A3 | \`97d06e88b963690202424a2936ae2b7bf597cea7\` | No existe \`steps/a3/validators/run.py\` en rama | Resolver \`SOURCE_RESOLUTION_POLICY\`, \`TYPED_DATA_ACCESS\`, EKB, CURRENTNESS, inventario AS-IS |
| A4 | \`4d38665d7f6da4e556bc05e8ed10489b62ddcc0b\` | No existe entrypoint A4 en rama | \`SHARED_CHANGE_IMPACT_ANALYSIS\` transversal y su adapter |
| A5 | \`da77f17283ced275f5498f7a5be07a7180edb7bc\` | No existe entrypoint A5 | \`DECISION_CONTEXT_ASOF\` y ADR; decisiones no inventadas |
| A6 | \`d000e6900300e12bcc1e1e56490ca3acf40713d1\` | No existe entrypoint A6 | \`IMPLEMENTABILITY_SCHEMA_V1\` + \`CANONICAL_IMPLEMENTATION_BINDINGS\` (WHAT, no HOW) |
| A7 | \`a0ef134afc07ed6fcc2385b37212d01e678f0cc6\` | No existe entrypoint A7 | \`MATERIAL_FRONT_COVERAGE_V1\`, completitud del frente material |
| A8 | \`4bb7265c985b06e23cc2428c4332187a9330fdae\` | No existe entrypoint A8 | \`ANALYSIS_STOP_RULE_V1\`, investigar solo brechas materiales |
| A9 | \`f74fc959975415f28a4ad4e02ad35671b7f4ad23\` | No existe entrypoint A9 | \`ANALYSIS_IMPLEMENTATION_PACKAGE_V1\`, \`PROGRAMMING_CONTEXT_SNAPSHOT_V1\`, validador previo, juez, exact PG-01 receipt |

**Precisión:** ausencia del path \`steps/aN/validators/run.py\` demuestra ausencia **de ese entrypoint**, no que no existan otros componentes transversales. Los validadores del perfil candidato y los contratos históricos sí existen y se reaprovecharán.

## 2. Hallazgos de interfaz y producto que no deben perderse

### P0 — Nada de la ejecución integral está acreditado
A1 estructurado y A2 Golden no prueban interpretación semántica real, fuente actual de 9 señales, juez externo, admisión \`EJECUCION_SKILL_LF\`, tránsito A2→A3 ni producción de \`A9\`. La actual salida de A2 mantiene \`a3_allowed=false\`. No proclamar READY.

### P0 — A3 es el primer gran vacío funcional
Para implementar una pantalla, A3 debe probar **por componente**, a partir de definiciones almacenadas, qué aplica y qué existe en código. Dos comparaciones diferenciadas: (1) definición almacenada CURRENT contra versión anterior/decisión aceptada y (2) definición vigente contra implementación AS-IS demostrada (hash/branch/tests/consumidores). No tomar «regla sin cambios» como «código completo». \`NO_OP\` solo cuando **ambos deltas son ninguno, con evidencia**. Si implementación es UNKNOWN, bloquear falso NO-OP.

### P1 — Reconciliar entradas A4/A5/A7, NO inventar contratos
El contrato fuente A5 enumera **4 inputs**: \`REQUEST_CONTEXT_V1\`, \`ANALYSIS_CHANGE_CLASSIFICATION_V1\`, \`TARGETED_EVIDENCE_SET_V1\`, \`SHARED_CHANGE_IMPACT_ANALYSIS\`. El manifiesto y \`analysis_procedure_v1.json\` describen sólo 3, omitiendo explícitamente la clasificación A2. Hay que verificar el transporte real y si existe alias/entrada implícita antes de asumir compatibilidad.
El contrato fuente A7 pide \`SHARED_CHANGE_IMPACT_ANALYSIS\`, \`ANALYSIS_IMPLEMENTATION_DRAFT\`, \`RISK_AND_QUALITY_SIGNALS\`, mientras que el manifiesto enumera \`SHARED_CHANGE_IMPACT_ANALYSIS\`, \`IMPLEMENTABILITY_SCHEMA_V1\`, \`ANALYSIS_DECISION_CONTEXT_V1\`. Se debe mapear transformación/adaptador existente (o bloquear) en lugar de alterar el contrato de origen.
A4 diferencia core \`SHARED_CHANGE_IMPACT_MAP_V1\` y proyección de análisis; no confundirlos. A8 usa \`DECISION_CONTEXT\` fuente; reconciliar alias exacto del output A5.

### P1 — A9 ya posee frontera de producto; NO-OP debe ser cierre de análisis
\`programming_entry_contract_v1.json\` admite Programación solamente con \`READY\` o \`PARTIAL_READY\`, según alcance, snapshot CURRENT y recibos PG-01. \`NO_OP\` no es un veredicto admitido en ese contrato. Se propone **cierre sin despacho de Programación** cuando ambos deltas estén probados cero, NO agregar unilateralmente \`NO_OP\` a la admisión de PG-01. Las alertas con subalcance aprobado conservan \`PARTIAL_READY\` solo si los scopes READY son independientes y compatibles.

### P1 — No reinterpretar la petición como nueva definición
En la implementación de \`B2B-AUTH-001\` ya existe inventario candidato (pantalla v0.5, 71 reglas, 13 links de políticas, 17 elementos, 3 variantes, 8 artefactos visuales, etc.). A3 debe reusar inventario y profundizar en elementos materiales. No reescribir políticas vigentes sin delta y autorización. Los estados de la pantalla no demuestran código funcionando.

## 3. Ruta mínima para terminar el objetivo original — no crear plataforma paralela

| Lote | Acción sobre infraestructura existente | Criterio verificable |
|---|---|---|
| **L1 — Continuidad real A1→A2** | Reusar Router→perfil→\`EJECUCION_SKILL_LF\`. Atestar fuentes exactas y 9 señales, productor semántico + juez independiente con 0 falsos permisos. Integrar Golden y brief sin alterar clasificación canónica. | RUN/receipts reales + judge; A3 solo se habilita tras PASS. |
| **L2 — A3 inventario AS-IS y DELTA** | Consumir contratos A3 y resolutores CURRENT existentes. Extraer inventario de definiciones, versiones, decisiones y trazabilidad; contrastar código/CI. Identificar reutilización, creación, cambio y alertas por scope. | \`TARGETED_EVIDENCE_SET_V1\` con refs actuales, gaps, delta definido vs implementado, y negativos. |
| **L3 — Adaptar A4–A8 existentes** | Conectar impacto transversal, decisiones/ADR, obligaciones A6, frentes A7 y STOP A8. Resolver diferencias A5/A7 de inputs sin duplicar contratos. | 5 salidas tipadas verificadas, tests positivos/negativos, decisión material correcta por scope. |
| **L4 — A9 y destino Spec-Driven** | Ensamblar desde outputs de A1–A8 y reusar validadores del perfil antiguo y \`validate_programming_snapshot_payload_v1\`. Caso NO-OP probado cierra sin Programación. Caso DELTA real genera full snapshot / parcial seguro con alertas y decisión de propietario. Juez y PG-01 readback exacto. | \`ANALYSIS_IMPLEMENTATION_PACKAGE_V1\` utilizable, \`PROGRAMMING_CONTEXT_SNAPSHOT_V1\`, fingerprints y recibo consumidor o NO-OP probado. |
| **L5 — Calificación A10–A15** | Evaluación E2E, casos adversariales y holdout vinculados al source manifest exacto. | Gates operacionales independientes; jamás inferir de fixtures históricos. |

### Condición de salida de la skill

- **Cierre sin modificación:** definiciones reconciliadas actuales + implementación conforme + sin deltas materiales, con hashes y decisión estable.
- **Spec-Driven:** definiciones almacenadas CURRENT y alcance aceptado; inventario y AS-IS, delta preciso, contratos, dependencias, aceptación, alerts/exclusiones, calidad de fuentes. Sin elegir HOW técnico; lo hace el programador.
- **Pendiente de usuario:** brecha real material, sin autoinferir aprobación. Aceptar un subalcance seguro requiere receipt exacto y no suprime bloqueos obligatorios.
- **Bloqueado:** fuente no almacenada/autoritativa, evidencia técnica desconocida material, riesgo obligatorio irresuelto, falso READY o consumidor PG-01 sin paridad.

## 4. Evidencia y límites de esta reconciliación

- **Evidencia POSITIVA:** 9/9 contratos presentes y SHA coincidentes; A1/A2 candidatos; perfil anterior en main; merges históricos confirmados; verificación Supabase 0 RUN.
- **Evidencia NEGATIVA:** \`module_entrypoint=null\` y paths faltantes A3–A9 en rama; admisión skill no habilitada y ninguna invocación registrada.
- **No se ha probado:** genuino LLM A1–A9, juicio semántico externo, uso de adapters CURRENT, ejecución real A3, igualdad con código de la pantalla B2B, CI E2E del agente, PG-01 readback.
- **El avance 9/9 contratos no es 9/9 funcional:** 2/9 etapas tienen código candidato local, 7/9 carecen de entrypoint; 0/9 acreditadas operacionalmente.
- **No modificar en este lote:** Main, Router, Supabase, EKB, fuentes de producto, perfiles operativos, Edge #3681, juez oficial, merges ni producción. El entregable de esta fase es SOLO reconciliación verificable y siguiente lote elegible L1.

## 5. Decisión final de reconciliación

\`OBJECTIVE_UNCHANGED\` · \`REUSE_EXISTING_PROCEDURE_AND_PROFILE\` · \`NO_PARALLEL_RUNTIME\` · \`CURRENT_READINESS=BLOCKED\` · \`NEXT=L1_A1_A2_SOURCE_AND_JUDGE_GATE\`.

**Próxima ejecución recomendada:** cerrar L1 con EKB primero, producer/independent-judge y readback real; luego A3. No seguir ampliando los 59 controles o el catálogo de skills sin una brecha material demostrada.
