# Catálogo de estándares LF · v0.6.1

> Archivo generado desde `standards/catalog.json` con `standards/tools/render_llm.py`. No editar a mano.

Estado: `BORRADOR_EN_REPO_DE_CALIFICACION`.

## Precedencia

1. L1 (piso que nadie rebaja)
2. Lo que trae el spec de la Fase 1 (reglas tipo A)
3. Contratos existentes y perfil técnico del proyecto (reglas tipo B, por manifiesto)
4. Valor por defecto del catálogo (L2)

**Legado:** Los checks BLOCK se aplican al código nuevo o modificado (diff), con línea base de violaciones medida en PG-06·C4.

## Decisiones

- **D1** (ADR-PROG-STD-001) · Formato de error: `REG_TEC_003` (envelope `{success,data,error,meta}`, VIGENTE) frente al plan M1 del producto (`ProblemDetail`, RFC 9457): (b) para proyectos nuevos: nativo de Spring 6, estándar de la industria, admite varios errores por campo. LF no cambia
- **D2** (ADR-PROG-STD-002) · Códigos de error. Los códigos los crea la Fase 1 en el catálogo del proyecto; el agente no los inventa: (1) Relación en BD por `error_id` numérico + código de texto único. (2) La API expone el código de texto y el `trace_code`, nunca el id interno. (3) Si falta un error en el spec → `REQUIRES_DECISION`. (4) El kit base trae errores técnicos mínimos (interno, servicio no disponible, timeout, datos inválidos, sin permiso, no encontrado); su texto visible es de la Fase 1 y, mientras falte, queda marcado "pendiente de copy", lo que bloquea producción
- **D3** (ADR-PROG-STD-003) · Mayúsculas en campos JSON de la API: snake_case en request, response, path y query params: Supabase lo devuelve así de forma nativa, coincide con las reglas de LF y en Spring es una línea de configuración (Jackson `SNAKE_CASE`). En TypeScript, los tipos generados de la API conservan snake_case; las variables propias del frontend siguen en camelCase
- **D4** (ADR-PROG-STD-004) · Idioma de los identificadores (tablas, columnas, variables, funciones, rutas). No aplica al copy visible (Fase 1, en español) ni a los códigos de catálogo (literales): Inglés: predomina en columnas y en lo más nuevo (`lf_client` 100 % inglés; `created_at`/`updated_at` 100 %), coincide con frameworks y evita tildes y ñ. El glosario de PG-00 fija una sola traducción por término (deuda → `debt`) y PG-11 lo verifica
- **D5** (ADR-PROG-STD-005) · PK de tablas nuevas: `id bigint generated always as identity`; UUID solo si el id se expone fuera o se relaciona con `auth.users`. FK `<entidad>_id` (`payments.debt_id`)
- **D6** (ADR-PROG-STD-006) · Nombres de constraints e índices: Siempre el nombre por defecto de Postgres (`debts_pkey`, `payments_debt_id_fkey`, `payments_debt_id_idx`); sin prefijos propios
- **D7** (ADR-PROG-STD-007) · Nombres de funciones: Esquemas de proyecto: `<verbo>_<objeto>_vN` sin prefijo (`saly.get_debt_summary_v1`). Plataforma LF: `lf_…_vN`
- **D8** (ADR-PROG-STD-008) · Header de idempotencia: `Idempotency-Key` en proyectos nuevos; LF mantiene `X-Idempotency-Key`
- **D9** (ADR-PROG-STD-009) · `request_id` y `correlation_id`: Dos conceptos: `X-Request-Id` por petición HTTP y `X-Correlation-Id` de punta a punta (FE, BE, auditoría, navegación); ambos se devuelven y se guardan en logs y auditoría
- **D10** (ADR-PROG-STD-010) · Montos: API: `"amount": "1650.00", "currency": "PEN"`; BD: `numeric(18,2)`; nunca float
- **D11** (ADR-PROG-STD-011) · Linters en CI: En cada repo: modo sombra y luego bloqueo solo sobre código nuevo o modificado. TS: ESLint + Prettier + `tsc`; Python: ruff + mypy; Postgres: lint de catálogo con SQL sobre la BD migrada; Spectral cuando haya OpenAPI. En `claude-persona-lf-patch`: admitir antes la ruta del workflow en PASE y pasar por el Train
- **D12** (ADR-PROG-STD-012) · ¿Se muestra un código al usuario? `REG_ACC_002` (VIGENTE) prohíbe "códigos de error" en mensajes visibles; `B2B-RULE-ERROR-003` (VIGENTE) exige mostrar `trace_code`: (b): el código técnico (`LF_OTP_EXPIRADO`) nunca se muestra; el de referencia ("Código para soporte: LF-20261021-AB12CD34") sí, porque es lo que permite rastrear el caso
- **D13** (ADR-PROG-STD-013) · Stack con el que se califica la V1 del agente: (b). Calificación primero en el entorno local del plan (`docker compose`: PostgreSQL 17 + Floci que emula AWS) y después en QA de AWS. STD-BE se activa; STD-SB queda solo para proyectos con backend Supabase (como la plataforma LF)
- **D14** (ADR-PROG-STD-014) · Infraestructura como código: qué escribe la Fase 2 y qué la Fase 4: (b). Si una pieza necesita un recurso (cola, bucket, secreto, evento), su IaC va en el mismo PR y se valida contra el emulador local. Red, cómputo, borde, identidad, entornos, secretos reales y promoción son de la Fase 4. El agente nunca aplica en la nube. Para LF ya está escrito así en `infra-terraform/FLOCI-A-AWS.md` (módulo `app-resources` igual en Floci y AWS)
- **D15** (ADR-PROG-STD-015) · Perfil de arquitectura del proyecto (estilo de software, unidades desplegables, arquitectura de nube, Docker, comunicación): (b). Es por proyecto, no del catálogo del agente. Cada proyecto declara su perfil con referencia exacta (repo + commit). Sin perfil vigente → `REQUIRES_DECISION` antes de programar. Salirse del perfil (servicio nuevo, unidad desplegable nueva, otro patrón de comunicación) → decisión humana + ADR, nunca en silencio. LF: `paulozterra/lf-architecture@bbe718c` (monolito modular Core + Payments + Workers; ECS Fargate ARM64, RDS, S3, EventBridge/SQS, Cognito, CloudFront) e `paulozterra/paulozterra-infra-terraform` (subido 21/10)
- **D16** (ADR-PROG-STD-016) · Medición del consumo (tokens y costo del agente): Siempre activa. Cada llamada al modelo registra tokens de entrada, de salida y de caché (lectura y escritura), modelo y costo calculado con una tabla de precios versionada. Se agrega por lote, por pedido y por etapa (planificar, construir, reintentos, dudas, reparación) y se separa el gasto útil del desperdiciado (intentos fallidos, rehacer por paquete vencido o por hallazgo). Hoy el Worker v0.8 ya registra entrada y salida por intento; falta caché y un registro persistente (Supabase vía Train)
- **D17** (ADR-PROG-STD-017) · Modo de optimización del consumo: Se elige por pedido y nunca relaja un control (reglamento, revisiones y pruebas iguales en cualquier modo). Palancas: (1) caché del contexto estable (reglamento, perfil técnico, paquete de Fase 1); (2) contexto mínimo (`CONTEXT_BUDGET_GOVERNANCE`); (3) no redescubrir; (4) freno temprano (PG-09); (5) modelo según dificultad del lote, apagado en V1 hasta que PG-18 demuestre que no baja la calidad. Presupuesto por pedido: aviso al 80 %, al 100 % `REQUIRES_DECISION`; nunca se recorta calidad para entrar en presupuesto. Montos POR DEFINIR con datos de PG-16

