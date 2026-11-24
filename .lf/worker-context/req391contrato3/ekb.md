# Errores conocidos (EKB) para este lote

Consultado por la ruta antes de implementar (T56). Revisa cada uno: si tu cambio puede repetirlo, aplica la prevención y deja la validación como prueba.

## LF-IDV-FACEPHI-DISABLED-GUARD-001 — Proveedor IDV seleccionado no equivale a activado
- Severidad: High · Frecuencia: 1 · Categoría: AUTHENTICATION
- Patrón: Provider declared while enabled=false
- Causa raíz: Confundir proveedor configurado con integración habilitada
- Prevención: Verificar bandera central, falta de integración y requerimiento B2B explícito antes de una activación futura por ruta oficial
- Validación: Estado apagado debe negar invocación, negar VERIFIED sin prueba, preservar flujos no IDV y ausencia de API externa

## LF-PROFILE-HANDOFF-DIRECT-42501-OLD-RUN-SUBSTITUTION-001 — Router entrega Gate2 READY pero agente intenta SQL read-only, obtiene 42501 y reutiliza run antiguo
- Severidad: HIGH · Frecuencia: 1 · Categoría: PROFILE_RUNTIME_GOVERNANCE
- Patrón: READ_ONLY_DIRECT_PROFILE_ADMISSION_AND_HISTORICAL_EXECUTION_SUBSTITUTION
- Causa raíz: El consumer ignora el inicio OIDC/Edge propio de EJECUCION_PERFIL_LF; CLAUDE.md mezclaba el contrato legacy independiente con el modo V3 CURRENT_CONTEXT_REVIEW y no explicitaba BEGIN desde el handoff.
- Prevención: Leer EKB y el runbook de perfiles. Un Gate2 GATE2_DERIVED_PENDING_GOVERNED_ADMISSION/HANDOFF_CONTEXT_TO_SELECTED_PROFILE obliga al agente a generar LF_PROFILE_NATIVE_BEGIN_REQUEST_V1 con router_context sin cambios y executor_mode GPT_NATIVE, crear Issue Github con label lf-profile-resume-governed y dejar que el workflow use GitHub OIDC->Edge->service_role->RPC canónico. No llamar el admit RPC desde supabase_read_only_user, no ampliar ACL, no mover secrets al Router, no crear dispatcher o ruta directa al perfil. Comprobar nuevo execution_id antes de afirmar recepcion; si no existe, NOT_EXECUTED, nunca reutilizar run previo. Continuar con mismo ID y evidencia real por LF_PROFILE_NATIVE_RESUME_REQUEST_V1 (screen/RAW/V3) hasta 11/11 COMPLETED READY, sin repetir autorización dentro del mismo alcance. CURRENT_CONTEXT_REVIEW es solo read_only/no_write/no_promotion, sin independencia simulada.
- Validación: Criterio canónico LF: Router ACT-0001 entrega Gate2 VALID, sin ejecutar el perfil ni transportar credenciales. El perfil inicia una ejecución distinta mediante LF_PROFILE_NATIVE_BEGIN_REQUEST_V1 en GitHub OIDC -> Edge -> RPC autorizado, con service_role exclusivamente dentro de Edge. Las etapas posteriores reutilizan el mismo execution_id y registran screen_selection, RAW real, output_validate y dictamen V3 con procedencia verificable. El cierre requiere exactamente 11/11 STEP_PASS_WITH_EVIDENCE, semantic_judge 70 y report_output 80 con trust_validation válido, ejecución COMPLETED y terminal READY en Supabase. Controles de permisos: supabase_read_only_user sin EXECUTE para admit_v2; service_role con EXECUTE. Evidencia positiva: tres ejecuciones distintas, EXEC-PROFILE-GATE2-31340B34D5B0E320E3B83C00, EXEC-PROFILE-GATE2-93CEF1403D252A61F5EC2AC8 y EXEC-PROFILE-GATE2-1B544082A880C107E66BCBD1; GitHub Actions 41293887404, 41296096617 y 41296832156. Este certificado acredita el transporte y cierre de los perfiles, no modifica reglas de negocio ni acredita producción.

