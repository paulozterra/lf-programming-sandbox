# A2 — Clasificación interna de cambio, alcance y profundidad

**Estado:** `LOCAL_DETERMINISTIC_CANDIDATE_UNQUALIFIED`. Paso **interno** de la skill `PROGRAMMING_ANALYSIS_LF`. No existe una segunda skill A2.

## Ajuste de intención humana (candidato source-only, 2026-11-06)

**Motivo:** un listado de 59 controles no explica por sí solo qué quiso decir el usuario ni permite decidir correctamente qué hay que investigar. No equivale a un documento preparado para implementar.

- Entrada: A1 (problema y resultado literal, negocio, target, restricciones y ambigüedades) + clasificación A2 + Golden v0.3 ya validado estructuralmente.
- `adapters/intent_brief_v1.py::build_brief` genera un documento humano preliminar, sin inventar la solución: intención declarada, resultado pedido, restricciones, dudas, preguntas candidatas al usuario y tareas separadas de investigación de A3.
- El adaptador `adapters/a2_a3_intake_preview_v1.py::prepare_preview` añade `human_intent_brief` como **anexo no canónico**, vinculado por digest al A1, la clasificación y el Golden. Los **dos inputs canónicos** de A3 permanecen iguales.
- Los 59 elementos Golden son checklist de control interno; los 33 obligatorios pendientes no desaparecen por el hecho de que las 26 preguntas de condicionales existan.
- `ambiguities=[]` significa que A1 no registró ambigüedad, **no** que el usuario haya sido entendido de manera inequívoca. No debe afirmarse que un objetivo genérico es suficientemente específico sin juicio semántico independiente.
- Las preguntas al dueño tienen estado `SUGGESTED_NOT_SENT_NEEDS_SEMANTIC_REVIEW`. El productor local NO las envía, NO acredita fuente CURRENT, NO realiza juicio semántico, NO habilita RUN/A3 y NO propone programación.
- **Corrección de diseño A2 (2026-11-07):** A1 ya transporta problema y resultado deseado. El brief **no genera automáticamente** una pregunta general al propietario para reconfirmar ambos. Produce una evaluación `CHECK_OBSERVABLE_OUTCOME` pendiente de juicio semántico. Ante ambigüedad material, la pregunta al propietario es solo candidata con ruta `A3_RESEARCH_FIRST_THEN_OWNER_IF_MATERIAL_UNRESOLVED`: investigar definiciones y evolución existentes primero; escalar únicamente si queda una decisión verdaderamente del propietario. Nunca sustituir el juicio por heurísticas de keywords, fabricar fuentes CURRENT, habilitar A3 ni añadir nuevos estados canónicos.
- `test_intent_brief_v1.py` contiene 20 pruebas nuevas, además de regresión completa del candidato. No usar PASS de fixture como calificación de operaciones reales.
- Para completar la corrección: incorporar productor semántico autorizado y juez independiente; distinguir pregunta material que necesita dueño de búsqueda que A3 puede resolver por fuentes; comprobar éxito observable antes de entregar análisis implementable.

## Hito H1 — Productor Golden 12/59 (candidato source-only)

- Catálogo exacto: `catalog/A2_GOLDEN_CATALOGO_DIMENSIONAL_v0_2.json` (12 dimensiones, 59 elementos, 26 activaciones).
- `adapters/golden_dimensions_v1.py::build_golden` prepara dos ejes de evaluación y evidencia declarada; `adapters/golden_handoff_v03.py::prepare_golden_v03` emite el **formato Golden propuesto v0.3**, validado con `schemas/A2_GOLDEN_CONTRATO_SALIDA_PROPUESTA_v0_3.schema.json`.
- La clasificación `ANALYSIS_CHANGE_CLASSIFICATION_V1` de `validators/run.py` sigue **sin modificación**, y A3 conserva sus dos inputs canónicos. Golden es un anexo de investigación y no puede sustituir ese contrato.
- Pruebas locales `test_golden_dimensions_v1.py` + `test_golden_handoff_v03.py`: 41/41 PASS sobre fuente idéntica al commit. Incluye 26 casos positivos por activación; no prueba actuales recibos ni juez.
- **No integrado operacionalmente**: `a3_allowed=false`, `D12-E05=PENDING_EVIDENCE`. Toda condición no probada queda `UNRESOLVED_TRIGGER`, nunca N/A. H2/H3/H4 y admisión gobernada siguen pendientes.
- Evidencia y seis hashes exactos: `handoffs/H1_GOLDEN_PRODUCER_SOURCE_CANDIDATE_20261106.md`.

