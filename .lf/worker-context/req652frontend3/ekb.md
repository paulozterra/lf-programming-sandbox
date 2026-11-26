# Errores conocidos (EKB) para este lote

Consultado por la ruta antes de implementar (T56). Revisa cada uno: si tu cambio puede repetirlo, aplica la prevención y deja la validación como prueba.

## LF-ROUTE-MODIFY-RETAINED-BEHAVIOR-UNPROTECTED — Modificar frontend existente sin pruebas que protejan lo conservado
- Severidad: High · Frecuencia: 1 · Categoría: PLANNING
- Patrón: La cadena bloquea REUTILIZACION_INDETERMINADA sobre un archivo de frontend
- Causa raíz: Solo existía protección por pruebas Java y el frontend no tenía pruebas
- Prevención: Suite visible declarativa con verificación por mutación y lote de caracterización antes de modificar
- Validación: Simulación T7 crea el lote de caracterización y la cadena protege su suite

## GOV-025 — Frontend Prototype Architect podía aprobar un plan sin crear el prototipo que su contrato exige
- Severidad: ALTA · Frecuencia: 2 · Categoría: PROFILE_DELIVERABLE_CONTRACT
- Patrón: Profile de ejecución produce una especificación de trabajo y la cuenta como artefacto final. El nombre/purpose prometen implementación, pero el gate sólo comprueba planificabilidad.
- Causa raíz: Contrato, schema, fixture, judge y propósito no comparten una definición única de done/deliverable. El schema modela intención de creación, no evidencia del archivo creado; el judge valida el plan como si fuera prototipo.
- Prevención: Todo profile cuyo propósito sea crear un artefacto debe definir done en términos observables del artefacto: file path, content/readback hash o contenido mínimo validable, apertura/parse local y acceptance checks sobre el archivo real. Separar SPEC_ONLY de ARTIFACT_CREATED; no permitir PASS_TO_*_ARTIFACT si sólo existe plan.
- Validación: Negativo: el worker_output histórico home_ruta_claridad_001 debe fallar ARTIFACT_NOT_CREATED aunque tenga files_to_create y 25/25. Positivo: AFTER debe incluir artifact_files con index.html real, content_sha256, parse/readback evidence y validación de invariantes upstream; el archivo debe abrir/parsear sin build/backend.