## LF-PROFILE-STEP80-IG-CLEARANCE-OMITTED-20261116-001 — Step40 omite ig_security_clearance requerido por Step80
- Severidad: HIGH · Frecuencia: 1 · Categoría: PROFILE_EXECUTION
- Patrón: REQUIRED_BOOLEAN_NOT_TRANSPORTED
- Causa raíz: Contratos de productor y consumidor no alineados; NULL no equivale a false en SQL.
- Prevención: Persistir false explicito en Step40 READ_ONLY; mantener fail-closed de Step80.
- Validación: PG17/18 BEGIN/ROLLBACK + CI; readback EKB/migracion y Step40 en un RUN nuevo por ruta oficial.

## AUD-001 — Independencia atribuida a una lectura de la misma cadena ejecutora
- Severidad: High · Frecuencia: 8 · Categoría: Auditoría
- Patrón: Un flujo declara independencia=true o equivalente, pero la identidad que debería respaldarla no puede autenticarse o no genera una attestation verificable; la separación existe como campo/rol nominal, no como evidencia ejecutada.
- Causa raíz: R5_EROSION_PROCESO: se aceptó una marca de independencia sin exigir una identidad/canal separado que produzca una attestation operativa verificable; el sistema conservó independencia declarada aunque los principals CI dedicados estaban NOLOGIN y no existían attestations.
- Prevención: La independencia no puede ser un booleano autodeclarado. Debe derivarse de una attestation verificable producida por una identidad/canal realmente separado y ligada a ejecución/HEAD; si no existe evidencia válida, el estado debe ser NOT_VERIFIED/NOT_APPLICABLE según la ADR vigente, nunca true.
- Validación: Negativo: sin attestation válida y sin principal independiente operativo, ninguna ruta puede devolver independencia=true. Positivo: cuando la política exija independencia, debe existir attestation verificable ligada a la ejecución/HEAD y a un actor distinto; cuando la ADR la marque NOT_REQUIRED, el sistema debe representarlo explícitamente y no simular independencia.

## SQL-015 — REVOKE ejecutado fuera del plano del grantor no cambió el estado
- Severidad: High · Frecuencia: 5 · Categoría: Postgres/Supabase Admin
- Patrón: El grantor/owner es supabase_admin; postgres no tiene MEMBER/USAGE/SET sobre supabase_admin; REVOKE no falla pero pg_auth_members/proacl permanece igual.
- Causa raíz: La validación previa comprobó que el SQL era aceptado, pero no que el rol efectivo tuviera autoridad sobre el grant originado por supabase_admin. El éxito del statement se confundió con cambio efectivo.
- Prevención: Antes de remediar ACL o memberships, inventariar owner/grantor y medir efecto. Si el grant es administrado intencionalmente por Supabase, no exigir su borrado como proxy de seguridad: separar metadata administrativa de capacidad runtime y controlar la frontera efectiva (LOGIN/INHERIT/SET, schema Data API expuesto y wrappers invocables). No repetir REVOKE que el readback ya demostró inefectivo.
[SECURITY_ADVISOR_20260905] Antes de REVOKE masivo medir ACL efectiva por target y preservar explícitamente service_role. Un remediation de advisor debe incluir denominador pre/post y no confundir ausencia de policy con exposición cuando tampoco hay grants cliente.
- Validación: Para roles LF: NOLOGIN, NOINHERIT y NOBYPASSRLS; cualquier membership hacia un actor runtime bloquea, y una membership administrativa de postgres solo es aceptable con INHERIT=false y SET=false. Para pg_net: el control-plane PostgREST debe excluir net de db_schema y el conteo de wrappers API invocables con egress net debe ser 0. Ejecutar mutaciones negativas y readback posterior.
[REMEDIATION_20260905] Snapshot ACL previo: 37 targets, anon/auth grants efectivos en 23, service_role SELECT 37. Snapshot posterior: anon=0, authenticated=0, service_role SELECT=37. Assertions de migration abortan ante target faltante, RLS deshabilitado, policy drift, grant residual o regresión service_role.

