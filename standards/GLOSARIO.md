# Glosario ES→EN · v0.3.0

> Generado desde `standards/glossary/*.json` con `standards/tools/glossary.py render`. No editar a mano.

Digest: `69e392b388e5393aa420f454a6417269cb6994a45a9bd3de363e9b03f2e30134`

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

### error → `error` · GLOSS-BASE-ERROR-001 · APROBADO

Representa una categoría de error que el proyecto referencia mediante un código técnico. Plural: `errors`. Contextos: domain, database, api.
- Nota: Homógrafo español/inglés: error se excluye de la detección española; se comprueba con el vocabulario canónico.
- ✅ `error_id`
- ❌ `errores`
- Fuentes: STD-MSG-01 · Decisión: GLOSS-DEC-BASE-002

### ocurrencia de error → `error_occurrence` · GLOSS-BASE-ERROR-OCCURRENCE-001 · APROBADO

Registra una instancia trazable de un error generado durante una solicitud. Plural: `error_occurrences`. Contextos: domain, database, api.
- ✅ `error_occurrence_id`
- ❌ `ocurrencia_id`
- ❌ `ocurrencias`
- Fuentes: D2 · Decisión: GLOSS-DEC-BASE-002

### mensaje → `message` · GLOSS-BASE-MESSAGE-001 · APROBADO

Identifica un mensaje de la interfaz cuyo contenido autoriza la Fase 1. Plural: `messages`. Contextos: domain, database, api.
- Rechazado `msg` en database, api: La abreviatura no es el nombre canónico message..
- ✅ `message_id`
- ❌ `mensaje`
- ❌ `msg`
- Fuentes: STD-MSG-01 · Decisión: GLOSS-DEC-BASE-002

### acción sugerida → `suggested_action` · GLOSS-BASE-SUGGESTED-ACTION-001 · APROBADO

Identifica la acción opcional que acompaña a un mensaje visible. Plural: `suggested_actions`. Contextos: domain, database, api.
- ✅ `suggested_action_id`
- ❌ `accion_sugerida`
- Fuentes: STD-MSG-03 · Decisión: GLOSS-DEC-BASE-002

### evento de auditoría → `audit_event` · GLOSS-BASE-AUDIT-EVENT-001 · APROBADO

Registra una acción auditable producida por el servidor sin duplicar datos personales. Plural: `audit_events`. Contextos: domain, database, api.
Sinónimos en español: auditoría.
- ✅ `audit_event_id`
- ❌ `audit_log`
- ❌ `auditoria_evento`
- Fuentes: STD-AUD-01 · Decisión: GLOSS-DEC-BASE-002

### evento de navegación → `navigation_event` · GLOSS-BASE-NAVIGATION-EVENT-001 · APROBADO

Identifica un evento de navegación asociado a una sesión y pantalla. Plural: `navigation_events`. Contextos: domain, database, api.
Sinónimos en español: navegación.
- ✅ `navigation_event_id`
- ❌ `navegacion_evento`
- Fuentes: STD-NAV-01 · Decisión: GLOSS-DEC-BASE-002

### categoría de evento → `event_category` · GLOSS-BASE-EVENT-CATEGORY-001 · APROBADO

Clasifica un evento de navegación entre las categorías técnicas permitidas. Plural: `event_categories`. Contextos: domain, database, api.
- ✅ `event_category_id`
- ❌ `categoria_evento`
- Fuentes: STD-NAV-01 · Decisión: GLOSS-DEC-BASE-002

### pantalla → `screen` · GLOSS-BASE-SCREEN-001 · APROBADO

Identifica la pantalla de la interfaz desde la cual se registra un evento. Plural: `screens`. Contextos: domain, database, api.
- ✅ `screen_id`
- ❌ `pantalla`
- ❌ `pantalla_codigo`
- Fuentes: STD-NAV-01 · Decisión: GLOSS-DEC-BASE-002

### sesión → `session` · GLOSS-BASE-SESSION-001 · APROBADO