## Regla Spec-Driven y delta nulo (propuesta documental 2026-11-06)

A2 prepara el **plan de comparación** de fuentes almacenadas y evidencias para A3. No presupone que implementar exige cambiar reglas ni que no tener reglas nuevas equivale a no tener trabajo de código. Exige: negocio/alcance autorizado, identidad y versión de las definiciones, mejoras históricas, inventario completo de familias materiales y divergencia por componente entre AS-IS y requisito. No clasifica NO-OP por sí solo: A3 debe acreditar definiciones CURRENT y código; A4–A9 deciden impacto y construyen Spec-Driven o cierre sin cambios. Ante documentación material ausente: alerta y decisión de alcance, sin declarar READY por consentimiento que pretenda omitir seguridad/autoridad. Fuentes de diseño: `handoffs/SPEC_DRIVEN_DELTA_DOCUMENTACION_GATE_CANDIDATE_20261106.md` y `handoffs/SPEC_DRIVEN_DELTA_DECISION_MATRIX_CANDIDATE_20261106.json` (relativas al paquete skill, no a este subdirectorio).

## Interfaz pendiente de diseño A1 → A2 (P0, sin cambio de contrato)
- **Readback de código 2026-11-07:** A1 devuelve `REQUIRES_DECISION` cuando hay ambigüedad material abierta (casos CORE 02/04). `steps/a2/validators/run.py` exige A1 `VALID_OUTPUT` y `next_capability=A2`. Por tanto, **no está demostrada la continuidad de esos dos casos a la investigación de A3**, aunque la semántica A1 haya pasado.
- No interpretar `REQUIRES_DECISION` como obligación automática de volver a preguntarle al propietario: distinguir `REQUIRES_SOURCE_RESEARCH` conceptual (resoluble por definiciones existentes) de `OWNER_DECISION_REQUIRED` conceptual (decisión verdaderamente no resoluble desde fuentes). **No se añaden estados canónicos ni se llama D4** en este lote.
- **Lote de diseño A2 (2026-11-07):** el componente aislado `adapters/unresolved_research_preview_v1.py::prepare` genera `A2_UNRESOLVED_RESEARCH_PREVIEW_CANDIDATE_V1` exclusivamente cuando A1 mantiene `REQUIRES_DECISION` con ambigüedad MATERIAL/UNKNOWN abierta y un candidato de intención enlazado por SHA-256. El puente A1→A2 incorpora `a2_research_preview` sin cambiar `status=HALTED_AT_A1`. Conserva objetivo, negocio, operación, artefacto, pistas, restricciones, negaciones y dudas; orienta a resolver identidad, autoridad, implementación y dependencias existentes antes de escalar decisiones verdaderas al propietario.
- **Límites de la vista preliminar:** `a2_classification=null`, `a3_canonical_inputs=null`, `a2_depth_classified=false`, `a3_dispatch_allowed=false`, `independent_judge_attested=false`; no reinterpreta `REQUIRES_DECISION` como `VALID_OUTPUT`, no llama D4 ni A3, ni altera esquemas canónicos. La fuente `user://` no se convierte en evidencia CURRENT. Probar un plan no es cerrar A2.
- **Prueba local aislada:** `evals/test_unresolved_research_preview_v1.py` 15/15 PASS en Python sobre blobs exactos de módulo y tests. Los tests de enlace adicionados a `steps/a1/evals/test_a1_semantic_candidate_v1.py` están definidos pero **aún no ejecutados** en runner del repositorio. El recorrido completo y el juicio semántico Native independiente continúan pendientes.
- **P0 de diseño aún abierto:** obtener evidencias reales de A3 y reconciliar ambigüedades sin quebrar la entrada de **dos contratos canónicos** de A3 (`REQUEST_CONTEXT_V1` + `ANALYSIS_CHANGE_CLASSIFICATION_V1`). No enviar la vista preliminar como una tercera entrada ni permitir invocación A3 hasta clasificar con señales tipadas y autoridad comprobada.
- Los archivos A1→D4/SQL del PR #3624 son **candidatos adelantados fuera del lote de diseño A2**; no son dependencia de aceptación de este paso, ni se deben integrar/activar por obtener PASS en A2.

