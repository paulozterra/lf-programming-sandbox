# Kit base PG-00·C5 · v0.1.0

## Autoridad y alcance
El kit pertenece al catálogo técnico, no al producto. Instancia ocho tablas comunes en PostgreSQL 17.11; el stack de calificación es Spring + RDS y no se añaden JPA ni Flyway al backend de este repositorio. Las migraciones siguen la convención Flyway V0_1…V0_4; el producto comienza en V1. Esquema `${schema}` y prefijo `${trace_prefix}` se renderizan mediante `python3 standards/tools/kit.py render --schema kit_test --trace-prefix KIT --out /tmp/kit-render`.

El consumidor fija `kit_version`, `catalog_version`, `glossary_version` y los SHA-256 de `kit.json` como contrato reproducible. `kit.py verify` compara digests. La aplicación crea `trace_code` con el patrón PREFIJO-YYYYMMDD-XXXXXXXX; el kit solo verifica su forma.

## Migraciones y reversas
- V0_1: tablas y relaciones, sin registros del producto.
- V0_2: triggers para timestamps y tablas append-only, cierre único de vigencia legal.
- V0_3: vistas con security_invoker para soporte.
- V0_4: seis errores técnicos con códigos KIT-TEC-001…006 (prefijo parametrizable), estado PENDING_COPY, sin títulos ni mensajes visibles.
- U0_4 revierte sólo seeds intactos; U0_3 y U0_2 conservan datos; U0_1 exige ocho tablas vacías y luego las elimina.

La reversa de V0_1 **solo** es válida en bootstrap vacío; nunca es mecanismo de downgrade de una base con datos. El ensayo `db_catalog_lint.py migrate-test` prueba dato testigo persistente al quitar/reaplicar V0_2 y V0_3, y tabla vacía para U0_1.

## Frontera con Fase 1 y bloqueo de producción
Fase 1 define códigos de negocio, copy visible, eventos concretos de navegación, qué pantallas instrumentar, consentimientos, retención y textos legales. `navigation_event_types` inicia vacía; sus categorías admisibles son screen_view, action, submit, error, exit. Los errores técnicos quedan PENDING_COPY; esa condición **impide habilitación productiva** hasta evidencia humana de copy, aunque las filas sean is_active=true.

## Roles, seguridad y RLS
El kit NO crea roles. El equipo de infraestructura proporciona rol propietario de migración y rol runtime independiente sin ownership ni BYPASSRLS. El runtime recibe USAGE en esquema, SELECT/INSERT en tablas necesarias y UPDATE solo en catálogos mutables (errors, messages, navigation_event_types); se niegan DELETE/TRUNCATE/UPDATE en append-only. legal_documents solo permite cerrar valid_to una vez y sin cambiar los demás campos; debe existir un writer del servidor con privilegio UPDATE(column valid_to), mientras el trigger impide el resto. La aplicación no expone la BD a clientes.

STD-DB-06: en este stack privado no se exige RLS **solo** con prueba de ausencia de grants a PUBLIC y de acceso directo; si una tabla/función se expone, REQUIRES_DECISION y deben definirse políticas explícitas. Funciones invoker; se revoca EXECUTE a PUBLIC.

## Legal y privacidad: REQUIRES_DECISION
IP, browser_info, user_ref (hash/anónimo), session_id, actor_ref, entity_ref, correlation_id y retención requieren aprobación de legal y seguridad (minimización, derecho de supresión, hash/salt, cifrado, finalidad, cookies). Nada de payload crudo ni copy inventado. Los campos son estructura, no autorización de recolección de datos.

## STD-DB / CI
`standards/tools/db_catalog_lint.py` inspecciona pg_catalog en el esquema del kit y prueba archivos/migraciones. El gate bloqueante se limita al kit (GO 22/10); otras bases siguen en sombra D11. STD-DB-10 del contexto de plataforma LF se informa NOT_APPLICABLE para Spring/RDS. La ejecución en CI usa docker compose y credencial efímera prevista en el workflow.
