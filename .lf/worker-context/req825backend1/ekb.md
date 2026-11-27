# Errores conocidos (EKB) para este lote

Consultado por la ruta antes de implementar (T56). Revisa cada uno: si tu cambio puede repetirlo, aplica la prevención y deja la validación como prueba.

## LF-ROUTE-CONTRACT-LIVE-OPERATION-MISSING — Operación contractual ausente en runtime
- Severidad: High · Frecuencia: 1 · Categoría: ENGINEERING_ORCHESTRATION
- Patrón: Bloqueo CONTRACT_LIVE_OPERATION_MISSING
- Causa raíz: La comparación viva encuentra una operación declarada que no está publicada; puede existir una dependencia BACKEND aún pendiente
- Prevención: Acreditar operación y responsable; exigir comparación al integrar el responsable, sin omitir operaciones existentes
- Validación: Comparación viva y pruebas de operación ausente con y sin responsable acreditado

## LF-ROUTE-DEPENDENCIA-DECLARADA-AUSENTE — Un endpoint registrado por varios lotes rompe las dependencias declaradas
- Severidad: High · Frecuencia: 1 · Categoría: PLANNING
- Patrón: T7_BLOCKED DEPENDENCIA_DECLARADA_AUSENTE con el registro de implementaciones regenerado
- Causa raíz: La corroboración del proveedor no distinguía qué área implementa el endpoint
- Prevención: Corroborar un endpoint solo con su lote BACKEND atestiguado y, si no hay, con el índice de código
- Validación: Prueba sintética con el endpoint en tres áreas

## LF-NUCLEO-TANDA6-7-JUICIOS-Y-REINTENTO-V4-20261123-001 — Tanda 6: seis PASS y una DEVOLVER + revisión v4
- Severidad: MEDIUM · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: NUCLEO_TANDA6_DEVOLUCION_VERSION_GOBERNADA
- Causa raíz: La descripción v3 presentaba requisitos como alternativas; el backend, las pruebas y la condición requieren todos. REG_TEC_009 borde de idempotencia pendiente de validación runtime de Paulo.
- Prevención: No promover REG_CHK_004 v4 sin otro juicio independiente. Validar en Paulo comportamiento real del borde exacto AUTH/IDEMPOTENCY_KEY_VALIDITY_MINUTES=5 y bindings de usuario, clave, sha y operación.
- Validación: PG17 BEGIN ROLLBACK, hash alterado negativo por 7 reglas, 6 AUTO, v3 DEVUELTA, v4 CANDIDATA no promovida, 17 regresiones y lector IG 14/14.

## LF-ROUTE-PEDIDO-WORKFLOW-SIN-AVANCE — Un workflow de la ruta quedó colgado sin terminar
- Severidad: Medium · Frecuencia: 1 · Categoría: CI_GOVERNANCE
- Patrón: Corrida en in_progress o queued más allá de TIMEOUT_MINUTES
- Causa raíz: Cola de runners saturada, espera de aprobación o paso bloqueado en red
- Prevención: Fijar timeout-minutes en cada job y reintentos acotados para llamadas de red
- Validación: stalled_run en pilot/request_failure_notify.py

## LF-ROUTE-PEDIDO-T7-FALLIDO — Admisión T7 fallida
- Severidad: High · Frecuencia: 5 · Categoría: ENGINEERING_ORCHESTRATION
- Patrón: Bloqueo PEDIDO_T7_FALLIDO
- Causa raíz: La admisión no pudo producir un plan válido; el código específico requiere diagnóstico
- Prevención: Revisar evidencia de A9, reutilización y selección antes de reintentar
- Validación: Pruebas sintéticas T7 y CI exacto del plan

## IG-EDGE-RPC-SCHEMA-BRIDGE-001 — Validator Edge calls SQL handoff functions outside default REST schema
- Severidad: HIGH · Frecuencia: 1 · Categoría: INPUT_GOVERNANCE_REFACTOR
- Patrón: -
- Causa raíz: New Edge Validator uses unqualified PostgREST RPC for two functions originally only in programacion schema
- Prevención: Before deploy, inspect exact RPC namespaces; expose minimal public SECURITY INVOKER wrappers that delegate to canonical programacion functions with EXECUTE exclusively for service_role, revoke PUBLIC/anon/authenticated; assert privileges and HTTP negative. Never expose whole schema.
- Validación: PR #2002 merged [REDACTADO]; migration applied; two RPCs discoverable by PostgREST with anon HTTP 401 permission denied; deployed Validator v15 and Agent v14 exact Git source; sandbox resume 8/8 PASS; live authenticated resume remains unobserved.

## IG-M101-SUPABASE-PUBLIC-DEFAULT-RPC-GRANTS-001 — Supabase public schema default EXECUTE grants must be explicitly revoked for new facades
- Severidad: HIGH · Frecuencia: 1 · Categoría: IG_SECURITY_FACADE
- Patrón: Schema-level default grants can silently expose a SECURITY INVOKER wrapper even when its runtime authority is intended to remain restricted.
- Causa raíz: postgres pg_default_acl for public functions grants EXECUTE directly to anon, authenticated and service_role. Revoking PUBLIC alone does not remove those explicit default privileges.
- Prevención: For each new public facade, query pg_default_acl first; REVOKE specifically from anon and authenticated, and service_role for owner-only dependencies. Verify has_function_privilege across roles in a ROLLBACK transaction, keep SECURITY INVOKER and reuse original function, then Git PR merge, exact migration ledger and DB readback. Do not add SECURITY DEFINER to bypass privilege errors.
- Validación: Initial source rollback failed M101_NEW_FACADE_PUBLIC_ROLE_EXPOSURE. Corrected in PR #2301 and verified: anon/authenticated EXECUTE=false on both new facades; service_role only worker_spec=true, currentness=false. Positive and negative router behavior parity in rollback, no residues. PR#2301 merged main [REDACTADO]; migration 20261012153000 exact Git blob [REDACTADO]. CP4 DONE, no production/runtime activation.