## Lote de endurecimiento y decisión P0 de ciclo (2026-11-07, diseño sin runtime)

- **Defecto detectado:** antes de este lote, `unresolved_research_preview_v1.py` validaba cada restricción presente en `payload.constraints` contra el texto, pero no verificaba la **igualdad completa** con `intent_analysis.explicit_constraints[]`. Era posible borrar `No crees otra pantalla` del payload conservando el texto original y el hash de `intent_analysis`, y producir un plan sin la prohibición.
- **Corregido en fuente candidata:** ahora exige igualdad completa del resultado deseado frente a `intent_analysis.desired_outcome`, restricciones declaradas frente a `explicit_constraints`, target_hints frente a la primera mención y ambigüedades tipadas; tipos anidados inválidos bloquean sin excepción no controlada.
- **Pruebas:** `evals/test_unresolved_research_preview_v1.py` pasa de **15 a 22** métodos definidos (siete negativos nuevos). El anterior 15/15 era de una versión **anterior** y NO califica esta fuente actual. Ejecución Python exact-HEAD y suite A1/A2 completa: **PENDIENTE**. No confundir PASE con ejecución de unittest.
- **P0 abierto y documentado:** A1 `REQUIRES_DECISION` no es admitido por el A2 canónico; A3 pide dos contratos, incluido el A2 canónico. El preview conserva datos pero no resuelve el ciclo. El documento `handoffs/A2_SOURCE_RESEARCH_CYCLE_DECISION_CANDIDATE_20261107.md` compara alternativas y propone evaluación de preclasificación conservadora `NEED_MORE_EVIDENCE` para investigación dirigida, sin inventar vigencia ni autorizar A3. **Propuesta, no implementada ni aprobada**.
- Paquete de revisión independiente congelado: `evals/a2_preclassification_research_independent_review_packet_20261107.json`, con seis casos y referencias Git blob SHA-1. El revisor debe distinguir defectos del código fuente vs decisiones arquitectónicas; sin atestación Native no hay cierre de A2.
- Reproducción solicitada al runner local autorizado, sin tocar Router/D4/SQL: `python -m unittest discover -s skills/programming_analysis/steps/a1/evals -p 'test_a1_semantic_candidate_v1.py' -v` y `python -m unittest discover -s skills/programming_analysis/steps/a2/evals -p 'test_*.py' -v` (requiere `jsonschema`). Conservar stdout, exit code, HEAD, hashes y fallos antes de cierre.

## Entrada
- `a1_result` válido y tipado, `status=VALID_OUTPUT`, `REQUEST_CONTEXT_V1`, `interpretation_state=PRESTRUCTURED_UNATTESTED`.
- `signal_bundle` recibido del consumidor: referencia exacta a un target aportado en A1, tipo/granularidad explícitos, refs de evidencia y señales tipadas, **sin afirmar que ya están autenticadas**.
- Candidatos semánticos de texto libre: **bloquear hasta productor real, revisor independiente y recibos**, sin aceptar autorreporte de juez dentro del bundle.