## STD-GEN · Transversal (L1)

### STD-GEN-01 · BLOCK (en código nuevo) · CI en modo sombra

Identificadores en inglés (D4); glosario obligatorio: un glosario base en `transversal` y un glosario de dominio por proyecto (L3)
Waiver: prohibido (por defecto)

- ✅ `String correlationId = request.getHeader("X-Correlation-Id");`
- ❌ `String identificadorCorrelacion = request.getHeader("X-Correlation-Id");`

### STD-GEN-02 · BLOCK · control pendiente

Nada de configuración, montos, timeouts ni URLs hardcodeados
Waiver: prohibido (por defecto)

Reglas LF de origen: `REG_LF_BENEFITS_CONFIG_001, B2B-RULE-TIMEOUT-001`

### STD-GEN-03 · BLOCK · control pendiente

Secretos nunca en código ni en logs; subprocess con entorno allowlist
Waiver: prohibido — Secretos y ejecucion segura son invariantes de seguridad

Reglas LF de origen: `PR-SEC-010`

- ✅ `String apiKey = System.getenv("SERVICE_API_KEY"); // entorno permitido por allowlist`
- ❌ `private static final String API_KEY = "sk-example-secret";`

### STD-GEN-04 · BLOCK · control pendiente

PII fuera de logs, eventos y Sentry
Waiver: prohibido — La proteccion de PII es obligatoria

