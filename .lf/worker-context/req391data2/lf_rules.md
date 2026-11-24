# PostgreSQL / Flyway — skill L2

## Propósito
Procedimiento genérico por stack; el catálogo se resuelve por el pin del pedido.

## Entradas
Stack verificado, dominios PG-02, pin PG-01, contrato Fase 1 y manifiesto de arquitectura separados.

## Orden de trabajo
Verificar contrato de migración y dependencia Flyway desde evidencia de repo. Aplicar pruebas sobre un esquema efímero; no desplegar.

## Verificación
Resolver `check_set_ref` mediante la fuente única de checks. Mantener estados blocking y shadow.

## Salida
Paquete de evidencias, comandos ejecutados y recibo de ensamblado; nunca autodeclarar GO.


STD-GEN-01 [APROBADO]
Identificadores en inglés (D4); glosario obligatorio: un glosario base en `transversal` y un glosario de dominio por proyecto (L3)
✅ String correlationId = request.getHeader("X-Correlation-Id");
❌ String identificadorCorrelacion = request.getHeader("X-Correlation-Id");


STD-GEN-02 [APROBADO]
Nada de configuración, montos, timeouts ni URLs hardcodeados

STD-GEN-03 [APROBADO]
Secretos nunca en código ni en logs; subprocess con entorno allowlist
✅ String apiKey = System.getenv("SERVICE_API_KEY");
✅ ProcessBuilder pb = new ProcessBuilder(command); pb.environment().keySet().retainAll(Set.of("PATH", "LANG"));
❌ private static final String API_KEY = "REDACTED";
❌ logger.info("api_key={}", apiKey);


STD-GEN-04 [APROBADO]
PII fuera de logs, eventos y Sentry
✅ logger.info("request_id={}", requestId);
❌ logger.info("customer_email={}", customerEmail);


STD-GEN-05 [APROBADO]
Toda supresión de lint lleva el id del waiver
✅ // eslint-disable-next-line no-console -- WAIVER-0001 diagnóstico temporal
✅ @SuppressWarnings("unchecked") // WAIVER-0002 API externa sin genéricos
❌ // eslint-disable-next-line no-console
❌ // @ts-ignore


STD-GEN-06 [APROBADO]
Fechas en ISO-8601 con zona y almacenadas en UTC
✅ 2026-10-23T14:30:00Z
❌ 2026-10-23 14:30


STD-GEN-07 [APROBADO]
Los códigos de catálogo provenientes de la Fase 1 se usan literales; la configuración del linter los excluye (por ejemplo, como strings o enums generados desde el catálogo, nunca como identificadores reescritos)

STD-DB-01 [APROBADO]
Tablas y columnas en snake_case minúscula y en inglés (D4); tablas en plural (`debts`, `offers`)
✅ create table offers (...)
✅ column discount_percent
❌ create table Oferta (...)
❌ column DescuentoPct


STD-DB-02 [APROBADO]
PK y FK según D5

STD-DB-03 [APROBADO]
Constraints e índices con el nombre por defecto de Postgres (D6)

STD-DB-04 [APROBADO]
`created_at`/`updated_at` `timestamptz not null default now()` en tablas nuevas; `updated_at` lo mantiene un trigger común del kit base, nunca la aplicación

STD-DB-05 [APROBADO]
Booleanos `is_`/`has_`; enums con tabla catálogo o `CHECK`, sin valores inventados

STD-DB-06 [APROBADO]
RLS activo en toda tabla nueva expuesta, con políticas explícitas

STD-DB-07 [APROBADO]
`SECURITY DEFINER` con EXECUTE revocado de PUBLIC, grants mínimos y `search_path` fijo

STD-DB-08 [APROBADO]
Migración: apply, reapply, rollback y reapply conservando datos; expand/contract para cambios incompatibles

STD-DB-09 [APROBADO]
Nombre de migración: plataforma LF; producto `V<n>__<descripcion_snake>.sql` (Flyway)

STD-DB-10 [APROBADO]
Funciones de la plataforma LF según D7

STD-GIT-01 [APROBADO]
Ramas del agente: `lf/prog-<work_code>/<slug>`, dentro de `lf/**` como indica el protocolo operativo (sandbox: `lf/prog-sandbox/<slug>`)
✅ lf/prog-sandbox/pg00-reglamento-v0-1
✅ lf/prog-PROG-REM-003/estrategia-tecnica
❌ feature/descuentos
❌ main-fix


STD-GIT-02 [APROBADO]
Commits: `<tipo>(<ámbito>): <resumen>` (Conventional Commits), uno por lote