## Proceso
1. Verificar el sobre completo de A1 y validar su payload contra el esquema canónico actual.
2. Validar el destino sin inferirlo de palabras clave. Objetivos anidados SECTION/CONTROL requieren `nested_parent_ref`.
3. Leer `analysis_change_classification_contract_v1.json` y aplicar **directamente sus expresiones** `L3_if_any`, `L2_if_no_L3_and_any`, `L1_requires_all` a las señales tipadas. Sin pesos, heurística libre ni familia de caso.
4. Entregar `ANALYSIS_CHANGE_CLASSIFICATION_V1` como **candidato**, con nivel L1/L2/L3 y predicados justificativos. No generar identidad de especialistas: CAPABILITY_SELECTOR y sus manifiestos RELEASED siguen siendo autoridad externa.
5. Emitir clasificación candidata, brechas explícitas e instrucciones dirigidas para A3. A3 espera a que A2 termine y pase la evaluación del juez existente por ruta nativa; A2 no espera la investigación de A3. En este módulo source-only `next_step=null` hasta readback gobernado del gate.

## Bloqueos
No admitir A1 con revisión semántica pendiente, source refs vacías, señales inválidas, target inventado, falta de padre en target anidado, drift de política o inferencia de permisos. L1 requiere todos los criterios; materialidad desconocida nunca puede dar L1. No se altera Router, Supabase, EKB ni catálogo de skills.

Pruebas locales sintéticas: `python -m unittest discover -s skills/programming_analysis/steps/a2/evals -p 'test_*.py' -v`. Estas no prueban runtime ni independencia de juez.

## Identidad obligatoria del negocio y ficha de investigación (requisito pre-admisión)
- **Negocio:** A2 debe transportar sin modificación `a1_result.business` (declarado y tipado por A1) para todo el resultado y el handoff A2→A3. Nulo/vacío, conflicto con la identidad del RUN o cambio de negocio sin fuente y autoridad ⇒ bloquear el handoff, nunca asumir LF/SALY por el nombre de una pantalla.
- **Producto, módulo y target:** registrar los valores si A1 los proporcionó de forma verificable mediante `REQUEST_CONTEXT_V1.provided_facts[]`, `target_hints[]` y `source_refs[]`; anotar `DECLARED` vs `CURRENT_VERIFIED`, sin derivar identidad canónica de una coincidencia textual. Si faltan, el estado es `UNKNOWN` y A3 recibe preguntas dirigidas. No fabricar códigos ni nombres.
- **Especificaciones para A3:** A2 detalla finalidad funcional, alcance incluido/excluido, restricciones, señales de clasificación, escenarios de riesgo **hipotéticos**, hechos conocidos con referencia, pistas de fuentes y las consultas exactas (identidad canónica, políticas, versiones, parámetros, implementación, API/UI y consumidores). A2 **no** hace la investigación de A3 ni declara CURRENT.
- **Responsabilidad de A3:** usar `REQUEST_CONTEXT_V1` + `ANALYSIS_CHANGE_CLASSIFICATION_V1` y el contexto de negocio retenido para resolver identidad y autoridad CURRENT, confirmar la implementación y completar parámetros y dependencias con evidencia; no pasar a otro negocio salvo dependencia acreditada por fuente y alcance.
- **Juez existente:** rechazar un A2 que omita negocio, cambie de negocio, presente una especificación no sustentada como vigente o traslade a A3 una tarea propia de clasificación. La ausencia de evidencia que A3 está encargado de obtener **no es FAIL automático de A2** si quedó clasificada y dirigida correctamente.
- **Implementado solo en rama candidata:** `schemas/input.schema.json` exige `business`; `schemas/output.schema.json` exige `business` en respuestas no bloqueadas; `validators/run.py` comprueba igualdad exacta contra `a1_result.business` y rechaza hechos de identidad contradictorios. `adapters/a2_a3_business_handoff_v1.py` crea una ficha con negocio, producto/módulo solo si figuran en hechos fuente, objetivo, restricciones, preguntas para A3, y sus **dos inputs canónicos**. El puente `adapters/a1_a2_candidate_bridge_v1.py` acepta `expected_business` del consumidor. Ausente ⇒ handoff bloqueado; nunca inferir identidad desde A1 para sustituir la autoridad del consumidor. Los tests del mismo paquete cubren LF→SALY, ausentes y hechos contradictorios. Nombre y código de un mismo producto o módulo pueden coexistir si tienen referencias válidas; se rechazan conflictos dentro de la misma clave y se conserva la totalidad de hechos declarados.
- **Límite:** el guard siempre devuelve `a3_allowed=false`, `judge_verified=false`, `next_step=null`. Son validaciones estructurales locales, no readback del RUN ni autorización de juez/skill. `expected_business` aportado por el consumidor requiere fuente gobernada y validación externa en runtime. No se modificó el contrato canónico `ANALYSIS_CHANGE_CLASSIFICATION_V1` ni `REQUEST_CONTEXT_V1`.