Reglas LF de origen: `REG_AUD_002, REG_OBS_002`

- ✅ `logger.info("request_id={}", requestId);`
- ❌ `logger.info("customer_email={}", customerEmail);`

### STD-GEN-05 · BLOCK · CI en modo sombra

Toda supresión de lint lleva el id del waiver
Waiver: prohibido — El requisito de citar un waiver no admite excepcion recursiva

- ✅ `// eslint-disable-next-line no-console -- WAIVER-0001 diagnóstico temporal`
- ✅ `@SuppressWarnings("unchecked") // WAIVER-0002 API externa sin genéricos`
- ❌ `// eslint-disable-next-line no-console`
- ❌ `// @ts-ignore`

### STD-GEN-06 · BLOCK · control pendiente

Fechas en ISO-8601 con zona y almacenadas en UTC
Waiver: prohibido — ISO-8601 y UTC son invariantes de interoperabilidad

- ✅ `2026-10-23T14:30:00Z`
- ❌ `2026-10-23 14:30`

### STD-GEN-07 · BLOCK · revisor PG-11

Los códigos de catálogo provenientes de la Fase 1 se usan literales; la configuración del linter los excluye (por ejemplo, como strings o enums generados desde el catálogo, nunca como identificadores reescritos)
Waiver: prohibido — Los codigos literales de Fase 1 no pueden alterarse


## STD-DB · PostgreSQL (L2)

### STD-DB-01 · BLOCK · exigido en CI

Tablas y columnas en snake_case minúscula y en inglés (D4); tablas en plural (`debts`, `offers`)
Waiver: prohibido (por defecto)

- ✅ `create table offers (...)`
- ✅ `column discount_percent`
- ❌ `create table Oferta (...)`
- ❌ `column DescuentoPct`

### STD-DB-02 · BLOCK (nuevas) · exigido en CI

PK y FK según D5
Waiver: prohibido (por defecto)

### STD-DB-03 · WARN · exigido en CI

Constraints e índices con el nombre por defecto de Postgres (D6)
Waiver: prohibido (por defecto)

### STD-DB-04 · BLOCK · exigido en CI

`created_at`/`updated_at` `timestamptz not null default now()` en tablas nuevas; `updated_at` lo mantiene un trigger común del kit base, nunca la aplicación
Waiver: prohibido (por defecto)

### STD-DB-05 · WARN · exigido en CI

Booleanos `is_`/`has_`; enums con tabla catálogo o `CHECK`, sin valores inventados
Waiver: prohibido (por defecto)

Reglas LF de origen: `PRV-SQL-008`

### STD-DB-06 · BLOCK · exigido en CI

RLS activo en toda tabla nueva expuesta, con políticas explícitas
Waiver: prohibido — RLS es control esencial de autorizacion

### STD-DB-07 · BLOCK · exigido en CI

`SECURITY DEFINER` con EXECUTE revocado de PUBLIC, grants mínimos y `search_path` fijo
Waiver: prohibido (por defecto)

Reglas LF de origen: `PR-SEC-011`

### STD-DB-08 · BLOCK · exigido en CI

Migración: apply, reapply, rollback y reapply conservando datos; expand/contract para cambios incompatibles
Waiver: prohibido — Las migraciones deben preservar datos y reversibilidad

Reglas LF de origen: `PRV-SQL-001`, `PRV-SQL-006`

### STD-DB-09 · BLOCK · exigido en CI

Nombre de migración: plataforma LF; producto `V<n>__<descripcion_snake>.sql` (Flyway)
Waiver: prohibido (por defecto)