## GOV-ADAPTER-GUARD-AUTHORITY-CONFLICT-001 — Adapter Repair Guard contradice autoridad canónica vigente de creator_asset
- Severidad: ALTA · Frecuencia: 2 · Categoría: GOVERNANCE
- Patrón: AUTHORITY_DRIFT_PLUS_ACTIVE_SCOPE_CONCURRENCY
- Causa raíz: Deriva de autoridad entre contrato GitHub legado owner_skill/parent_skill y runtime/Supabase Router-bound vigente. La reparación parcial en Supabase no constituye reconciliación canónica mientras main conserve reglas contradictorias.
- Prevención: No cerrar ni promover Adapter mientras GitHub canonical contract y Supabase enforcement discrepen sobre owner_skill/parent_skill. Reconciliar mediante cambio versionado en fuente canónica y luego repetir canary/readback.
- Validación: PASS FINAL: GitHub main v0.3 alinea CREACION_ADAPTER_LF con ROUTER_BOUND_ONLY, parent_skill_required=false y base adapters/. PR #348 exact-head CI PASS (lf-contract-check, Validate LF Packs, Bootstrap). Supabase Adapter reconciliado post-last-writer a 1 GPT semántico / 16 no-GPT, Router READY_TO_EXECUTE, lifecycle 1/1.

## SRC-010 — Artefacto explicativo añadió requisitos no sustentados por la fuente canónica
- Severidad: High · Frecuencia: 2 · Categoría: SOURCE_GROUNDING
- Patrón: Fuente canónica incompleta o específica + transformación a diagrama/resumen/imagen -> el artefacto rellena huecos con requisitos habituales o plausibles -> el receptor puede interpretarlos como reglas vigentes aunque nunca fueron recuperadas de la fuente.
- Causa raíz: El generador priorizó completar una representación didáctica con patrones plausibles en vez de mantener un boundary estricto entre hechos source-bound y contenido ilustrativo/no demostrado.
- Prevención: Toda explicación, resumen o visual que represente reglas/requisitos debe construirse claim-by-claim desde la fuente autoritativa. Los claims no sustentados se omiten o se etiquetan explícitamente ILLUSTRATIVE/PROPOSED; nunca se presentan con el mismo estatus que SOURCE_BOUND. Antes de entregar, reconciliar semánticamente el artefacto contra la fuente.
- Validación: Negativo: inyectar en un visual de Login una regla de complejidad no presente en la fuente debe bloquear o quedar marcada como ilustrativa, nunca canónica. Positivo: cada claim del artefacto debe resolver a una fuente autoritativa exacta y conservar su alcance contextual; una política de creación de nueva contraseña no puede aparecer como validación del campo de contraseña actual de Login.

## CI-CHANGESET-MANIFEST-SCOPE-ADMISSION-001 — Canonical contract scope rejected required changeset manifest path
- Severidad: HIGH · Frecuencia: 1 · Categoría: CI / CHANGESET GOVERNANCE
- Patrón: New canonical governance surface is introduced but an older preflight scope authority still rejects the path before the new evaluator can run.
- Causa raíz: The legacy LF contract scope allowlist predated CHANGESET_GOVERNANCE and had no narrow admission rule for the new canonical manifest surface.
- Prevención: When introducing a canonical versioned governance surface, update the existing scope validator in the same solution with a narrow syntax-bound admission and negative lookalikes; never bypass the preflight.
- Validación: Exact failure must disappear on PR-4 rerun; intrinsic scope test accepts one canonical changesets/<solution_ref>.json and rejects nested, hidden, YAML and malformed lookalikes.