## Vinculación a RUN gobernado (guard candidato, no autenticación)

- La identidad no puede proceder solo de `expected_business`: ahora el puente `adapters/a1_a2_candidate_bridge_v1.py` requiere una conciliación coherente del RUN de perfil, `lf_skill_invocation_v1` y RUN hijo `EJECUCION_SKILL_LF`. `expected_business` sirve exclusivamente como veto. Sin `run_readback` o sin `actor_parent_execution_id`, bloquea.
- **Ruta A2→A3 vigente en rama candidata:** el puente `adapters/a1_a2_candidate_bridge_v1.py` usa `adapters/native_pending_run_binding_v1.py::verify_pending`: exige invocación `IN_PROGRESS`, RUN hijo `EJECUCION_SKILL_LF`, negocio y `request_sha256` vinculados al perfil, fuente tipada y `init_execution`/0 limpio. No acepta `COMPLETED` prematuro, negocio cruzado ni paso 0 omitido. El guard previo `adapters/run_business_binding_v1.py::reconcile` queda como referencia histórica de cierre y **no** es invocado por el puente A2 actual.
- **Límite obligatorio:** incluso si `verify_pending` devuelve `CANDIDATE_PENDING_RUN_CONSISTENT`, conserva `readback_authenticated=false`, `native_judge_verified=false`, `a3_allowed=false`; el puente mantiene `runtime_qualified=false` y `next_step=null`. El host autorizado todavía debe consultar la BD directamente, validar actor y fuente CURRENT, y acreditar al juez independiente por el mismo RUN. La consistencia de JSON suministrado no es autenticación.
- El informe y consulta SELECT de referencia están en `handoffs/RUN_BUSINESS_BINDING_CANDIDATE_20261106.md`. Las 30 pruebas locales se limitan a consistencia, bloqueo y puente con otras unidades simuladas; no acreditan RPC, juez o admisión.
- **Brecha de arquitectura confirmada:** `lf_skill_invoke_v1` solo crea `child_execution_id` para `effect=WRITE_GOVERNED`. Esta skill es candidata `READ_ONLY`; no cambiar su efecto ni usar funciones paralelas para producir artificialmente un RUN hijo. La resolución de la apertura real de `EJECUCION_SKILL_LF` permanece P0 pre-admisión.

## Patrón verificado de EJECUCION_PERFIL_LF (reutilización, no activado)

