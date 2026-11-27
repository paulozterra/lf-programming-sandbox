# Errores conocidos (EKB) para este lote

Consultado por la ruta antes de implementar (T56). Revisa cada uno: si tu cambio puede repetirlo, aplica la prevención y deja la validación como prueba.

## LF-NUCLEO-TANDA6-7-JUICIOS-Y-REINTENTO-V4-20261123-001 — Tanda 6: seis PASS y una DEVOLVER + revisión v4
- Severidad: MEDIUM · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: NUCLEO_TANDA6_DEVOLUCION_VERSION_GOBERNADA
- Causa raíz: La descripción v3 presentaba requisitos como alternativas; el backend, las pruebas y la condición requieren todos. REG_TEC_009 borde de idempotencia pendiente de validación runtime de Paulo.
- Prevención: No promover REG_CHK_004 v4 sin otro juicio independiente. Validar en Paulo comportamiento real del borde exacto AUTH/IDEMPOTENCY_KEY_VALIDITY_MINUTES=5 y bindings de usuario, clave, sha y operación.
- Validación: PG17 BEGIN ROLLBACK, hash alterado negativo por 7 reglas, 6 AUTO, v3 DEVUELTA, v4 CANDIDATA no promovida, 17 regresiones y lector IG 14/14.

## LF-NUCLEO-M4C-B2B-AUTH-BINDINGS-PENDING-20261123-001 — M4C controles B2B autenticacion y tenant pendientes de binding
- Severidad: HIGH · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: M4C_B2B_AUTH_BINDINGS_PENDING
- Causa raíz: Migración de textos antes de binding físico con fuente verificable
- Prevención: Exigir binding acreditado de Paulo, señal de intento real, tests de integración y juicio independiente antes de publicar.
- Validación: 8 candidatas; 32 casos; 8 mutantes; PG17 BEGIN/ROLLBACK; no publicar

## LF-PROMO-42501-VERDICT-READ-20261114-001 — Lectura de veredictos con permisos minimos
- Severidad: HIGH · Frecuencia: 1 · Categoría: RULE_GOVERNANCE
- Patrón: VERDICT_FUNCTION_NOT_CALLABLE_BY_INSPECTION
- Causa raíz: Falta EXECUTE y USAGE efectiva a la ruta invocadora pese a SECURITY DEFINER.
- Prevención: Ingenieria prepara wrapper SECURITY DEFINER read-only en public, EXECUTE solo service_role, sin grants amplios a anon/authenticated; probar PG17/18.
- Validación: pg_get_functiondef y 42501 observados; wrapper propuesto PR #3898.

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

## LF-NUCLEO-ENGINE-PRODUCT-CONSTANTS-20261121-001 — Motor del núcleo con valores y datos de LF que impedían reutilizarlo en SALY
- Severidad: MEDIUM · Frecuencia: 1 · Categoría: ARCHITECTURE_GOVERNANCE
- Patrón: ENGINE_COUPLED_TO_INSTANCE_DATA
- Causa raíz: El motor y sus pruebas se construyeron con una sola instancia a la vista; los datos de prueba se tomaron del catálogo real en vez de crearse.
- Prevención: Todo valor de producto del motor va en la configuración de la instancia; las autopruebas crean sus propios datos dentro de la subtransacción; una prueba conjunta verifica paridad de código y tablas entre instancias.
- Validación: PR #4483 (motor independiente: 65/65 pruebas, 77/77 mutaciones cubiertas) y PR #4484 (instancia SALY: 65/65 en SALY y LF, conjunto 5/5, 5 divergencias detectadas).

## LF-NUCLEO-TANDA4-8-INDEPENDIENTES-20261123-001 — Tanda 4 ocho juicios independientes M4B
- Severidad: MEDIUM · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: NUCLEO_TANDA4_JUICIO_INDEPENDIENTE
- Causa raíz: Hechos agregados de cooldown, reenvío y expiración no acreditan runtime; claves AUTH deben mantenerse en configuración.
- Prevención: Comparar hash versión, 4 pruebas, hash paquete y parámetros AUTH; negativo hash alterado; conservar IG, REG_CHK_007 y 586 legadas.
- Validación: PG17 BEGIN ROLLBACK, 8 casos y negativos, 17 regresiones, 14 lectura IG, Train y readback.

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

## IG-M96-MIGRATION-VERSION-COLLISION-001 — Colision entre timestamp Git y version existente del ledger
- Severidad: High · Frecuencia: 2 · Categoría: INPUT_GOVERNANCE_EKB
- Patrón: Colision entre timestamp Git y version existente del ledger
- Causa raíz: PR2191 uso version 20261010100000 ya ocupada por t_remed_layer1_test_entry_v3; la fuente era valida pero su version no.
- Prevención: Antes de PR y aplicacion comparar version/nombre en Git y supabase_migrations.schema_migrations; corregir ruta por PR sin alterar SQL.
- Validación: PR2192 renombro a 20261010235001, SQL identico; Git=ledger=DB confirmado; ningun replay de version ajena.

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