## GOV-017 — Rutas declaradas en allowed_paths y path_prefix no existen en el arbol real del repo
- Severidad: ALTA · Frecuencia: 1 · Categoría: GOVERNANCE_INTEGRITY
- Patrón: Declaracion de gobernanza sin verificador. Regla escrita, nadie la comprueba.
- Causa raíz: Las rutas declaradas en gobernanza nunca se validan contra el arbol real. La declaracion y la realidad pueden divergir indefinidamente sin que ningun control falle. Mismo patron que naming_rule en lf_artifact_destination_registry, que no tiene ni un consumidor en el repo (0 coincidencias de naming_rule y SLUG_ en .py, .yaml, .json, .md).
- Prevención: Control de CI obligatorio: por cada entrada de allowed_paths y por cada path_prefix declarado en gobernanza, verificar que la ruta exista en el arbol del HEAD evaluado. Ruta declarada inexistente = FAIL, no warning. Prohibido autorizar rutas que no existen todavia; si la ruta es futura, se declara al crearla. Extension general: toda ruta, prefijo o regla de nombrado declarada en un activo de gobernanza debe tener un consumidor identificable que la verifique; si no lo tiene, es decorativa y debe eliminarse o cablearse.
- Validación: Prueba positiva: allowed_paths alineado al arbol pasa. Prueba negativa: agregar una ruta inexistente a allowed_paths debe hacer fallar el gate. Ejecutar sobre el repo real, no sobre fixture.

## GOV-CARD-DEPTH-ORDER-001 — CREACION_CARD_LF tiene depth gates después de contract_judge/close
- Severidad: HIGH · Frecuencia: 1 · Categoría: GOVERNANCE_CONTRACT
- Patrón: GIT_FIRST_STEPS_END_AT_30 + SUPABASE_REQUIRED_DEPTH_31_39 + CONTRACT_JUDGE_28_REQUIRES_ALL_REQUIRED_STEPS_PASS
- Causa raíz: Drift entre fuente GIT_FIRST_YAML y extensiones Supabase de junio: los depth gates fueron anexados después del cierre sin reconciliar el procedimiento Git ni la semántica all_required_steps_pass del contract judge.
- Prevención: Antes de ejecutar Card Factory, reconciliar lista y orden completo de required steps entre Git y Supabase. Los depth gates deben ejecutarse antes del contract judge/close; el judge debe validar required pre-judge steps y el receipt final debe exigir todos los required steps completos. Validar source parity y canary limpio antes de fan-out.
- Validación: CONFIRMED: Git blob [REDACTADO] contiene sólo 15-30. Supabase readback muestra 31-39 required con source SUPABASE-DEPTH-GATE-20260601-001 / SUPABASE-EXAMPLES-DEPTH-20260601-001. Clean canary LF-CARD-CANARY2-CAMPANAS-20260831-001 pasó 1-26 y quedó bloqueado antes de contract_judge; receipt_allowed=false. Source-first fix abierto en PR #361 HEAD [REDACTADO]; Validate LF Packs PASS, lf-contract-check/bootstrap aún in_progress al checkpoint.

## GOV-PROFILE-AGG-JUDGE-SOURCE-DRIFT-001 — Aggregate judge Perfil omitía fail_if canónico close_without_operation_execution
- Severidad: ALTA · Frecuencia: 1 · Categoría: GOVERNANCE
- Patrón: -
- Causa raíz: Deriva de materialización entre fuente GitHub y registry Supabase.
- Prevención: Antes de promover aggregate judge comparar SHA y pass_if/fail_if contra fuente autora GitHub.
- Validación: PASS: fail_if sincronizado con judge_contrato_perfil_lf.yaml SHA [REDACTADO]; status ACTIVE_ENFORCEMENT.