- Referencia: `handoffs/PARIDAD_EJECUCION_PERFIL_A_EJECUCION_SKILL_20261106.md`.
- `lf_profile_execution_begin_from_handoff_v1` valida la autoridad; `lf_profile_execution_begin_v1` reserva mediante `fn_lf_operation_reserve_execution_v1` y registra `init_execution`/0. El mismo patrón debe adaptar `EJECUCION_SKILL_LF` sin nueva operación.
- `lf_record_profile_execution_step_v1` es un wrapper mínimo que obtiene trust desde `lf_profile_execution_trust_validation_v2` y delega a `lf_record_operation_step_core_v1`. Para skill, usar el **núcleo común** con validación propia de negocio, identidad, fuente, juez y 9 pasos; no reusar trust del perfil por nombre ni `lf_record_creacion_skill_step_v1`.
- La acción `profile_native_skill_invoke_v1` del caller Edge ya tiene transporte OIDC. Una integración nativa posterior debe preservar su ruta SQL vigente para otras skills y no declarar `SKILL_INVOKED/COMPLETED` como sinónimo de RUN 0–80 completado.
- Permanece P0: no existen authority activa perfil→`EJECUCION_SKILL_LF` ni entrada `PROGRAMMING_ANALYSIS_LF` READY en catálogo; no editar grants/contratos oficiales o ejecutar hasta cerrar admisión. Pruebas PP01–PP15 son criterios, no resultados demostrados.

## Apertura read-only del RUN de skill (brecha nativa, preadmisión)

- La entrada `SKILL_EXECUTION` del Router resuelve a `EJECUCION_SKILL_LF`, operación existente 0–80. `fn_lf_operation_reserve_execution_v1` es el **reservador genérico vigente**, pero no valida por sí mismo el Router/caller/negocio: sólo un host con identidad admitida y control previo puede llamarlo y registrar/readback del paso 0. No invocarlo desde A1, A2 ni un consumidor con permisos propios.
- `lf_skill_invoke_v1` para `READ_ONLY` termina una invocación SQL sin `child_execution_id`; eso no es un RUN gobernado. El guard `adapters/run_business_binding_v1.py` devuelve `RUN_GOVERNED_CHILD_ABSENT_READ_ONLY_INVOKER` en ese caso. Ningún `skill_run_id` SQL reemplaza `execution_id` de `EJECUCION_SKILL_LF`.
- **P0 pendiente:** enlazar el caller/invocador gobernado actual con la reserva nativa, identidad read-only, paso 0 y readback transaccional, sin alterar el efecto `READ_ONLY`, crear Router alterno ni cambiar ACL. `lf_pre_ekb_child_dispatch_v1` sólo sirve a ACT-0057: no utilizar para A2. No ejecutar A3 ni admitir mientras falte este enlace.
- Documento y pruebas: `handoffs/NATIVE_READONLY_SKILL_RUN_OPEN_CANDIDATE_20261106.md` y `steps/a2/evals/test_run_business_binding_v1.py` (32 pruebas sintéticas; NO prueban que el host haya reservado, juzgado o escrito recibos).

## Lote 15: planificación de reserva/readback de RUN (sin ejecución)

- El código candidato `adapters/native_readonly_run_plan_v1.py` evalúa condiciones declaradas antes de reservar `EJECUCION_SKILL_LF`, deriva IDs y clave de idempotencia estables (padre + skill + hash de input), y verifica el readback **supuesto** del reservador, RUN hijo y `init_execution` (paso 0). Es una propuesta local, NO ejecuta RPC.
- El reservador canónico `fn_lf_operation_reserve_execution_v1` valida idem/target/request pero **no** compara manifiesto en replay. El plan exige negocio, fuente Main, actor y `skill_run_id` exactos; acepta solo `operation_policy_snapshots` como metadata de gobernanza adicional. Drift ⇒ bloqueo.
- `steps/a2/evals/test_native_readonly_run_plan_v1.py`: 39 pruebas sintéticas; el plan mantiene siempre `host_attested=false`, `reservation_executed=false`, `step0_recorded=false`, `readback_authenticated=false`, `a3_allowed=false`, incluso con fixture PASS.
- Documento de enlace mínimo: `handoffs/NATIVE_READONLY_INVOCATION_PRE_ADMISSION_CANDIDATE_20261106.md`. Requiere cambiar fuente oficial invocador/Edge mediante su gobierno **antes** de admisión: evitar handler SQL prematuro / estado COMPLETED en READ_ONLY nativo y nunca reportar `SKILL_INVOKED` si la RPC respondió BLOCKED.
- P0 sin resolver: autorización de perfil a `EJECUCION_SKILL_LF` (actualmente 0 filas), catálogo READY (0 para esta skill), aprobación de caller OIDC y fuente Main; registro real del paso 0 y juez nativo. No promover ni ejecutar A3.

