# Errores conocidos (EKB) para este lote

Consultado por la ruta antes de implementar (T56). Revisa cada uno: si tu cambio puede repetirlo, aplica la prevención y deja la validación como prueba.

## LF-NUCLEO-TANDA3-8-INDEPENDIENTES-20261123-001 — Tanda 3 ocho juicios independientes M4
- Severidad: MEDIUM · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: NUCLEO_TANDA3_JUICIO_INDEPENDIENTE
- Causa raíz: Hechos agregados no prueban binding runtime de seguridad. La fixture lectura IG exige pantalla sin nativas.
- Prevención: Verificar hash version, 4 pruebas y nucleo_hash_paquete_v1, negativo hash adulterado, REG_CHK_007 y legadas intactos, 14/14 lectura IG.
- Validación: PG17 exacto BEGIN ROLLBACK, ocho casos y negativo por caso, 17 regresiones, 14 lectura IG, Train y readback.

## LF-NUCLEO-TANDA5-8-INDEPENDIENTES-20261123-001 — Tanda 5 ocho juicios independientes M4C B2B
- Severidad: MEDIUM · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: NUCLEO_TANDA5_JUICIO_INDEPENDIENTE
- Causa raíz: Hechos agregados de autenticación y permisos no acreditan runtime; límites de archivos aún pendientes de Paulo.
- Prevención: Verificar hash versión, cuatro pruebas y hash canónico en una misma transacción; negativo hash alterado; conservar IG, REG_CHK_007, otras candidatas y legadas.
- Validación: PG17 exacto BEGIN ROLLBACK, ocho positivos y ocho negativos, 17 regresiones, 14 lectura IG, Train y readback.

## LF-NUCLEO-TANDA6-7-JUICIOS-Y-REINTENTO-V4-20261123-001 — Tanda 6: seis PASS y una DEVOLVER + revisión v4
- Severidad: MEDIUM · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: NUCLEO_TANDA6_DEVOLUCION_VERSION_GOBERNADA
- Causa raíz: La descripción v3 presentaba requisitos como alternativas; el backend, las pruebas y la condición requieren todos. REG_TEC_009 borde de idempotencia pendiente de validación runtime de Paulo.
- Prevención: No promover REG_CHK_004 v4 sin otro juicio independiente. Validar en Paulo comportamiento real del borde exacto AUTH/IDEMPOTENCY_KEY_VALIDITY_MINUTES=5 y bindings de usuario, clave, sha y operación.
- Validación: PG17 BEGIN ROLLBACK, hash alterado negativo por 7 reglas, 6 AUTO, v3 DEVUELTA, v4 CANDIDATA no promovida, 17 regresiones y lector IG 14/14.

## LF-NUCLEO-M2L2-UI-SEMANTIC-BINDINGS-PENDING-20261123-001 — M2L2 obligaciones UI de ofertas pendientes de binding
- Severidad: HIGH · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: M2L2_UI_SEMANTIC_BINDINGS_PENDING
- Causa raíz: Migración de textos antes de binding físico con fuente verificable
- Prevención: Exigir binding acreditado de Paulo, señal de intento real, tests de integración y juicio independiente antes de publicar.
- Validación: 7 candidatas; 28 casos; 7 mutantes; PG17 BEGIN/ROLLBACK; no publicar

## LF-NUCLEO-M4-LOGICAL-FACTS-NO-RUNTIME-BINDING-20261123-001 — M4 guards de seguridad con hechos lógicos pendientes de binding
- Severidad: HIGH · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: M4_LOGICAL_GUARD_BINDING_PENDING
- Causa raíz: Migración de textos antes de binding físico con fuente verificable
- Prevención: Exigir binding acreditado de Paulo, señal de intento real, tests de integración y juicio independiente antes de publicar.
- Validación: 8 candidatas; 32 casos; 8 mutantes; PG17 BEGIN/ROLLBACK; no publicar

## LF-NUCLEO-M4B-LOGICAL-FACTS-RUNTIME-PENDING-20261123-001 — M4B guards de OTP y sesion pendientes de binding
- Severidad: HIGH · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: M4B_LOGICAL_GUARD_BINDING_PENDING
- Causa raíz: Migración de textos antes de binding físico con fuente verificable
- Prevención: Exigir binding acreditado de Paulo, señal de intento real, tests de integración y juicio independiente antes de publicar.
- Validación: 8 candidatas; 32 casos; 8 mutantes; PG17 BEGIN/ROLLBACK; no publicar

## LF-NUCLEO-M4C-B2B-AUTH-BINDINGS-PENDING-20261123-001 — M4C controles B2B autenticacion y tenant pendientes de binding
- Severidad: HIGH · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: M4C_B2B_AUTH_BINDINGS_PENDING
- Causa raíz: Migración de textos antes de binding físico con fuente verificable
- Prevención: Exigir binding acreditado de Paulo, señal de intento real, tests de integración y juicio independiente antes de publicar.
- Validación: 8 candidatas; 32 casos; 8 mutantes; PG17 BEGIN/ROLLBACK; no publicar