## PROGRAMMING-ANALYSIS-CONTEXT-SNAPSHOT-HANDOFF-001 — Analysis must hand Programming a compact resolved context snapshot instead of forcing rediscovery
- Severidad: HIGH · Frecuencia: 2 · Categoría: GOVERNANCE
- Patrón: Downstream workers re-query canonical sources for already-resolved material facts, or receive a large undifferentiated context blob, causing context loss, duplicate reads and inconsistent interpretation.
- Causa raíz: The Analysis-to-Programming boundary previously specified what facts were required but did not require a compact frozen projection of those resolved facts with a reuse/currentness protocol.
- Prevención: A6 must prepare CANONICAL_IMPLEMENTATION_BINDINGS. A9 must compile PROGRAMMING_CONTEXT_SNAPSHOT_V1 inside ANALYSIS_IMPLEMENTATION_PACKAGE_V1. Small material stable facts travel as canonical_ref + resolved_value; large identified sources as exact_ref; dynamic/staleness-sensitive sources as exact_ref + typed_resolver; irrelevant data is omitted. PG-01 must reuse the snapshot while authority_fingerprint_sha256 remains current. Requery is allowed only for MISSING, STALE, CONTRADICTION, SOURCE_DRIFT or MATERIAL_NEW_QUESTION and must use a typed resolver when available. The snapshot must not choose component structure, framework pattern, endpoint design or internal algorithm; PG-03 retains technical strategy ownership.
- Validación: Positive: PG-01 receives current PROGRAMMING_CONTEXT_SNAPSHOT_V1 with [REDACTADO] refs/fingerprint and performs zero rediscovery while fingerprint is unchanged. Negative: removing snapshot requirement, allowing freeform requery with a typed resolver, transporting a large identified source inline by default, adding CURIOSITY as a requery trigger, or leaking chosen technical strategy must fail deterministic validation. | 2026-10-09 read-only B2B_APP_SHELL source refresh preflight, PR2071 analysis_a9_b2b_shell_refresh_readback_20261009.md: recorded context v0.9 has 9 scopes, 10 abbreviated fronts, 0 matrix. Current shell v1.0 CANDIDATO; changed state rule, target repo advanced 14 commits; session and support now exist but authenticated consumer proof missing; effective permissions still not sent; 15 relationship references are derivable but canonical A7 source/currentness evidence is missing. A9 does not invent new readiness. Full source-only three-suite regression passed on scalora-vps at head 5b8ed703. Remains ACTIVO until true canonical A7 refreshed and new A9/PG01 receipt checked. | 2026-10-09 A9 live-source REFRESH persisted through public.fn_lf_decision_context_asof_record_v1: context e5adcfbf-e53f-420d-a94a-fad553fa6e48, decision PROGRAMMING_CONTEXT:B2B_APP_SHELL:REFRESH-20261009-001, SHA [REDACTADO]; rollback rehearsal returned NEW_CONTEXT and left 0 rows. Persistent readback 9 scopes, 10 canonical fronts, 15 matrix, SHA parity true, resolver RESOLVED, exact code A9 validator PASS; 0 READY, 7 NEED_MORE_EVIDENCE, 2 BLOCKED, source-only and NOT admitted to PG01. Previous v0.9 context intact. Semantic currentness and real PG01/model E2E remain pending; do not change ACTIVO to RESUELTO. | 2026-10-09 S05/S07 LF_B2B_SHELL exact main 994bda4a: 9/9 existing node22 shell contracts PASS; 8/8 direct source behavior tests PASS with isolated mocked responses (S05 ANONYMOUS/UN

## ENGINEERING-MATERIAL-HEARTBEAT-001 — Material execution can be healthy while chat UI appears stalled
- Severidad: HIGH · Frecuencia: 1 · Categoría: ENGINEERING_GOVERNANCE
- Patrón: bootstrap PASS -> material execution -> no visible durable stage -> apparent hang
- Causa raíz: Progress was persisted only at checkpoint boundaries, not at material action-step boundaries.
- Prevención: For material ACTION_SPEC_V3 steps, persist heartbeat stages before and after each declared action. CONNECTOR_BLOCKED and RETRYING are recordable for material and read-only checkpoints. Retry only the failed execution_packet operation; never restart the checkpoint. Heartbeats never alter checkpoint progress. Heartbeat is not a state-transition boundary: do not rebuild bootstrap after heartbeat writes. Return a compact receipt and rebootstrap only after checkpoint/transversal transition or an authorized state-changing operation. Do not compile ACTION_SPEC on every material heartbeat. Resolve frozen context first; only compile on ACTION_STARTED, missing context or stale fingerprint. Material packets must compile exact heartbeat arguments. Never infer heartbeat p_step_code from connector_plan seq or operation. Predictable validation errors must return allowed values and canonical next action in the error contract. Do not make the executor discover enum/check constraints or blocker storage semantics.
- Validación: PASS when material heartbeats consume ACTION_SPEC_V3; CONNECTOR_BLOCKED can be persisted for read-only checkpoints; terminal units preserve STOP_TERMINAL_DONE; checkpoint progress remains ledger-derived.

## GOV-038 — Una remediacion de prompt puede pasar un canario y fallar otro semanticamente equivalente
- Severidad: ALTA · Frecuencia: 1 · Categoría: PROFILE_RUNTIME_QUALITY
- Patrón: Se valida la remediacion con un unico canario o con canarios de fraseo homogeneo; el PASS observado se generaliza a toda la clase de entradas equivalentes.
- Causa raíz: La correccion se implemento como FINAL SERIALIZATION GUARD al final del SKILL.md. Esa tecnica de saliencia por posicion es sensible al fraseo del input: el modelo pequeno la aplica en un fraseo y la omite en otro. No existe control determinista que obligue la serializacion en tiempo de ejecucion; el literal solo esta descrito en prosa del perfil.
- Prevención: Exigir un minimo de canarios de fraseo heterogeneo por clase semantica, con criterio all-must-pass y comparacion directo vs Router. Preferir un control determinista de serializacion en el adaptador de runtime sobre una instruccion en prosa dependiente de saliencia. Tratar la divergencia directo/Router como BLOCK_ROUTER_DIRECT_DIVERGENCE y no como varianza aceptable.
- Validación: Repetir ambos canarios sobre el SHA de cierre y comparar el RAW tras Assistant: con trim contra el literal exacto; exigir igualdad byte a byte en los dos y entre si. VALIDADO 2026-08-28: tras retirar el priming negativo (commit c613287, PR #287), los dos canarios de fraseo heterogeneo sobre [REDACTADO] devolvieron el literal exacto de cuatro segmentos: directo 3ac1cd3e-56e6-4b33-8306-18c167e0a6a8 (run 33149700468) y Router e5122ea6-4333-432e-b94a-e333144da635 (run 33149705800), ambos con input_md5 identico al del handoff. Divergencia directo/Router resuelta.

## GOV-PILOT-ADAPTER-RUNTIME-001 — Runtime queue pudo ejecutar Adapter mientras Router canónico lo bloquea
- Severidad: HIGH · Frecuencia: 1 · Categoría: GOVERNANCE_ROUTER
- Patrón: PROFILE_RUNTIME_QUEUE_SUCCEEDED != ROUTER_AUTHORIZED cuando el runner puede materializar un adapter cuyo registry canónico sigue runtime_enabled=false.
- Causa raíz: Desalineación entre el runner de EJECUCION_PERFIL_LF, que aplica el runtime capsule del adapter, y la autoridad canónica del Router, que exige adapter_metadata.runtime_enabled=true y runtime autorizado en public.v_lf_fuente_operativa. El adapter sigue CANDIDATO/READ_ONLY/NO_HABILITADO.
- Prevención: Antes de contabilizar cualquier ejecución de perfil con adapter como evidencia de cadena, ejecutar ACT-0001/lf_router_resolve_v1 sobre target exacto y exigir READY_TO_EXECUTE. Un SUCCEEDED de queue no sustituye el gate del Router.
- Validación: Para Product Director, UI Architect y ACT-0051, public.lf_router_resolve_v1 debe retornar READY_TO_EXECUTE; el adapter debe estar autorizado en la fuente canónica. Recién después repetir ejecución y exigir receipt + RAW material + downstream authorization aplicable.

## IG-M100-LEGACY-JUDGE-VS-PINNED-RECEIPT-001 — La prueba previa de M9.0 no equivale a la identidad firmada del release
- Severidad: HIGH · Frecuencia: 1 · Categoría: INPUT_GOVERNANCE
- Patrón: GIT_HEAD_SAME_BUT_DB_MANIFEST_MUTABLE; HISTORICAL_JUDGE_DIGEST_NOT_SIGNED_RELEASE_ID
- Causa raíz: El contrato de M10.0 exigía comparar un digest del test histórico pre-freeze con el recibo final; confundía evidencia de juez con autoridad de un snapshot firmado. Además fn_input_governance_release_bundle_manifest_v1 consulta objetos DB vivos.
- Prevención: En binding de ingeniería seleccionar por checkpoint DONE M9.0/BUNDLE_READBACK su receipt_id explícito, no latest ni rebuilt; recomputar identidades SHA y 7 digests desde snapshot firmado; mantener diferencia del test histórico visible; exigir currentness y autorización humana separados antes de promoción.
- Validación: 2026-10-12: readback receipt 187 VERIFIED EVIDENCE_VERIFIER_V1, head SHA40 y bundle SHA256 consistentes; 7/7 componentes internos, negativo registry tamper falla, prueba histórica diversa preservada; M9.12 #1667 coincide; PR2309 merged main=[REDACTADO], migración aplicada, CP2 DONE, ledger 35%. No prueba de producción.

## LF-NUCLEO-MIGRATION-CANDIDATE-LEGACY-COEXISTENCE-20261121-001 — La asociación FK de una candidata migrada puede ocultar la regla legada antes de publicar
- Severidad: HIGH · Frecuencia: 1 · Categoría: RULE_GOVERNANCE
- Patrón: CANDIDATE_LEGACY_FK_PREMATURE_REPLACEMENT
- Causa raíz: La vista de compatibilidad equipara asociación de candidata con reemplazo; no separa trazabilidad de origen, identidad legada y corte operativo.
- Prevención: En una migración de prueba preservar legadas: entrar por nucleo_regla_proponer_v1, registrar origen MIGRACION con referencias exactas y juicio completo ligado al hash del paquete, sin asignar regla_legacy_id ni publicar hasta una transición de coexistencia validada. No fabricar APROBAR ni confundir pruebas deterministas con juicio semántico. Revisar duplicación visible por código y lectores antes de habilitar publicación; no cerrar puertas antiguas sin aprobación.
Corrección #4524: vista de compatibilidad conserva cada legada sin condición; las reglas de núcleo ligadas por FK, código o referencia de origen MIGRACION lf_ops.reglas quedan solo en la superficie nativa. No equivale a cutover ni autorización de publicación.
- Validación: PASE 44880886628 PG17: 10 candidatas, 10 juicios CONTEXTO_ACTUAL con siete criterios, 10 evaluaciones; 10 hashes falsos rechazados por NUCLEO_JUICIO_HASH_DISTINTO y 9 intentos de publicación rechazados por NUCLEO_PUBLICAR_SIN_PROMOCION; 17/17 regresiones y 17/17 después de rollback. Nueve DEVUELTA, REG_CHK_007 AUTO nota 97 sin publicar. La prueba existente del puente verifica ocultamiento al asignar FK. SELECT después del Train: diez candidatas, cero vigentes, cero FK, 586 legadas idénticas.
PG17 PASE 44883064124 positivo; 44883134661 negativo por AM_COEX_V6_ORIGIN_DUPLICATE; 44883228388 recertificado positivo, PUENTE 8/8 y 17/17 regresiones tras rollback.

## LF-ROUTE-DATA-VISIBLE-NO-DB-CONN — El comando visible de DATA no recibe conexión a la base
- Severidad: High · Frecuencia: 1 · Categoría: ROUTE_TOOL
- Patrón: El lote DATA falla en el comando visible con error de conexión
- Causa raíz: El puente del Worker no derivaba las variables PG desde DB_*
- Prevención: Derivar las variables PG desde las DB_* validadas en el puente
- Validación: Ensayo T40 de un lote DATA

## LF-ROUTE-DEPENDENCIA-DECLARADA-AUSENTE — Un endpoint registrado por varios lotes rompe las dependencias declaradas
- Severidad: High · Frecuencia: 1 · Categoría: PLANNING
- Patrón: T7_BLOCKED DEPENDENCIA_DECLARADA_AUSENTE con el registro de implementaciones regenerado
- Causa raíz: La corroboración del proveedor no distinguía qué área implementa el endpoint
- Prevención: Corroborar un endpoint solo con su lote BACKEND atestiguado y, si no hay, con el índice de código
- Validación: Prueba sintética con el endpoint en tres áreas