Reglas LF de origen: `POL-LF-MIGRATION-NAMING`

### STD-DB-10 · WARN · control pendiente

Funciones de la plataforma LF según D7
Waiver: prohibido (por defecto)


## STD-API · Contrato HTTP (L1/L2)

### STD-API-01 · BLOCK · control pendiente

APIs REST propias (Spring o API propia): prefijo `/api/v1/`. En Supabase la versión va en el nombre de la función (`_vN`)
Waiver: prohibido (por defecto)

Reglas LF de origen: `antecedente REG_API_001`

- ✅ `GET /api/v1/work-requests`
- ❌ `GET /work-requests`

### STD-API-02 · BLOCK · control pendiente

APIs REST propias — rutas: recursos como sustantivos en plural y kebab-case; acciones solo como subrecurso verbal (`/checkout/confirm`); path params en el casing de D3
Waiver: prohibido (por defecto)

- ✅ `GET /api/v1/work-batches/{workBatchId}`
- ❌ `GET /api/v1/work_batch/{workBatchId}`

### STD-API-03 · BLOCK · control pendiente

Campos JSON, path params y query params en snake_case (D3), consistentes en request y response
Waiver: prohibido (por defecto)

- ✅ `{"offer_id": 12, "discount_percent": "15.00"}`
- ❌ `{"offerId": 12, "DiscountPercent": 15}`

### STD-API-04 · BLOCK · control pendiente

Errores según D1 + D2; nunca stack trace ni SQL
Waiver: prohibido — Nunca exponer SQL ni stack traces

Reglas LF de origen: `REG_TEC_010`

- ✅ `HTTP 500: {"code":"INTERNAL_ERROR","message":"Request could not be completed"}`
- ❌ `HTTP 500: {"error":"SELECT * FROM accounts; stack trace ..."}`

### STD-API-05 · BLOCK · control pendiente

Headers: `Idempotency-Key` (D8), `X-Request-Id` y `X-Correlation-Id` (D9), rate limit 429 + `Retry-After`
Waiver: prohibido (por defecto)

Reglas LF de origen: `REG_API_005`

- ✅ `POST /api/v1/work-requests + Idempotency-Key: example-key; X-Request-Id: example-request; X-Correlation-Id: example-correlation`
- ❌ `HTTP 429 without Retry-After`

### STD-API-06 · BLOCK · control pendiente

Contrato primero: en Spring, OpenAPI antes del código y cliente FE generado; en Supabase, firma de la función RPC o de la Edge Function definida antes y tipos generados (`supabase gen types`)
Waiver: prohibido (por defecto)

- ✅ `Define OpenAPI operation GET /api/v1/work-requests before implementing Spring controller; generate FE client from spec`
- ❌ `Implement Spring controller first and manually write incompatible frontend fetch calls`

### STD-API-07 · WARN · control pendiente

Paginación, filtros y orden con parámetros estándar: REST propia `page`, `size`, `sort`; funciones Supabase `p_limit`, `p_offset`
Waiver: prohibido (por defecto)

### STD-API-08 · BLOCK · control pendiente

Montos como texto decimal + `currency` (D10); en BD `numeric(18,2)`
Waiver: prohibido (por defecto)

- ✅ `{"amount": "1650.00", "currency": "PEN"}`
- ❌ `{"amount": 1650.0}`
- ❌ `{"monto": 1650}`

### STD-API-09 · BLOCK · control pendiente

Cambio incompatible significa nueva versión, sin romper la anterior: `/api/v2/` en REST propia; `_v2` en Supabase, manteniendo `_v1` hasta que no tenga consumidores
Waiver: prohibido (por defecto)

- ✅ `Keep GET /api/v1/work-requests and add GET /api/v2/work-requests for breaking response changes`
- ❌ `Replace /api/v1/work-requests response incompatibly without publishing /api/v2/`


## STD-BE · Java / Spring Boot (L2) · PENDIENTE_REVISION

### STD-BE-01 · BLOCK · control pendiente

Paquetes en minúscula; clases e interfaces en PascalCase; métodos y variables en camelCase; constantes en UPPER_SNAKE
Waiver: prohibido (por defecto)

### STD-BE-02 · BLOCK · control pendiente