Agrupa eventos de navegación correspondientes a una sesión. Plural: `sessions`. Contextos: domain, database, api.
- ✅ `session_id`
- ❌ `sesion_id`
- Fuentes: STD-NAV-01 · Decisión: GLOSS-DEC-BASE-002

### documento legal → `legal_document` · GLOSS-BASE-LEGAL-DOCUMENT-001 · APROBADO

Identifica la versión y vigencia de un documento legal referenciado por consentimientos. Plural: `legal_documents`. Contextos: domain, database, api.
- Nota: Legal es homógrafo español/inglés y se excluye de la detección española; documento sigue siendo detectable.
- ✅ `legal_document_id`
- ❌ `documento_legal`
- Fuentes: STD-CONS-01 · Decisión: GLOSS-DEC-BASE-002

### consentimiento → `consent` · GLOSS-BASE-CONSENT-001 · APROBADO

Registra la concesión o revocación de un consentimiento respecto de un documento legal. Plural: `consents`. Contextos: domain, database, api.
- ✅ `consent_id`
- ❌ `consentimientos`
- Fuentes: STD-CONS-02 · Decisión: GLOSS-DEC-BASE-002

### código de referencia → `trace_code` · GLOSS-BASE-TRACE-CODE-001 · APROBADO

Identifica una referencia visible para localizar la traza de una incidencia. Plural: `trace_codes`. Contextos: domain, database, api.
- Rechazado `trace_id` en database, api: La referencia visible debe conservar el nombre trace_code..
- ✅ `trace_code_id`
- ❌ `trace_id`
- ❌ `codigo_referencia`
- Fuentes: D12 · Decisión: GLOSS-DEC-BASE-002

### identificador de correlación → `correlation_id` · GLOSS-BASE-CORRELATION-ID-001 · APROBADO

Identifica la correlación transversal entre solicitudes y eventos relacionados. Plural: `correlation_ids`. Contextos: domain, database, api.
- ✅ `correlation_id`
- ❌ `correlacion_id`
- Fuentes: D9 · Decisión: GLOSS-DEC-BASE-002

### identificador de petición → `request_id` · GLOSS-BASE-REQUEST-ID-001 · APROBADO

Identifica de manera única una petición HTTP. Plural: `request_ids`. Contextos: domain, database, api.
- ✅ `request_id`
- ❌ `peticion_id`
- Fuentes: D9 · Decisión: GLOSS-DEC-BASE-002


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

### plan de pagos → `payment_plan` · GLOSS-LF-PAYMENT-PLAN-001 · APROBADO

Acuerdo para pagar una deuda mediante una o varias cuotas. Plural: `payment_plans`. Contextos: domain, database, api.
- Heredado `plan` solo en: `public.lf_user_offer_selections.plan_id`.
- ✅ `payment_plan_id`
- ❌ `plan_de_pagos_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-12; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-16; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-17 · Decisión: GLOSS-DEC-LF-002

### pago único → `one_time_payment` · GLOSS-LF-ONE-TIME-PAYMENT-001 · APROBADO

Modalidad de pago en una sola operación. Plural: `one_time_payments`. Contextos: domain, database, api.
- Rechazado `lump_sum_payment` en domain, database, api: D1: no es la forma canónica de pago único en LF..
- ✅ `one_time_payment_amount`
- ❌ `pago_unico`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-12; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-17 · Decisión: GLOSS-DEC-LF-002

### plazo → `term` · GLOSS-LF-TERM-001 · APROBADO

Duración pactada de un plan u oferta; se expresa siempre con calificador y unidad. Plural: `term`. Contextos: domain, database, api.
- Rechazado `tenor` en domain, database, api: D2: plazo se denomina term en contexto de oferta..
- Nota: Nunca usar term como identificador aislado; calificarlo, por ejemplo installment_term o max_term_months.
- ✅ `max_term_months`
- ❌ `plazo_maximo`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-10; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-12 · Decisión: GLOSS-DEC-LF-002

### descuento → `discount` · GLOSS-LF-DISCOUNT-001 · APROBADO

Reducción aplicable al importe a pagar. Plural: `discounts`. Contextos: domain, database, api.
- ✅ `discount_percent`
- ❌ `descuento_porcentaje`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-10; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-12; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-17 · Decisión: GLOSS-DEC-LF-002

### interés → `interest` · GLOSS-LF-INTEREST-001 · APROBADO

Cargo financiero previsto en un plan de cuotas. Plural: `interest`. Contextos: domain, database, api.
- ✅ `interest_rate`
- ❌ `interes_tasa`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-12 · Decisión: GLOSS-DEC-LF-002

### campaña → `campaign` · GLOSS-LF-CAMPAIGN-001 · APROBADO

Campaña comercial de beneficios para segmentos de clientes. Plural: `campaigns`. Contextos: domain, database, api.
- Nota: La campaign de lf_ops.system_audit_campaigns corresponde a auditoría técnica y no a esta campaña comercial.
- ✅ `campaign_id`
- ❌ `campana_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-13 · Decisión: GLOSS-DEC-LF-002