STD-GIT-03 [APROBADO]
Una migración por PR; Router y Train para la BD; PASE obligatorio

STD-SEC-01 [APROBADO]
Toda entrada se valida del lado servidor (tipo, formato, longitud, rango), aunque el frontend ya la valide
✅ public record CreateWorkRequest(@NotBlank @Size(max = 64) String title) {}
✅ ResponseEntity<WorkRequestResponse> create(@Valid @RequestBody CreateWorkRequest body)
❌ ResponseEntity<WorkRequestResponse> create(@RequestBody CreateWorkRequest body) // sin @Valid: solo valida el navegador


STD-SEC-02 [APROBADO]
Autorización verificada en cada endpoint o función, no solo en la pantalla
✅ @PreAuthorize("hasAuthority('work_request:read')") @GetMapping("/api/v1/work-requests/{workRequestId}")
❌ @GetMapping("/api/v1/work-requests/{workRequestId}") // sin control de autorización: la pantalla oculta el botón


STD-SEC-03 [APROBADO]
Dependencias con versión fija (lockfile) y escaneo de vulnerabilidades en CI

STD-SEC-04 [APROBADO]
Límite de intentos en endpoints sensibles (login, OTP, pagos)
✅ POST /api/v1/auth/otp: enforce per-identity attempt limit and return HTTP 429 on excess
❌ POST /api/v1/auth/otp: unlimited verification attempts


STD-AUD-01 [APROBADO]
Auditoría append-only, escrita solo del lado servidor, con `correlation_id` obligatorio, en la tabla de auditoría del propio proyecto (kit base). Antecedente en LF: *B2B-RULE-AUDIT-001*

STD-AUD-02 [APROBADO]
**Qué entidades necesitan historial lo define el spec (Fase 1).** PG-03 verifica que el spec lo haya respondido para cada tabla nueva con datos que cambian; si no, `REQUIRES_DECISION`. Si la respuesta es sí, se usa el patrón estándar: tabla `<entidad>_history` con `valid_from`/`valid_to`, `changed_by`, `correlation_id` y la fila completa (en Spring: Hibernate Envers). Ejemplo vigente del patrón: `lf_client.client_phone_bindings` (`valid_from`/`valid_to`). No se marcan entidades por adelantado

STD-AUD-03 [APROBADO]
Sin PII completa en auditoría ni en historial; definir con legal cómo convive el historial inmutable con el derecho de supresión

STD-NAV-01 [APROBADO]
Qué eventos registrar en cada pantalla lo define el spec. El agente implementa la tabla de eventos de navegación del proyecto: `session_id`, `user_ref` (hash/anónimo), `screen_code`, `event_type` (screen_view, action, submit, error, exit), `occurred_at`, `duration_ms`, `trace_code`, `correlation_id`, canal y dispositivo. Los tipos de evento salen de un catálogo de eventos del propio proyecto, no de texto libre (en LF ya existe: `lf_ops.analytics_eventos_definicion`)

STD-NAV-02 [APROBADO]
Consultas estándar listas para soporte: "dónde se quedó cada sesión" (último evento), tiempo por pantalla, sesiones que terminaron en error, recorrido completo de un `trace_code`

STD-NAV-03 [APROBADO]
Nada de lo que el usuario escribe se guarda; identificadores con hash; retención definida; consentimiento de analítica según la política de cookies (validar con legal)

STD-CONS-01 [VALIDAR_CON_LEGAL] (pendiente, no obligatoria)
Qué se consiente y sus textos los define el spec (con legal); el agente implementa la estructura. `legal_documents`: tipo, versión, hash del texto exacto y vigencia. No se acepta un documento DEMO en producción

STD-CONS-02 [VALIDAR_CON_LEGAL] (pendiente, no obligatoria)
`consents` append-only: cliente, versión del documento, tipo (términos, datos, marketing, cookies), otorga o revoca, fecha y hora UTC, IP, navegador, canal, pantalla y `correlation_id`. Una revocación es una fila nueva, nunca un update. Cada proyecto tiene las suyas, porque cada producto es su propio titular del banco de datos (validar con legal). En LF cubriría el registro pendiente de `LEGAL-CONSENTIMIENTO-DATOS-01` (`canonical_consent_store = PENDING_CANONICAL_REGISTRY`)

STD-CONS-03 [VALIDAR_CON_LEGAL] (pendiente, no obligatoria)
Checkbox desmarcado por defecto; los consentimientos obligatorios bloquean y el de marketing no

STD-CONS-04 [VALIDAR_CON_LEGAL] (pendiente, no obligatoria)
Campos y retención validados por legal antes de producción