DTOs separados de las entidades (`…Request`/`…Response`); nunca exponer entidades JPA
Waiver: prohibido (por defecto)

### STD-BE-03 · BLOCK · control pendiente

Si el perfil de arquitectura del proyecto (D15) declara módulos, sus límites se verifican con una prueba automatizada en el CI (en Spring Modulith: `ApplicationModules.verify()`). Sin módulos declarados, no aplica.
Waiver: prohibido (por defecto)

### STD-BE-04 · BLOCK · control pendiente

Logs técnicos en JSON con el formato estructurado nativo de Spring Boot. Campos mínimos: `timestamp`, `level`, `logger`, `message`, `request_id` y `correlation_id` (D9). Nunca PII (STD-GEN-04). El proyecto puede exigir campos adicionales (L3).
Waiver: prohibido (por defecto)

Reglas LF de origen: `REG_TEC_012`

### STD-BE-05 · BLOCK · CI en modo sombra

Formato automático con palantir-java-format (4 espacios, 120 columnas) aplicado con Spotless; el CI y el agente usan el mismo comando
Waiver: permitido

- ✅ `Código que no cambia al correr mvn spotless:apply`
- ❌ `Sangría de 2 espacios o líneas de más de 120 columnas que Spotless reescribe`

### STD-BE-06 · BLOCK · revisor PG-11

Toda llamada saliente (HTTP, BD, colas) tiene un timeout explícito tomado de la configuración, nunca un literal en el código ni el valor por defecto sin límite. Solo se reintentan operaciones idempotentes, con límite y espera configurados. La política concreta la fija el proyecto (L3).
Waiver: prohibido (por defecto)

Reglas LF de origen: `B2B-RULE-TIMEOUT-001`


## STD-FE · Next.js + TypeScript (L2)

### STD-FE-01 · BLOCK · control pendiente

Componentes y tipos en PascalCase; hooks `useX`; variables y funciones en camelCase; constantes en UPPER_SNAKE; sin prefijo `I` en interfaces. Excepción: las propiedades de los tipos generados de la API se mantienen en snake_case (D3)
Waiver: prohibido (por defecto)

### STD-FE-02 · BLOCK · CI en modo sombra

Todos los archivos en kebab-case (`b2b-shell.tsx`, `client-session.ts`), como ya usa `libertad-financiera`; el componente dentro del archivo sigue en PascalCase
Waiver: permitido

- ✅ `src/components/b2b-shell/b2b-shell.tsx`
- ✅ `src/lib/auth/client-session.ts`
- ❌ `src/components/B2BShell.tsx`
- ❌ `src/lib/auth/clientSession.ts`

### STD-FE-03 · BLOCK · exigido en CI

TypeScript `strict`, sin `any` implícito ni `@ts-ignore` sin waiver
Waiver: permitido solo para @ts-ignore, @ts-expect-error

### STD-FE-04 · BLOCK · control pendiente

Llamadas a la API solo con el cliente o los tipos generados (`api-client` desde OpenAPI, o `supabase gen types`); nada de `fetch` a mano
Waiver: prohibido (por defecto)

### STD-FE-05 · BLOCK · revisor PG-11

El FE no recalcula precios ni montos
Waiver: prohibido (por defecto)

Reglas LF de origen: `REG_PRI_002`

### STD-FE-06 · BLOCK_OR_WARN · control pendiente

Accesibilidad, responsive y Core Web Vitals
Waiver: prohibido (por defecto)

Reglas LF de origen: `reglas ACCESSIBILITY/RESPONSIVE, REG_OBS_004`

### STD-FE-07 · BLOCK · CI en modo sombra

Formato
Waiver: permitido

- ✅ `Código que no cambia al correr prettier --write`
- ❌ `Comillas, comas o saltos de línea distintos a los que deja Prettier`


## STD-PY · Python (L2)

### STD-PY-01 · BLOCK (en código nuevo) · control pendiente

PEP 8: funciones y variables en snake_case, clases en PascalCase, constantes en UPPER_SNAKE
Waiver: prohibido (por defecto)

### STD-PY-02 · BLOCK · control pendiente

Formato
Waiver: prohibido (por defecto)

### STD-PY-03 · BLOCK · control pendiente