### beneficio → `benefit` · GLOSS-LF-BENEFIT-001 · APROBADO

Ventaja temporal configurada en una campaña. Plural: `benefits`. Contextos: domain, database, api.
- ✅ `campaign_benefit`
- ❌ `beneficio_campana`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-13 · Decisión: GLOSS-DEC-LF-002

### vigencia → `validity_period` · GLOSS-LF-VALIDITY-PERIOD-001 · APROBADO

Intervalo temporal durante el cual una regla, condición u oferta se aplica. Plural: `validity_periods`. Contextos: domain, database, api.
- Nota: Los tokens técnicos valid y valid_until no son sinónimos libres del concepto. Ver fechas de inicio y fin.
- ✅ `valid_from`
- ❌ `vigencia_inicio`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-10; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-12; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-13; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-17 · Decisión: GLOSS-DEC-LF-002

### vencimiento → `expiration` · GLOSS-LF-EXPIRATION-001 · APROBADO

Finalización de la vigencia de una oferta en una fecha y hora. Plural: `expirations`. Contextos: domain, database, api.
- ✅ `expires_at`
- ❌ `vencimiento_fecha`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-14 · Decisión: GLOSS-DEC-LF-002

### cronograma → `payment_schedule` · GLOSS-LF-PAYMENT-SCHEDULE-001 · APROBADO

Fechas y condiciones programadas de cada cuota de un plan. Plural: `payment_schedules`. Contextos: domain, database, api.
- ✅ `payment_schedule_id`
- ❌ `cronograma_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-16 · Decisión: GLOSS-DEC-LF-002

### saldo → `balance` · GLOSS-LF-BALANCE-001 · APROBADO

Importe pendiente de pago de una deuda. Plural: `balance`. Contextos: domain, database, api.
- ✅ `outstanding_balance`
- ❌ `saldo_pendiente`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-15; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-25 · Decisión: GLOSS-DEC-LF-002

### deuda original → `original_debt` · GLOSS-LF-ORIGINAL-DEBT-001 · APROBADO

Deuda antes de aplicar pagos u ofertas de LF. Plural: `original_debts`. Contextos: domain, database, api.
- Nota: original es también una palabra inglesa; excluir del detector léxico de español.
- ✅ `original_debt`
- ❌ `deuda_original`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-15 · Decisión: GLOSS-DEC-LF-002

### transacción → `transaction` · GLOSS-LF-TRANSACTION-001 · APROBADO

Intento y resultado individual de una operación de pago, con referencia de proveedor. Plural: `transactions`. Contextos: domain, database, api.
- ✅ `transaction_id`
- ❌ `transaccion_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-26; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-29; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-30 · Decisión: GLOSS-DEC-LF-002

