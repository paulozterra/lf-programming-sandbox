# Glosario ES→EN · v0.1.0

> Generado desde `standards/glossary/*.json` con `standards/tools/glossary.py render`. No editar a mano.

Digest: `1310962f09a7b8f4d976baafe85a405396e3889cbce7ba1b8ce1b4b94080d65f`

**Precedencia de nombres:** contrato existente consumido > glosario del proyecto > glosario base > propuesta nueva (`REQUIRES_DECISION`). Una forma heredada vale solo en sus contratos exactos.

## Glosario base (L1) · `APROBADO_EN_REPO_DE_CALIFICACION`

### estado → `status` · GLOSS-BASE-STATUS-001 · APROBADO

Situación de una entidad dentro de su ciclo de vida (p. ej. pago aprobado, deuda cerrada). Plural: `statuses`. Contextos: domain, database, api.
- Rechazado `state` en database, api: En BD y API la situación de negocio es status.
- Nota: state se permite para el estado interno de máquinas de estado y del frontend (p. ej. useState); no es alternativa libre a status.
- ✅ `payment_status`
- ❌ `payment_state (en BD o API)`
- ❌ `estado_pago`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-15; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-23; supabase: status en 255 columnas · Decisión: GLOSS-DEC-LF-001

### monto → `amount` · GLOSS-BASE-AMOUNT-001 · APROBADO

Cantidad de dinero; en API texto decimal más currency, en BD numeric(18,2) (D10). Plural: `amounts`. Contextos: domain, database, api.
Sinónimos en español: importe.
- ✅ `paid_amount`
- ❌ `monto_pagado`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-16; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-26; D10 · Decisión: GLOSS-DEC-LF-001

### moneda → `currency` · GLOSS-BASE-CURRENCY-001 · APROBADO

Moneda de un monto, como código ISO 4217 (p. ej. PEN) (D10). Plural: `currencies`. Contextos: domain, database, api.
- Rechazado `currency_code` en api: D10 fija currency en la API.
- ✅ `currency`
- ❌ `moneda`
- ❌ `currency_code (en API)`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RNF-41; D10 · Decisión: GLOSS-DEC-LF-001

### usuario → `user` · GLOSS-BASE-USER-001 · APROBADO

Persona que inicia sesión en el sistema (backoffice o portal). Plural: `users`. Contextos: domain, database, api.
- ✅ `user_id`
- ❌ `usuario_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-03; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-06; supabase: user en 31 columnas y 9 tablas · Decisión: GLOSS-DEC-LF-001

### rol → `role` · GLOSS-BASE-ROLE-001 · APROBADO

Conjunto de permisos que se asigna a un usuario (RBAC). Plural: `roles`. Contextos: domain, database, api.
- ✅ `user_role`
- ❌ `rol_usuario`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-04 · Decisión: GLOSS-DEC-LF-001

### permiso → `permission` · GLOSS-BASE-PERMISSION-001 · APROBADO

Autorización para realizar una operación. Plural: `permissions`. Contextos: domain, database, api.
- Heredado `permisos` solo en: `lf_ops.permisos`, `lf_ops.perfiles_permisos`, `lf_ops.menu_items_permisos`, `lf_ops.pantallas_permisos`, `lf_ops.empresa_usuarios_permisos`.
- ✅ `permission_id`
- ❌ `permiso_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-04; supabase: permission en 15 columnas · Decisión: GLOSS-DEC-LF-001

### aprobación → `approval` · GLOSS-BASE-APPROVAL-001 · APROBADO

Autorización explícita de una persona para que una operación continúe. Plural: `approvals`. Contextos: domain, database, api.
- Heredado `aprobaciones` solo en: `lf_ops.aprobaciones_registros`.
- Heredado `aprobacion` solo en: `lf_ops.politicas_aprobacion`.
- ✅ `approval_status`
- ❌ `aprobacion_estado`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-08; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-27; supabase: approval en 10 columnas · Decisión: GLOSS-DEC-LF-001


## Glosario del proyecto LF (L3) · `CANDIDATO_EN_REPO_DE_CALIFICACION`

### empresa compradora → `company` · GLOSS-LF-COMPANY-001 · APROBADO