Type hints en funciones públicas + typecheck (activar `PR-PROG-005`, hoy inactiva)
Waiver: prohibido (por defecto)


## STD-GIT · Repositorio (L1)

### STD-GIT-01 · BLOCK · CI en modo sombra

Ramas del agente: `lf/prog-<work_code>/<slug>`, dentro de `lf/**` como indica el protocolo operativo (sandbox: `lf/prog-sandbox/<slug>`)
Waiver: prohibido (por defecto)

- ✅ `lf/prog-sandbox/pg00-reglamento-v0-1`
- ✅ `lf/prog-PROG-REM-003/estrategia-tecnica`
- ❌ `feature/descuentos`
- ❌ `main-fix`

### STD-GIT-02 · WARN · control pendiente

Commits: `<tipo>(<ámbito>): <resumen>` (Conventional Commits), uno por lote
Waiver: prohibido (por defecto)

### STD-GIT-03 · BLOCK · control pendiente

Una migración por PR; Router y Train para la BD; PASE obligatorio
Waiver: prohibido — Train, Router y PASE son controles de autoridad


## STD-SB · Backend Supabase (L2)

### STD-SB-01 · BLOCK · control pendiente

Funciones SQL del proyecto: `<esquema>.<verbo>_<objeto>_vN`, `SECURITY INVOKER` por defecto (DEFINER solo con justificación y STD-DB-07)
Waiver: prohibido (por defecto)

### STD-SB-02 · BLOCK · control pendiente

Superficie expuesta mínima: el frontend solo llama funciones RPC o Edge Functions declaradas como API; nunca tablas directas sin RLS y política explícita
Waiver: prohibido — La superficie de datos exige RLS y politicas

### STD-SB-03 · WARN · control pendiente

Políticas RLS nombradas `<tabla>__<rol>__<acción>` y una por acción
Waiver: prohibido (por defecto)

### STD-SB-04 · BLOCK · control pendiente

Edge Functions en kebab-case con versión (`<dominio>-<acción>-vN`, patrón observado); responden errores con el formato D1
Waiver: prohibido (por defecto)

### STD-SB-05 · BLOCK · control pendiente

Tipos generados con `supabase gen types` versionados; el frontend usa solo esos tipos
Waiver: prohibido (por defecto)

### STD-SB-06 · BLOCK · control pendiente

Parámetros de funciones con prefijo `p_` y variables PL/pgSQL con `v_` (patrón del 98 % de las funciones de LF; previene el error de `PRV-SQL-013`)
Waiver: prohibido (por defecto)


## STD-SEC · Seguridad de aplicación (L1)

### STD-SEC-01 · BLOCK · control pendiente

Toda entrada se valida del lado servidor (tipo, formato, longitud, rango), aunque el frontend ya la valide
Waiver: prohibido — Validar entradas del lado servidor es obligatorio

- ✅ `server.validate(input, { type: "string", maxLength: 64 });`
- ❌ `// Only browser checks input length; server persists unchecked input`

### STD-SEC-02 · BLOCK · control pendiente

Autorización verificada en cada endpoint o función, no solo en la pantalla
Waiver: prohibido — La autorizacion por endpoint es obligatoria

- ✅ `if (!authorization.canRead(actor, resource)) return forbidden();`
- ❌ `// UI hides button; backend handler returns protected resource unconditionally`

### STD-SEC-03 · BLOCK (para severidad alta) · control pendiente

Dependencias con versión fija (lockfile) y escaneo de vulnerabilidades en CI
Waiver: prohibido (por defecto)

### STD-SEC-04 · BLOCK (cuando aplica) · control pendiente

Límite de intentos en endpoints sensibles (login, OTP, pagos)
Waiver: prohibido — Rate limits en operaciones sensibles son obligatorios

- ✅ `POST /api/v1/auth/otp: enforce per-identity attempt limit and return HTTP 429 on excess`
- ❌ `POST /api/v1/auth/otp: unlimited verification attempts`


## STD-LOG · Logs y eventos (L1)

### STD-LOG-01 · BLOCK · revisor PG-11

Separar tres destinos: **logs técnicos** en CloudWatch/stdout JSON con retención corta (nunca en la BD); **eventos de auditoría** en BD, append-only; **navegación** en STD-NAV
Waiver: prohibido (por defecto)