### medio de pago → `payment_method` · GLOSS-LF-PAYMENT-METHOD-001 · APROBADO

Canal o instrumento usado para iniciar un pago. Plural: `payment_methods`. Contextos: domain, database, api.
- ✅ `payment_method`
- ❌ `medio_de_pago`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-20; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-26 · Decisión: GLOSS-DEC-LF-002

### anulación → `void` · GLOSS-LF-VOID-001 · APROBADO

Operación que anula un pago según las reglas del proveedor. Plural: `voids`. Contextos: domain, database, api.
- Rechazado `cancellation` en domain, database, api: D3: en el flujo de pagos se usa void..
- Nota: Confirmar semántica técnica de void/voided contra documentación oficial de Niubiz cuando esté disponible.
- ✅ `void_reason`
- ❌ `anulacion_motivo`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-27 · Decisión: GLOSS-DEC-LF-002

### reverso → `reversal` · GLOSS-LF-REVERSAL-001 · APROBADO

Operación de reverso de pago con motivo y doble aprobación. Plural: `reversals`. Contextos: domain, database, api.
- ✅ `reversal_id`
- ❌ `reverso_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-27 · Decisión: GLOSS-DEC-LF-002

### conciliación → `payment_reconciliation` · GLOSS-LF-PAYMENT-RECONCILIATION-001 · APROBADO

Contraste entre pagos de LF y registros de proveedores por periodo. Plural: `payment_reconciliations`. Contextos: domain, database, api.
- Nota: reconciliation existente en GitHub/plataforma es otro contexto, no la conciliación financiera.
- ✅ `payment_reconciliation_id`
- ❌ `conciliacion_pago`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-29; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-37; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-41 · Decisión: GLOSS-DEC-LF-002

### diferencia de conciliación → `reconciliation_discrepancy` · GLOSS-LF-RECONCILIATION-DISCREPANCY-001 · APROBADO

Diferencia identificada en una conciliación: ausencia o divergencia de importe/estado. Plural: `reconciliation_discrepancies`. Contextos: domain, database, api.
- Nota: discrepancy en la plataforma puede corresponder a otras verificaciones; el término está acotado a pagos.
- ✅ `reconciliation_discrepancy_id`
- ❌ `diferencia_conciliacion`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-30; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-31 · Decisión: GLOSS-DEC-LF-002

### liquidación → `settlement` · GLOSS-LF-SETTLEMENT-001 · APROBADO

Cierre y liquidación de operaciones por empresa y periodo. Plural: `settlements`. Contextos: domain, database, api.
- ✅ `settlement_id`
- ❌ `liquidacion_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-32 · Decisión: GLOSS-DEC-LF-002

### controversia → `dispute` · GLOSS-LF-DISPUTE-001 · APROBADO

Disputa registrada por un cliente u operador, con seguimiento y resolución. Plural: `disputes`. Contextos: domain, database, api.
- ✅ `dispute_id`
- ❌ `controversia_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-33 · Decisión: GLOSS-DEC-LF-002

### recaudo → `collected_amount` · GLOSS-LF-COLLECTED-AMOUNT-001 · APROBADO

Importe recaudado en los indicadores de empresa. Plural: `collected_amount`. Contextos: domain, database, api.
Sinónimos en español: recaudación.
- Rechazado `collection` en domain, database, api: D4: collection significa cobranza, no importe recaudado..
- Heredado `collection` solo en: `public.lf_b2b_pricing_config.b2b_collection_cost_type`, `public.lf_b2b_pricing_config.b2b_collection_cost_value`, `public.lf_b2b_pricing_config.b2b_collection_cost_customer_visible`, `public.lf_b2b_pricing_config.collection_channel`.
- Nota: collection ya se usa para cobranza en LF; no intercambiar con recaudo. La excepción de legado solo preserva las cuatro columnas concretas.
- ✅ `collected_amount`
- ❌ `recaudo_total`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-41 · Decisión: GLOSS-DEC-LF-002

### comprobante de pago → `payment_receipt` · GLOSS-LF-PAYMENT-RECEIPT-001 · APROBADO

Documento consultable y descargable que acredita un pago. Plural: `payment_receipts`. Contextos: domain, database, api.
- Nota: receipt ya aparece como recibo de evidencia técnica de plataforma; en LF este compuesto designa comprobante financiero.
- ✅ `payment_receipt_id`
- ❌ `comprobante_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-28 · Decisión: GLOSS-DEC-LF-002