Empresa que compra cartera y opera en LF; cada una es un tenant aislado. Plural: `companies`. Contextos: domain, database, api.
Sinónimos en español: empresa.
- Rechazado `tenant` en domain, api: tenant es el concepto técnico de aislamiento (RLS, autorización), no la entidad.
- Rechazado `organization` en domain, database, api: Alternativa descartada en el Lote 1.
- Heredado `empresas` solo en: `lf_ops.empresas`.
- Heredado `empresa` solo en: `lf_ops.empresa_usuarios`, `lf_ops.empresa_usuarios_perfiles`, `lf_ops.empresa_usuarios_permisos`.
- Nota: tenant se reserva para aislamiento multi-tenant, autorización y partición lógica (en BD sí se permite, p. ej. políticas RLS).
- ✅ `company_id`
- ❌ `tenant_id como entidad de negocio`
- ❌ `empresa_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-05; supabase: company en 15 columnas y 5 tablas · Decisión: GLOSS-DEC-LF-001

### cliente deudor → `customer` · GLOSS-LF-CUSTOMER-001 · APROBADO

Persona que tiene una deuda gestionada en LF y la consulta o paga en el portal. Plural: `customers`. Contextos: domain, database, api.
Sinónimos en español: cliente, deudor, titular.
- Rechazado `client` en domain, database, api: Ambiguo en código (cliente HTTP, de API, app OAuth).
- Rechazado `debtor` en domain, database, api: Alternativa descartada en el Lote 1.
- Heredado `client` solo en: `lf_client.client_accounts`, `lf_client.client_auth_sessions`, `lf_client.client_phone_bindings`, `lf_client.client_accounts.client_id`, `lf_client.client_auth_sessions.client_id`, `lf_client.client_phone_bindings.client_id`, `lf_client.onboarding_sessions.client_id`, `lf_client.security_events.client_id`.
- Nota: La excepción client vale solo para esos objetos exactos; no autoriza nombres nuevos en el esquema lf_client.
- ✅ `customer_id`
- ❌ `client_id (fuera de los contratos heredados)`
- ❌ `deudor_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-01; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-15 · Decisión: GLOSS-DEC-LF-001

### deuda → `debt` · GLOSS-LF-DEBT-001 · APROBADO

Obligación de pago de un cliente con una empresa compradora de cartera. Plural: `debts`. Contextos: domain, database, api.
Sinónimos en español: adeudo.
- Nota: Contexto dominio: no confundir con deuda técnica (p. ej. v_lf_event_contract_debt_v3). loan (préstamo) es otro concepto y no está prohibido.
- ✅ `debt_id`
- ❌ `deuda_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-15; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-25 · Decisión: GLOSS-DEC-LF-001

### cartera → `portfolio` · GLOSS-LF-PORTFOLIO-001 · APROBADO

Conjunto de deudas que una empresa carga y gestiona en LF. Plural: `portfolios`. Contextos: domain, database, api.
- ✅ `portfolio_id`
- ❌ `cartera_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-07; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-08 · Decisión: GLOSS-DEC-LF-001

### carga de cartera → `portfolio_load` · GLOSS-LF-PORTFOLIO-LOAD-001 · APROBADO

Proceso o lote que incorpora una cartera al dominio a partir de un archivo. Plural: `portfolio_loads`. Contextos: domain, database, api.
Sinónimos en español: carga.
- Rechazado `portfolio_upload` en domain, database, api: upload es la transferencia del archivo, no el lote de carga.
- Heredado `cargas` solo en: `lf_ops.cargas_lotes`, `lf_ops.cargas_archivos`.
- Nota: upload se usa solo para la transferencia del archivo (p. ej. upload_url).
- ✅ `portfolio_load_id`
- ❌ `portfolio_upload_id`
- ❌ `carga_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-07; supabase: vistas lf_ops.v_b2b_rel_load_* · Decisión: GLOSS-DEC-LF-001

### segmento → `segment` · GLOSS-LF-SEGMENT-001 · APROBADO

Grupo de deudas o clientes definido por variables y rangos. Plural: `segments`. Contextos: domain, database, api.
- ✅ `segment_id`
- ❌ `segmento_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-09 · Decisión: GLOSS-DEC-LF-001

### oferta → `offer` · GLOSS-LF-OFFER-001 · APROBADO

Propuesta de pago (único o en cuotas) que se presenta al cliente, con vigencia. Plural: `offers`. Contextos: domain, database, api.
- ✅ `offer_id`
- ❌ `oferta_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-12; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-17; supabase: offer en 4 columnas · Decisión: GLOSS-DEC-LF-001

### cuota → `installment` · GLOSS-LF-INSTALLMENT-001 · APROBADO

Cada pago parcial de un plan en cuotas. Plural: `installments`. Contextos: domain, database, api.
- ✅ `installment_number`
- ❌ `cuota_numero`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-12; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-16 · Decisión: GLOSS-DEC-LF-001

### pago → `payment` · GLOSS-LF-PAYMENT-001 · APROBADO

Intento o transacción de pago de una deuda, oferta o cuota. Plural: `payments`. Contextos: domain, database, api.
- ✅ `payment_id`
- ❌ `pago_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-20; supabase: payment en 2 columnas · Decisión: GLOSS-DEC-LF-001
