# Spring Boot — skill L2

## Propósito
Procedimiento genérico por stack; el catálogo se resuelve por el pin del pedido.

## Entradas
Stack verificado, dominios PG-02, pin PG-01, contrato Fase 1 y manifiesto de arquitectura separados.

## Orden de trabajo
Verificar el contrato de API y el perfil externo antes de implementar. Separar DTO y cambios internos; ejecutar los checks declarados.

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

STD-API-01 [APROBADO]
APIs REST propias (Spring o API propia): prefijo `/api/v1/`. En Supabase la versión va en el nombre de la función (`_vN`)
✅ GET /api/v1/work-requests
❌ GET /work-requests


STD-API-02 [APROBADO]
APIs REST propias — rutas: recursos como sustantivos en plural y kebab-case; acciones solo como subrecurso verbal (`/checkout/confirm`); path params en el casing de D3
✅ GET /api/v1/work-batches/{workBatchId}
❌ GET /api/v1/work_batch/{workBatchId}


STD-API-03 [APROBADO]
Campos JSON, path params y query params en snake_case (D3), consistentes en request y response
✅ {"offer_id": 12, "discount_percent": "15.00"}
❌ {"offerId": 12, "DiscountPercent": 15}


STD-API-04 [APROBADO]
Errores según D1 + D2; nunca stack trace ni SQL
✅ HTTP 500 Content-Type: application/problem+json {"type":"about:blank","title":"Internal Server Error","status":500,"code":"INTERNAL_ERROR","trace_code":"7f3a9c21"}
❌ HTTP 500: {"error":"SELECT * FROM accounts; stack trace ..."}
❌ HTTP 404: {"error_id":17,"message":"texto inventado por el agente"}


STD-API-05 [APROBADO]
Headers: `Idempotency-Key` (D8), `X-Request-Id` y `X-Correlation-Id` (D9), rate limit 429 + `Retry-After`
✅ POST /api/v1/work-requests + Idempotency-Key: example-key; X-Request-Id: example-request; X-Correlation-Id: example-correlation
❌ HTTP 429 without Retry-After


STD-API-06 [APROBADO]
Contrato primero: en Spring, OpenAPI antes del código y cliente FE generado; en Supabase, firma de la función RPC o de la Edge Function definida antes y tipos generados (`supabase gen types`)
✅ Define OpenAPI operation GET /api/v1/work-requests before implementing Spring controller; generate FE client from spec
❌ Implement Spring controller first and manually write incompatible frontend fetch calls


STD-API-07 [APROBADO]
Paginación, filtros y orden con parámetros estándar: REST propia `page`, `size`, `sort`; funciones Supabase `p_limit`, `p_offset`

STD-API-08 [APROBADO]
Montos como texto decimal + `currency` (D10); en BD `numeric(18,2)`
✅ {"amount": "1650.00", "currency": "PEN"}
❌ {"amount": 1650.0}
❌ {"monto": 1650}


STD-API-09 [APROBADO]
Cambio incompatible significa nueva versión, sin romper la anterior: `/api/v2/` en REST propia; `_v2` en Supabase, manteniendo `_v1` hasta que no tenga consumidores
✅ Keep GET /api/v1/work-requests and add GET /api/v2/work-requests for breaking response changes
❌ Replace /api/v1/work-requests response incompatibly without publishing /api/v2/


STD-BE-01 [APROBADO]
Paquetes en minúscula; clases e interfaces en PascalCase; métodos y variables en camelCase; constantes en UPPER_SNAKE

STD-BE-02 [APROBADO]
DTOs separados de las entidades (`…Request`/`…Response`); nunca exponer entidades JPA

STD-BE-03 [APROBADO]
Si el perfil de arquitectura del proyecto (D15) declara módulos, sus límites se verifican con una prueba automatizada en el CI (en Spring Modulith: `ApplicationModules.verify()`). Sin módulos declarados, no aplica.

STD-BE-04 [APROBADO]
Logs técnicos en JSON con el formato estructurado nativo de Spring Boot. Campos mínimos: `timestamp`, `level`, `logger`, `message`, `request_id` y `correlation_id` (D9). Nunca PII (STD-GEN-04). El proyecto puede exigir campos adicionales (L3).

STD-BE-05 [APROBADO]
Formato automático con palantir-java-format (4 espacios, 120 columnas) aplicado con Spotless; el CI y el agente usan el mismo comando
✅ Código que no cambia al correr mvn spotless:apply
❌ Sangría de 2 espacios o líneas de más de 120 columnas que Spotless reescribe


STD-BE-06 [APROBADO]
Toda llamada saliente (HTTP, BD, colas) tiene un timeout explícito tomado de la configuración, nunca un literal en el código ni el valor por defecto sin límite. Solo se reintentan operaciones idempotentes, con límite y espera configurados. La política concreta la fija el proyecto (L3).

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


STD-LOG-01 [APROBADO]
Separar tres destinos: **logs técnicos** en CloudWatch/stdout JSON con retención corta (nunca en la BD); **eventos de auditoría** en BD, append-only; **navegación** en STD-NAV

STD-LOG-02 [APROBADO]
**Una sola copia:** columnas tipadas para lo que se consulta (cuándo, quién, acción, entidad, resultado, `correlation_id`, `trace_code`) y `jsonb` solo para el detalle variable. Prohibido guardar el JSON crudo y además su versión parseada

STD-LOG-03 [APROBADO]
La lectura humana se resuelve con **vistas** que aplanan el JSON por tipo de evento y con consultas guardadas, no duplicando datos

STD-LOG-04 [APROBADO]
Excepción: el payload crudo de un proveedor externo (webhook de pago) se guarda **una vez**, con hash, como prueba. Su versión parseada se obtiene por vista; si es grande, va a S3 con referencia

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

STD-MSG-01 [APROBADO]
Ningún texto de error o éxito escrito en el código: sale del catálogo de mensajes y errores **del propio proyecto** (kit base). En LF: `lf_ops.mensajes_pantallas` y `lf_ops.errores_catalogo`

STD-MSG-02 [APROBADO]
El agente **no redacta ni corrige copy**: usa el texto referenciado en el spec. Si un error o éxito aplicable no trae texto, el resultado es `REQUIRES_DECISION` (vuelve a Fase 1); nunca se inventa

STD-MSG-03 [APROBADO]
Estructura técnica que todo mensaje debe poder mostrar: título, mensaje, acción sugerida con botón y código de referencia (`trace_code`). Qué se muestra en cada caso lo decide el spec