### STD-LOG-02 · BLOCK · control pendiente

**Una sola copia:** columnas tipadas para lo que se consulta (cuándo, quién, acción, entidad, resultado, `correlation_id`, `trace_code`) y `jsonb` solo para el detalle variable. Prohibido guardar el JSON crudo y además su versión parseada
Waiver: prohibido (por defecto)

### STD-LOG-03 · WARN · revisor PG-11

La lectura humana se resuelve con **vistas** que aplanan el JSON por tipo de evento y con consultas guardadas, no duplicando datos
Waiver: prohibido (por defecto)

### STD-LOG-04 · BLOCK · revisor PG-11

Excepción: el payload crudo de un proveedor externo (webhook de pago) se guarda **una vez**, con hash, como prueba. Su versión parseada se obtiene por vista; si es grande, va a S3 con referencia
Waiver: prohibido (por defecto)


## STD-AUD · Auditoría e historial de valores (L1)

### STD-AUD-01 · BLOCK · control pendiente

Auditoría append-only, escrita solo del lado servidor, con `correlation_id` obligatorio, en la tabla de auditoría del propio proyecto (kit base). Antecedente en LF: *B2B-RULE-AUDIT-001*
Waiver: prohibido — La auditoria append-only no es dispensable

### STD-AUD-02 · BLOCK (si la pregunta queda sin responder) · revisor PG-11

**Qué entidades necesitan historial lo define el spec (Fase 1).** PG-03 verifica que el spec lo haya respondido para cada tabla nueva con datos que cambian; si no, `REQUIRES_DECISION`. Si la respuesta es sí, se usa el patrón estándar: tabla `<entidad>_history` con `valid_from`/`valid_to`, `changed_by`, `correlation_id` y la fila completa (en Spring: Hibernate Envers). Ejemplo vigente del patrón: `lf_client.client_phone_bindings` (`valid_from`/`valid_to`). No se marcan entidades por adelantado
Waiver: prohibido (por defecto)

### STD-AUD-03 · BLOCK · revisor PG-11

Sin PII completa en auditoría ni en historial; definir con legal cómo convive el historial inmutable con el derecho de supresión
Waiver: prohibido — No se permite PII completa en auditoria

Reglas LF de origen: `REG_AUD_002`


## STD-NAV · Recorrido del usuario (L1)

### STD-NAV-01 · BLOCK (cuando el proyecto tiene UI) · control pendiente

Qué eventos registrar en cada pantalla lo define el spec. El agente implementa la tabla de eventos de navegación del proyecto: `session_id`, `user_ref` (hash/anónimo), `screen_code`, `event_type` (screen_view, action, submit, error, exit), `occurred_at`, `duration_ms`, `trace_code`, `correlation_id`, canal y dispositivo. Los tipos de evento salen de un catálogo de eventos del propio proyecto, no de texto libre (en LF ya existe: `lf_ops.analytics_eventos_definicion`)
Waiver: prohibido (por defecto)

### STD-NAV-02 · BLOCK · control pendiente

Consultas estándar listas para soporte: "dónde se quedó cada sesión" (último evento), tiempo por pantalla, sesiones que terminaron en error, recorrido completo de un `trace_code`
Waiver: prohibido (por defecto)

### STD-NAV-03 · BLOCK · revisor PG-11

Nada de lo que el usuario escribe se guarda; identificadores con hash; retención definida; consentimiento de analítica según la política de cookies (validar con legal)
Waiver: prohibido (por defecto)


## STD-CONS · Términos, condiciones y consentimientos (L1) · VALIDAR_CON_LEGAL

### STD-CONS-01 · BLOCK · control pendiente

Qué se consiente y sus textos los define el spec (con legal); el agente implementa la estructura. `legal_documents`: tipo, versión, hash del texto exacto y vigencia. No se acepta un documento DEMO en producción
Waiver: prohibido — Consentimiento legal vigente no es dispensable

Reglas LF de origen: `REG_CLIENT_DOC_DEMO_VERSIONING_001`

### STD-CONS-02 · BLOCK · control pendiente