## Ciclo Golden interno A2 → juez existente → A3 (candidato, NO activado)
- Durante `execute_skill` de la operación `EJECUCION_SKILL_LF`, A1 entrega su resultado a A2; A2 debe cumplir su trabajo de clasificación, activación dinámica de las 12 dimensiones/59 elementos y plan dirigido a A3. Una brecha de evidencia legítimamente encargada a A3 no convierte A2 en incompleta.
- Primero control determinístico. Después, **únicamente el juez semántico existente mediante la ruta nativa autorizada** revisa calidad, profundidad, contradicciones y cobertura material del candidato A2. No crear otro juez, invocador, motor, Router ni dispatcher.
- PASS externo acreditado: gate interno de A2 permite al coordinador invocar A3 **una sola vez** con el resultado y las instrucciones. Los recibos deben vincularse al mismo RUN, SHA exacto de candidato y evidencia de readback. El propio productor no puede autodeclarar PASS.
- FAIL reparable: el juez devuelve dimensión, elemento, criterio, esperado, observado, evidencia, causa y corrección. A2 regenera con historial íntegro y no repite defectos. Máximo **3 entregas A2** (original + 2 correcciones), sin consumir intentos por fallos de transporte.
- Tercer FAIL: **no A3**, terminar proceso y elaborar expediente terminal al perfil. Cierre de ticket solo mediante operación canónica con recibo; si no existe, `CLOSURE_NOT_VERIFIED`. Estado interno `A2_MAX_ATTEMPTS_EXCEEDED` NO es un estado de BD instalado.
- `output_validate`/60, `semantic_judge`/70 y `report_output`/80 del RUN gobernado mantienen su orden; el juez de la operación en 70 no prueba retroactivamente que A2 haya sido revisada antes de A3.
- El código de `guards/native_review_cycle_v1.py` y su esquema/23 pruebas **solo simulan lógica determinista**; no ejecutan modelo ni API de juez, no hacen persistencia y NO acreditan enlace nativo. Bloquear la invocación real mientras `PROGRAMMING_ANALYSIS_LF` no esté admitida y el juez nativo de A2 no esté verificado.

## Continuidad 2026-11-09 — Ruta semántica hacia Golden y mapa de A3 (fuente candidata)

**Readback:** PR #3624; evidencia `steps/a2/evals/results/a2_semantic_golden_bridge_source_readback_20261109.json` y mapa `handoffs/A3_LF_SCREEN_SOURCE_MAP_CANDIDATE_20261109.json` (ruta relativa a raíz de la skill).