## IG-M107-G2B-TWO-BACKEND-EXECUTED-021 — M10.7 G2B dos sesiones reales: commit fuente y fence final del fixture
- Severidad: HIGH · Frecuencia: 1 · Categoría: GOVERNANCE
- Patrón: G2B_TWO_SESSION_COMMIT_AND_FINAL_LOCK_FIXTURE
- Causa raíz: Se carecía de Operation admitida de dos sesiones sobre el fixture; se reutilizó transporte confiable existente bajo modo fijo sin SQL/credenciales en el PR solicitante.
- Prevención: No declarar G2B global ni activar consumidores hasta comprobar cobertura transaccional de todos los writers de fuentes reales, paridades y rendimiento CP3; conservar currentness actual.
- Validación: PASS_FIXTURE_ONLY: run 38827928190, job 116739743662, 12/12, READ COMMITTED, write commit, TOCTOU lock, readback 0 filas, 21 triggers. NO equivale a G2B global PASS.

## IG-VALIDATOR-HANDOFF-PRODUCER-NOT-WIRED-001 — Validator Edge promotion blocked: verified Curator handoff producer not wired
- Severidad: HIGH · Frecuencia: 1 · Categoría: INPUT_GOVERNANCE_REFACTOR
- Patrón: -
- Causa raíz: Edge Curator v12 calls materialize but does not invoke fn_input_governance_curator_handoff_receipt_v1; no SQL producer references, and zero EVIDENCE_VERIFICATION receipts for input_governance_curator_handoff. New Validator requires receipt before first validation chunk.
- Prevención: Do not deploy the deadline Validator/Agent until an actual Curator→handoff receipt→EVIDENCE_VERIFIER VERIFIED→Validator consumer run is proven end-to-end with rollback and fail-closed negative cases. Repair producer at its canonical owner; do not bypass handoff or invent receipt. Preserve deployment backups and use selective sandbox verification.
- Validación: 2026-10-08: deployed Validator v15 and Agent v14 from GitHub, exact-source sandbox resume 8/8 PASS; preflight detected 0 verified handoff receipts and Curator v12 no producer call. Rolled back to original Edge code (Validator deployed v16, Agent deployed v15), verified exact backup parity and verify_jwt. RPC bridge PR #2002 reverted by PR #2004 and migration rollback applied. M8.8 remains 6/7 pending real post-deploy verification. [IG_M88_UPSTREAM_REPAIRED_20261008] PR #2005 merged [REDACTADO]; migration applied, canonical materialize readback producer/consumer guards true; rollback E2E 47/47 families, 5 continuations + COMPLETED sixth, VERIFIED handoff each, 0 residue. PR #2006 merged [REDACTADO]; service_role-only RPC adapters restored. Edge Agent v16 and Validator v17 deployed exact source with verify_jwt; anon HTTP 403. Authenticated Edge E2E and 30-day performance margin remain unproven, hence checkpoint CHUNK_MARGIN_READBACK PENDING.

## LF-NUCLEO-M1-C03-BACKEND-GUARD-20261123-001 — Regla de recibo bloquea backend sin intento de emisión
- Severidad: HIGH · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: RECIBO_EMISION_GUARD_AUSENTE
- Causa raíz: Guard de evento omitido para regla BACKEND
- Prevención: Exigir hecho booleano de intento y probar no-emisión con backend inválido; no inferir persistencia de incidencia sin binding.
- Validación: V2 por REVISION canónica; siete casos sintéticos y mutante sin guard; PG17/rollback.

## LF-NUCLEO-M2L2-UI-SEMANTIC-BINDINGS-PENDING-20261123-001 — M2L2 obligaciones UI de ofertas pendientes de binding
- Severidad: HIGH · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: M2L2_UI_SEMANTIC_BINDINGS_PENDING
- Causa raíz: Migración de textos antes de binding físico con fuente verificable
- Prevención: Exigir binding acreditado de Paulo, señal de intento real, tests de integración y juicio independiente antes de publicar.
- Validación: 7 candidatas; 28 casos; 7 mutantes; PG17 BEGIN/ROLLBACK; no publicar

## LF-NUCLEO-M4C-B2B-AUTH-BINDINGS-PENDING-20261123-001 — M4C controles B2B autenticacion y tenant pendientes de binding
- Severidad: HIGH · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: M4C_B2B_AUTH_BINDINGS_PENDING
- Causa raíz: Migración de textos antes de binding físico con fuente verificable
- Prevención: Exigir binding acreditado de Paulo, señal de intento real, tests de integración y juicio independiente antes de publicar.
- Validación: 8 candidatas; 32 casos; 8 mutantes; PG17 BEGIN/ROLLBACK; no publicar