`consents` append-only: cliente, versión del documento, tipo (términos, datos, marketing, cookies), otorga o revoca, fecha y hora UTC, IP, navegador, canal, pantalla y `correlation_id`. Una revocación es una fila nueva, nunca un update. Cada proyecto tiene las suyas, porque cada producto es su propio titular del banco de datos (validar con legal). En LF cubriría el registro pendiente de `LEGAL-CONSENTIMIENTO-DATOS-01` (`canonical_consent_store = PENDING_CANONICAL_REGISTRY`)
Waiver: prohibido — Integridad de consentimientos y revocaciones obligatoria

### STD-CONS-03 · BLOCK · control pendiente

Checkbox desmarcado por defecto; los consentimientos obligatorios bloquean y el de marketing no
Waiver: prohibido — Consentimiento explicito y opt-in obligatorios

Reglas LF de origen: `REG_ONB_003, LEGAL-CONSENTIMIENTO-DATOS-01`

### STD-CONS-04 · BLOCK (para producción) · revisor PG-11

Campos y retención validados por legal antes de producción
Waiver: prohibido — La revision legal no es dispensable


## STD-MSG · Mensajes al usuario (L1)

### STD-MSG-01 · BLOCK · control pendiente

Ningún texto de error o éxito escrito en el código: sale del catálogo de mensajes y errores **del propio proyecto** (kit base). En LF: `lf_ops.mensajes_pantallas` y `lf_ops.errores_catalogo`
Waiver: prohibido (por defecto)

### STD-MSG-02 · BLOCK · control pendiente

El agente **no redacta ni corrige copy**: usa el texto referenciado en el spec. Si un error o éxito aplicable no trae texto, el resultado es `REQUIRES_DECISION` (vuelve a Fase 1); nunca se inventa
Waiver: prohibido — El agente no puede inventar copy de Fase 1

### STD-MSG-03 · BLOCK · control pendiente

Estructura técnica que todo mensaje debe poder mostrar: título, mensaje, acción sugerida con botón y código de referencia (`trace_code`). Qué se muestra en cada caso lo decide el spec
Waiver: prohibido (por defecto)


## STD-IAC · Infraestructura como código (L1)

### STD-IAC-01 · POR_DEFINIR · control pendiente

La IaC de los recursos que pide una funcionalidad va en el mismo PR que el código que los usa
Waiver: prohibido (por defecto)

### STD-IAC-02 · POR_DEFINIR · control pendiente

Un mismo módulo para local (emulador) y nube; solo cambian proveedor y variables
Waiver: prohibido (por defecto)

### STD-IAC-03 · POR_DEFINIR · control pendiente

Ningún endpoint de nube, nombre de recurso ni secreto escrito en el código; todo por variables de entorno
Waiver: prohibido (por defecto)

### STD-IAC-04 · POR_DEFINIR · control pendiente

Nombres y etiquetas obligatorias según la convención del proyecto (L3)
Waiver: prohibido (por defecto)

### STD-IAC-05 · POR_DEFINIR · control pendiente

Validación en PG-08: `fmt`, `validate`, lint de IaC y `plan`/`apply` contra el emulador local
Waiver: prohibido (por defecto)

### STD-IAC-06 · POR_DEFINIR · control pendiente

El agente nunca aplica en la nube; eso es Fase 4 con `plan` revisado por una persona
Waiver: prohibido (por defecto)

### STD-IAC-07 · POR_DEFINIR · control pendiente

Solo servicios y patrones del perfil de arquitectura (D15); otro → `REQUIRES_DECISION`
Waiver: prohibido (por defecto)


## STD-CONT · Contenedores (L1)

### STD-CONT-01 · POR_DEFINIR · control pendiente

Una imagen por unidad desplegable del perfil de arquitectura; la misma imagen en local y en la nube
Waiver: prohibido (por defecto)

### STD-CONT-02 · POR_DEFINIR · control pendiente

Build multi-etapa, versiones de imagen base fijadas, plataforma según el perfil (LF: ARM64)
Waiver: prohibido (por defecto)

### STD-CONT-03 · POR_DEFINIR · control pendiente

La imagen no corre como root, expone healthcheck y no contiene secretos
Waiver: prohibido (por defecto)

### STD-CONT-04 · POR_DEFINIR · control pendiente

`docker compose` local refleja las unidades del perfil; no se emula el orquestador de la nube
Waiver: prohibido (por defecto)