## LF-PROFILE-HANDOFF-DIRECT-42501-OLD-RUN-SUBSTITUTION-001 — Router entrega Gate2 READY pero agente intenta SQL read-only, obtiene 42501 y reutiliza run antiguo
- Severidad: HIGH · Frecuencia: 1 · Categoría: PROFILE_RUNTIME_GOVERNANCE
- Patrón: READ_ONLY_DIRECT_PROFILE_ADMISSION_AND_HISTORICAL_EXECUTION_SUBSTITUTION
- Causa raíz: El consumer ignora el inicio OIDC/Edge propio de EJECUCION_PERFIL_LF; CLAUDE.md mezclaba el contrato legacy independiente con el modo V3 CURRENT_CONTEXT_REVIEW y no explicitaba BEGIN desde el handoff.
- Prevención: Leer EKB y el runbook de perfiles. Un Gate2 GATE2_DERIVED_PENDING_GOVERNED_ADMISSION/HANDOFF_CONTEXT_TO_SELECTED_PROFILE obliga al agente a generar LF_PROFILE_NATIVE_BEGIN_REQUEST_V1 con router_context sin cambios y executor_mode GPT_NATIVE, crear Issue Github con label lf-profile-resume-governed y dejar que el workflow use GitHub OIDC->Edge->service_role->RPC canónico. No llamar el admit RPC desde supabase_read_only_user, no ampliar ACL, no mover secrets al Router, no crear dispatcher o ruta directa al perfil. Comprobar nuevo execution_id antes de afirmar recepcion; si no existe, NOT_EXECUTED, nunca reutilizar run previo. Continuar con mismo ID y evidencia real por LF_PROFILE_NATIVE_RESUME_REQUEST_V1 (screen/RAW/V3) hasta 11/11 COMPLETED READY, sin repetir autorización dentro del mismo alcance. CURRENT_CONTEXT_REVIEW es solo read_only/no_write/no_promotion, sin independencia simulada.
- Validación: Criterio canónico LF: Router ACT-0001 entrega Gate2 VALID, sin ejecutar el perfil ni transportar credenciales. El perfil inicia una ejecución distinta mediante LF_PROFILE_NATIVE_BEGIN_REQUEST_V1 en GitHub OIDC -> Edge -> RPC autorizado, con service_role exclusivamente dentro de Edge. Las etapas posteriores reutilizan el mismo execution_id y registran screen_selection, RAW real, output_validate y dictamen V3 con procedencia verificable. El cierre requiere exactamente 11/11 STEP_PASS_WITH_EVIDENCE, semantic_judge 70 y report_output 80 con trust_validation válido, ejecución COMPLETED y terminal READY en Supabase. Controles de permisos: supabase_read_only_user sin EXECUTE para admit_v2; service_role con EXECUTE. Evidencia positiva: tres ejecuciones distintas, EXEC-PROFILE-GATE2-31340B34D5B0E320E3B83C00, EXEC-PROFILE-GATE2-93CEF1403D252A61F5EC2AC8 y EXEC-PROFILE-GATE2-1B544082A880C107E66BCBD1; GitHub Actions 41293887404, 41296096617 y 41296832156. Este certificado acredita el transporte y cierre de los perfiles, no modifica reglas de negocio ni acredita producción.

## LF-NUCLEO-586-INVENTARIO-SECURITY-PILOTO-20261123-001 — Inventario 586 y primer piloto SECURITY
- Severidad: MEDIUM · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: NUCLEO_COBERTURA_NO_INFERIDA
- Causa raíz: La columna regla_legacy_id está NULL en 58; origen.ref no certifica cobertura.
- Prevención: Requiere puente N:M de cobertura validada; no promocionar S1-C01 sin juicio Claude.
- Validación: PG17 8 casos y negativo de intento, BEGIN/ROLLBACK, núcleo 17/17, IG 14/14.

## LF-NUCLEO-REG-CHK-007-V2-REVISION-PENDIENTE-20261123-001 — REG_CHK_007 v2 intento y violación
- Severidad: MEDIUM · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: NUCLEO_INTENTO_VIOLACION
- Causa raíz: Condición anterior evaluaba pantalla y no acción de modificación.
- Prevención: Distinguir navegación, intento y violación; no declarar binding runtime; pago pendiente requiere decisión de Cristhian; no promocionar sin juicio.
- Validación: PG17 12 pruebas, negativo v1, BEGIN ROLLBACK exacto, núcleo 17/17, lector IG 14/14.

## LF-NUCLEO-SECURITY-S1C02-S1C06-CANDIDATAS-20261123-001 — SECURITY cinco candidatas sin promover
- Severidad: MEDIUM · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: NUCLEO_SECURITY_CANDIDATE
- Causa raíz: Procedencia legada no equivale a cobertura comprobada ni binding real de backend.
- Prevención: No promover sin juicio independiente y sin test de pantalla legal 36; hechos curados aún sin binding Paulo.
- Validación: PG17 40 casos únicos, 5 negativos hash alterado, rollback exacto, 17 regresiones, IG 14/14.

## LF-NUCLEO-TANDA1-10-JUICIOS-INDEPENDIENTES-20261123-001 — Escalamiento de juicio independiente por tandas sin forzar publicacion
- Severidad: MEDIUM · Frecuencia: 1 · Categoría: NUCLEO_REGLAS
- Patrón: NUCLEO_TANDA1_INDEPENDENT_JUDGE
- Causa raíz: El puntaje de juicio no sustituye el contrato de evaluacion, profundidad y dependencias.
- Prevención: Antes del juicio, comparar version.hash, numero de pruebas y nucleo_hash_paquete_v1 con atestacion; negativo de hash; solo promover AUTO; verificar legadas y otras candidatas intactas.
- Validación: PG17 exacto, mutante hash, BEGIN ROLLBACK, 17 regresiones, Merge Train y readback Supabase.