- **Corregido como fuente candidata:** `adapters/a2_semantic_input_integrity_v1.py` valida coherencia de `SEMANTIC_REVIEWED_CANDIDATE` con los contratos A1/A2, literal de la petición, hash semántico, operación, target, restricciones y sus spans. Únicamente para `PROGRAMMING_ANALYSIS_LF` y negocio `LF`. El resultado `CHECKED_SOURCE_ONLY` NO acredita juez independiente, fuentes CURRENT, RUN ni permiso de A3.
- **Integrado sin nuevo contrato:** `adapters/golden_dimensions_v1.py` y `adapters/a2_a3_intake_preview_v1.py` pueden aceptar la interpretación semántica no ambigua validada por el helper; la ruta PRESTRUCTURED continúa intacta y todo `a3_allowed` permanece `false`.
- **Prueba realmente ejecutada:** 15/15 regresiones Python del helper contra exactamente los blobs GitHub registrados, con exit 0; `test_a2_semantic_input_integrity_v1.py`.
- **Pruebas todavía NO ejecutadas:** las 21 regresiones previas LF/SALY y alcance, más 9 regresiones nuevas de integración semántica `test_semantic_golden_preview_integration_v1.py`. Los anteriores 41/41 Golden pertenecen a fuentes previas; NO acreditan el HEAD actual.
- **Ciclo P0 sin resolver:** A1 `REQUIRES_DECISION` por ambigüedad material no puede convertirse en `VALID_OUTPUT` ni abrir A3 por atajo. El preview de investigación conserva `a2_classification=null`, `a3_canonical_inputs=null`, `a3_dispatch_allowed=false`. La preclasificación de investigación A2-P y el gate research-only de A3 aún necesitan revisión independiente, señales tipadas y RUN/autoridad verificables, siempre con los dos contratos canónicos de A3.
- **Mapa de fuentes propuesto:** `lf_ops.fn_screen_contract_v1` (STABLE, 10 secciones en B2B-AUTH-001) y fuentes LF relacionadas; separado de `saly.reglas`. Router: LF `ENABLED`, SALY `RECOGNIZED_NOT_ENABLED`. La pantalla B2B-AUTH-001 continúa `CANDIDATO`; una extracción no equivale a aprobación.
- **Gobernanza:** PR DRAFT / NO-GO. PASE SUCCESS certifica el gate correspondiente, NO la ejecución especializada Python ni la calificación A2→A3. Sin modificaciones de Router, Main, Supabase o contratos canónicos.

## Lote P0 2026-11-09 — Preclasificación A2-P / investigación gobernada

**Estado real:** sin admisión operativa; NO se activó A3 ni se cambió el contrato canónico.

- Hallazgo P0: `material_contradiction` en la política canónica A2 es `BOOLEAN`. La cadena `UNKNOWN` no es un valor permitido. No atribuir `false` por falta de prueba negativa para desbloquear A2-P. Véase `handoffs/A2_P_RESEARCH_GATE_CANONICAL_SIGNAL_CONFLICT_20261109.md`.
- Dos fuentes canónicas de A3 sin cambio: `REQUEST_CONTEXT_V1` y `ANALYSIS_CHANGE_CLASSIFICATION_V1`. A1 `REQUIRES_DECISION` no puede ser convertido en `VALID_OUTPUT`; la ruta A2-P aún debe obtener pruebas tipadas y permiso de investigación sin eludir revisión ni RUN.
- Readback: `private.fn_lf_source_investigation_prepare_v1` existe pero la llamada directa devolvió 42501 (ACL). El usuario SQL tampoco posee EXECUTE sobre `private.fn_lf_d1_inventory_candidates_v1` ni `public.lf_targeted_evidence_acquisition_plan_v1`. No se ejecutó con rol alternativo; debe usarse una fachada gobernada.
- 14/14 comprobaciones de **política y fuentes exactas** PASS (simulación de predicados del contrato, no ejecución Python A2): `steps/a2/evals/results/a2_p_research_policy_boundary_readback_20261109.json`.
- Diez pruebas especializadas nuevas están **definidas, no ejecutadas** en `steps/a2/evals/test_a2_p_research_policy_boundary_v1.py`. Las 30 regresiones anteriores en checkout completo también están pendientes. No inferir cierre por PASE.
- Decisión de lote: no realizar cast de contradicción desconocida, no cambiar esquema, no desactivar gate de ambigüedad; A2-P→A3 se mantiene NO-GO hasta permiso de resolutor, señal tipada, juez independiente y pruebas Python exact HEAD.