### carta de no adeudo → `debt_clearance_letter` · GLOSS-LF-DEBT-CLEARANCE-LETTER-001 · APROBADO

Carta emitida tras confirmar el cierre de la deuda. Plural: `debt_clearance_letters`. Contextos: domain, database, api.
- Rechazado `no_debt_certificate` en domain, database, api: D6: nombre descartado para el documento de cierre..
- ✅ `debt_clearance_letter_id`
- ❌ `carta_no_adeudo_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-34 · Decisión: GLOSS-DEC-LF-002

### verificación de identidad → `identity_verification` · GLOSS-LF-IDENTITY-VERIFICATION-001 · APROBADO

Validación de que el cliente es titular antes de mostrar su deuda. Plural: `identity_verifications`. Contextos: domain, database, api.
- ✅ `identity_verification_status`
- ❌ `verificacion_identidad`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-02 · Decisión: GLOSS-DEC-LF-002

### días de atraso → `days_past_due` · GLOSS-LF-DAYS-PAST-DUE-001 · APROBADO

Número de días transcurridos desde el vencimiento impago. Plural: `days_past_due`. Contextos: domain, database, api.
- ✅ `days_past_due`
- ❌ `dias_atraso`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-09 · Decisión: GLOSS-DEC-LF-002

### regla → `offer_rule` · GLOSS-LF-OFFER-RULE-001 · APROBADO

Regla de negocio por segmento que determina qué ofertas son aplicables. Plural: `offer_rules`. Contextos: domain, database, api.
- Rechazado `rule` en domain, database, api: D5: rule aislado se confunde con reglas técnicas y linters..
- Heredado `reglas` solo en: `lf_ops.reglas`, `lf_ops.reglas_pantallas`, `lf_ops.pantallas_politicas_reglas`.
- Heredado `regla` solo en: `lf_ops.reglas_pantallas.regla_id`, `lf_ops.pantallas_politicas_reglas.regla_id`.
- Nota: No confundir con el catálogo general lf_ops.reglas ni con reglas de linters; son reglas de aplicabilidad de ofertas.
- ✅ `offer_rule_id`
- ❌ `regla_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-10; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-11 · Decisión: GLOSS-DEC-LF-002

### condición → `offer_condition` · GLOSS-LF-OFFER-CONDITION-001 · APROBADO

Restricción versionada que debe cumplirse para aplicar una oferta. Plural: `offer_conditions`. Contextos: domain, database, api.
- Rechazado `condition` en domain, database, api: D5: condition aislado no identifica la condición de la oferta..
- ✅ `offer_condition_id`
- ❌ `condicion_id`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-10; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-11; paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-18 · Decisión: GLOSS-DEC-LF-002

### estado de pago → `payment_status` · GLOSS-LF-PAYMENT-STATUS-001 · APROBADO

Estado de una transacción de pago con valores de RF-23. Plural: `payment_statuses`. Contextos: domain, database, api.
- Valores: `creado` → `created`, `pendiente` → `pending`, `aprobado` → `approved`, `rechazado` → `rejected`, `expirado` → `expired`, `anulado` → `voided`.
- Nota: Los seis valores se registran juntos en una sola entrada; anulado -> voided, sujeto a confirmación posterior con documentación Niubiz.
- ✅ `payment_status`
- ❌ `estado_pago`
- Fuentes: paulozterra/lf-architecture@bbe718c:docs/requisitos.md#RF-23 · Decisión: GLOSS-DEC-LF-002
