# Informe del análisis (candidato simulado)

## Pedido literal

```text
implementa SBX-B2B-LOGIN
```

- Autor: paulozterra
- Issue: #391
- Fecha: 2026-11-23T17:59:39Z
- Pantalla: SBX-B2B-LOGIN
- Modo: SIMULATED_ANALYSIS

## Reglas de la ficha

| Código | Título | Descripción |
| --- | --- | --- |
| SBX-B2B-R-A11Y-CONTRAST | Contraste y color | Ningún estado depende únicamente del color. |
| SBX-B2B-R-A11Y-FORCED-COLORS | Forced colors y alto contraste sin pérdida funcional | En modo de colores forzados o alto contraste la pantalla conserva toda su funcionalidad, foco y estados. |
| SBX-B2B-R-A11Y-INTERACTION | Interacción accesible | Controles con área táctil mínima, foco visible, navegación por teclado y etiquetas. |
| SBX-B2B-R-A11Y-MOTION | Preferencia de movimiento reducido | Se respeta la preferencia de movimiento reducido del usuario. Cuando esté activa, las animaciones y transiciones no esenciales se reducen o eliminan; ningún estado, error, progreso ni acción depende exclusivamente del movimiento. |
| SBX-B2B-R-AUTH-DENY-DEFAULT | Denegar por defecto | Toda acción operativa posterior a autenticación completa se deniega por defecto y requiere autorización del lado servidor. El login nunca concede por sí mismo permisos operativos. |
| SBX-B2B-R-AUTH-ENVELOPE | Sobre de respuesta seguro de autenticación | La respuesta expone únicamente el outcome funcional, un correlation_id generado por servidor y, cuando corresponda, el código de error canónico. No se exponen errores crudos, credenciales, tokens internos ni razones sensibles. |
| SBX-B2B-R-AUTH-FAIL-CLOSED | Autenticación del lado servidor y fail-closed | El Login se comunica exclusivamente con una capa de autenticación del lado servidor. El navegador no verifica credenciales por sí mismo. Si la identidad no puede verificarse válidamente, no se crea sesión ni se concede acceso. |
| SBX-B2B-R-AUTH-GENERIC | Mensaje genérico ante credenciales inválidas | Ante fallos de credencial o denegaciones relacionadas con la cuenta, el Login no debe revelar si el correo existe, si el usuario está activo/restringido ni qué credencial falló. Las respuestas externas de estos fallos deben ser funcionalmente indistinguibles en mensaje y comportamiento observable, mitigando diferencias de tiempo. Estados no equivalentes como rate limit o indisponibilidad del servicio conservan su tratamiento específico. |
| SBX-B2B-R-AUTH-OUTCOMES | Resultados normalizados del servicio de autenticación | La capa de autenticación traduce cualquier resultado a un outcome funcional estable. Para outcomes no exitosos se utiliza exclusivamente un código del catálogo de errores; el HTTP y los mensajes visibles se resuelven desde ese catálogo. |
| SBX-B2B-R-AUTH-REQUEST | Contrato de solicitud hacia la capa de autenticación | La solicitud de login viaja por HTTPS en el cuerpo, nunca en la URL, query string ni headers de logging. La contraseña no se recorta, normaliza ni transforma; el correo puede recortarse por fuera. El servidor genera el correlation_id. Un resultado de éxito declarado por el cliente no es autoritativo. |
| SBX-B2B-R-AUTH-RUNTIME-PASSWORD | Contraseña solo en runtime | La contraseña ingresada en Login solo existe durante la autenticación. No se persiste en tablas funcionales, logs, analytics, session replay ni payloads de diseño. |
| SBX-B2B-R-AUTH-SESSION-AFTER-AUTH | Creación de sesión únicamente tras autenticación completa | Solo se crea o confirma una sesión autenticada cuando el resultado funcional sea AUTHENTICATED. La creación y rotación de sesión se ejecutan del lado servidor y consumen la política central de sesión; el cliente no decide TTL, concurrencia, rotación ni elevación de privilegios. |
| SBX-B2B-R-AUTH-TIMEOUT | Timeout y reintento controlado de autenticación | La autenticación consume la política central de timeout. Ante timeout o indisponibilidad se mantiene fail-closed y la respuesta funcional se normaliza como SERVICE_UNAVAILABLE; nunca se reclasifica como credenciales inválidas. |
| SBX-B2B-R-DATA-ATTEMPTS | Registro persistente de intentos fallidos | Cada intento de inicio de sesión fallido queda registrado en el almacén persistente con la referencia de la cuenta o el correo normalizado, la hora, el resultado y el correlation id; nunca la contraseña. El bloqueo por intentos se calcula desde ese registro, de modo que se mantiene aunque el servicio se reinicie. Rige la política del login existente (bloqueo tras 5 fallos durante 15 minutos). |
| SBX-B2B-R-DATA-SESSIONS | Sesiones persistidas y revocables | La sesión emitida tras un resultado AUTHENTICATED se registra en el almacén persistente (solo el hash del token, la cuenta, creación, último uso, vencimiento y revocación). La inactividad y la concurrencia de sesiones se aplican desde ese registro. Cerrar sesión revoca el registro; un token revocado o vencido deja de ser válido aunque el servicio se reinicie. |
| SBX-B2B-R-DATA-USER-STORE | Cuentas en el almacén persistente | Las cuentas que pueden iniciar sesión viven en el almacén persistente del sandbox (base relacional, migraciones Flyway versionadas que aplica el propio servicio al iniciar). Cada cuenta guarda correo, empresa, perfil y estado; la contraseña solo se guarda como hash. El correo es único sin distinguir mayúsculas. Los datos iniciales son ficticios y nunca incluyen contraseñas en claro. Las cuentas inactivas o restringidas no pueden autenticarse y se tratan como credenciales inválidas hacia afuera. |
| SBX-B2B-R-DESIGN-NO-HARDCODE | Sin valores visuales duros | Pantallas y componentes no almacenan HEX, RGB ni medidas directas; los consumen desde los tokens. |
| SBX-B2B-R-DESIGN-TOKENS | Referencias semánticas de tokens | Toda definición visual consume los tokens del sistema de diseño de la pantalla (color, tipografía, espaciado, componentes). Está prohibido gobernar la pantalla mediante valores locales no registrados. |
| SBX-B2B-R-ERROR-CODE | Código canónico de error | Todo error se relaciona con el catálogo de errores de la pantalla mediante su código canónico estable. |
| SBX-B2B-R-ERROR-SAFE-MESSAGE | Mensaje seguro al usuario | Mostrar qué ocurrió, acción sugerida, CTA y código de referencia; ocultar detalles técnicos. |
| SBX-B2B-R-ERROR-TRACE | Trazabilidad de ocurrencia | Cada ocurrencia de error se registra del lado servidor con trace_code y correlation_id. El cliente nunca inserta ocurrencias directamente. En errores pre-autenticación solo se conserva contexto redactado y no identificante. |
| SBX-B2B-R-INT-EMAIL-LOGIN | El login existente acepta correo | Integración del sandbox (no es regla de LF): el servicio de login existente (POST /api/auth/login) acepta el correo electrónico como identificador; el usuario de prueba tiene el correo demo@sandbox.test. No se crea un segundo servicio de login; el acceso por usuario existente sigue funcionando. |
| SBX-B2B-R-INT-HOME | Pantalla de inicio tras autenticarse | Integración del sandbox: existe una pantalla de inicio en /home que solo muestra el título Welcome. Requiere una sesión válida, verificada por el servidor; sin sesión válida se redirige a /sbx-b2b-login con next=/home. |
| SBX-B2B-R-INT-RETURN | Volver a la pantalla de origen | Integración del sandbox (no es regla de LF): tras iniciar sesión se navega a la ruta interna indicada en el parámetro next de /sbx-b2b-login; si no hay next o no es una ruta interna del sitio, se navega a la pantalla de inicio /home. Nunca se redirige a un dominio externo. |
| SBX-B2B-R-INT-ROUTE | Ruta de la pantalla y redirección desde pantallas protegidas | Integración del sandbox (no es regla de LF): la pantalla de login vive en la ruta /sbx-b2b-login. La pantalla protegida existente /sbx-rem-list, cuando no hay sesión, redirige a /sbx-b2b-login?next=/sbx-rem-list en vez de a /login. |
| SBX-B2B-R-INT-SESSION-STORE | Dónde queda la sesión en el navegador | Integración del sandbox (no es regla de LF): tras un resultado AUTHENTICATED, el token devuelto por el backend se guarda en sessionStorage con la clave sbx-session-token, que es la que leen las pantallas protegidas existentes. Nunca se guarda la contraseña. |
| SBX-B2B-R-LAYOUT-COMPOSITION | Composición de la pantalla por regiones | La pantalla se compone por regiones (cabecera con logo y contexto, decorativa con marca de agua, principal y pie) según la composición del contrato visual: orden, alineación, anchos, alturas y separaciones salen de los tokens registrados (incluidos los de layout), con una tolerancia de 8 px respecto de los lienzos de referencia 1440×900, 834×1112 y 390×844. El logo y la marca de agua se usan desde los archivos registrados en brand_assets, nunca se recrean. La marca de agua cambia de posición según la variante y se oculta en móvil. No se usa tarjeta contenedora ni barra lateral. |
| SBX-B2B-R-PRIVACY-TELEMETRY | PII prohibida en telemetría | Analytics, logs, replay y errores no reciben PII. |
| SBX-B2B-R-RATE-LIMIT | Límites por recurso | Todo límite de frecuencia o cantidad de solicitudes se obtiene de la política central. En el sandbox rige la política del login existente (sesión de 30 minutos y bloqueo tras 5 fallos durante 15 minutos); los valores de sesión y rate limit B2B no aplican (decisión del owner 2026-11-16). |
| SBX-B2B-R-RESP-BREAKPOINTS | Tres breakpoints funcionales | La pantalla tiene variantes desktop, tablet y móvil. |
| SBX-B2B-R-SESSION-CONCURRENCY | Rotación y concurrencia gobernadas por políticas centrales | La rotación de sesión y los límites de concurrencia se obtienen de la política central de sesión. En el sandbox rige la política del login existente (sesión de 30 minutos y bloqueo tras 5 fallos durante 15 minutos); los valores de sesión y rate limit B2B no aplican (decisión del owner 2026-11-16). |
| SBX-B2B-R-SESSION-IDLE | Duración de la sesión | La expiración de la sesión se rige por la política central de sesión. En el sandbox rige la política del login existente (sesión de 30 minutos y bloqueo tras 5 fallos durante 15 minutos); los valores de sesión y rate limit B2B no aplican (decisión del owner 2026-11-16). |
| SBX-B2B-R-THEME-LIGHT | Modo claro | La pantalla usa el tema claro del sistema de diseño (el modo noche queda fuera de alcance en este sandbox). |
| SBX-B2B-R-UX-ACTIONS | Contrato de acciones del Login | Las acciones del Login son: iniciar sesión, mostrar u ocultar contraseña, recuperación de contraseña, Términos y condiciones, Política de privacidad y Contáctanos. Recuperación, Términos, Privacidad y Contáctanos se muestran como enlaces sin destino funcional en esta pantalla. |
| SBX-B2B-R-UX-PASSWORD-MANAGERS | Entrada compatible con gestores de credenciales | El Login permite gestores de contraseñas y pegado de credenciales mediante controles estándar. El correo usa autocomplete=username y la contraseña autocomplete=current-password, en el mismo formulario. El valor de la contraseña nunca se envía a telemetría. |
| SBX-B2B-R-UX-PASSWORD-VISIBILITY | Mostrar u ocultar contraseña sin alterar el valor | El campo Contraseña permite alternar entre contenido visible y enmascarado mediante control de visibilidad, sin modificar el valor ni enviarlo a telemetría. |
| SBX-B2B-R-UX-RECOVERY | Recuperación de contraseña visible y separada | El Login muestra una acción visible de recuperación inmediatamente asociada al campo Contraseña. La recuperación se resuelve en un flujo separado (fuera de alcance de esta pantalla) y no se ejecuta dentro del formulario de Login. |
| SBX-B2B-R-UX-SINGLE-FLIGHT | Un solo intento de autenticación en vuelo | Mientras exista una solicitud de autenticación pendiente, se ignoran envíos duplicados y el CTA permanece en estado procesando. |

## Etapas A1–A9

| Etapa | Estado | Significado |
| --- | --- | --- |
| A1 | VALID_OUTPUT | La entrada del pedido produjo una salida estructurada válida |
| A2 | NEED_MORE_EVIDENCE | Falta evidencia suficiente para considerar acreditada la información |
| A3 | SOURCE_READBACK_PROCESSED_UNATTESTED | Se procesó la ficha fuente, sin acreditar autoridad de producción |
| A4 | PLANNED_BUILD_IMPACT_UNATTESTED | Se identificó impacto de implementación, pendiente de acreditación |
| A5 | UNRESOLVED | Las decisiones de gobierno o autoridad siguen sin resolverse |
| A6 | CANDIDATE_ONLY | Las obligaciones WHAT son candidatas, no aprobaciones productivas |
| A7 | CANDIDATE_ONLY | Los frentes y su alcance son candidatos, no autorizaciones |
| A8 | CANDIDATE_ONLY | La comprobación de cobertura permanece en estado candidato |
| A9 | SIMULATED_PACKAGE_CANDIDATE | Se produjo un paquete de implementación simulado |

## Clasificación

| Campo | Valor |
| --- | --- |
| authority_state | UNKNOWN |
| change_type | CREATE |
| depth | L3 |
| depth_reason_predicates | ["materiality_level=HIGH"] |
| implementation_state | NEW |
| target_granularity | SCREEN |

## Desconocidos

- {"code": "SIMULATED_SANDBOX_ONLY_NO_PRODUCTION_AUTHORITY", "source_ref": "fixture://SBX-B2B-LOGIN"}

## Decisiones pendientes

- Ninguno consignado

## Requisitos y frentes por área

### DATA

Requisitos:

- REQ-SBX-B2B-R-DATA-ATTEMPTS: Cada intento de inicio de sesión fallido queda registrado en el almacén persistente con la referencia de la cuenta o el correo normalizado, la hora, el resultado y el correlation id; nunca la contraseña. El bloqueo por intentos se calcula desde ese registro, de modo que se mantiene aunque el servicio se reinicie. Rige la política del login existente (bloqueo tras 5 fallos durante 15 minutos).
- REQ-SBX-B2B-R-DATA-SESSIONS: La sesión emitida tras un resultado AUTHENTICATED se registra en el almacén persistente (solo el hash del token, la cuenta, creación, último uso, vencimiento y revocación). La inactividad y la concurrencia de sesiones se aplican desde ese registro. Cerrar sesión revoca el registro; un token revocado o vencido deja de ser válido aunque el servicio se reinicie.
- REQ-SBX-B2B-R-DATA-USER-STORE: Las cuentas que pueden iniciar sesión viven en el almacén persistente del sandbox (base relacional, migraciones Flyway versionadas que aplica el propio servicio al iniciar). Cada cuenta guarda correo, empresa, perfil y estado; la contraseña solo se guarda como hash. El correo es único sin distinguir mayúsculas. Los datos iniciales son ficticios y nunca incluyen contraseñas en claro. Las cuentas inactivas o restringidas no pueden autenticarse y se tratan como credenciales inválidas hacia afuera.

Frentes:

- F3-e2a979e0fa39d8e1: DATA_CONTRACT (CLOSED)

### BACKEND

Requisitos:

- REQ-SBX-B2B-R-AUTH-DENY-DEFAULT: Toda acción operativa posterior a autenticación completa se deniega por defecto y requiere autorización del lado servidor. El login nunca concede por sí mismo permisos operativos.
- REQ-SBX-B2B-R-AUTH-ENVELOPE: La respuesta expone únicamente el outcome funcional, un correlation_id generado por servidor y, cuando corresponda, el código de error canónico. No se exponen errores crudos, credenciales, tokens internos ni razones sensibles.
- REQ-SBX-B2B-R-AUTH-FAIL-CLOSED: El Login se comunica exclusivamente con una capa de autenticación del lado servidor. El navegador no verifica credenciales por sí mismo. Si la identidad no puede verificarse válidamente, no se crea sesión ni se concede acceso.
- REQ-SBX-B2B-R-AUTH-GENERIC: Ante fallos de credencial o denegaciones relacionadas con la cuenta, el Login no debe revelar si el correo existe, si el usuario está activo/restringido ni qué credencial falló. Las respuestas externas de estos fallos deben ser funcionalmente indistinguibles en mensaje y comportamiento observable, mitigando diferencias de tiempo. Estados no equivalentes como rate limit o indisponibilidad del servicio conservan su tratamiento específico.
- REQ-SBX-B2B-R-AUTH-OUTCOMES: La capa de autenticación traduce cualquier resultado a un outcome funcional estable. Para outcomes no exitosos se utiliza exclusivamente un código del catálogo de errores; el HTTP y los mensajes visibles se resuelven desde ese catálogo.
- REQ-SBX-B2B-R-AUTH-REQUEST: La solicitud de login viaja por HTTPS en el cuerpo, nunca en la URL, query string ni headers de logging. La contraseña no se recorta, normaliza ni transforma; el correo puede recortarse por fuera. El servidor genera el correlation_id. Un resultado de éxito declarado por el cliente no es autoritativo.
- REQ-SBX-B2B-R-AUTH-RUNTIME-PASSWORD: La contraseña ingresada en Login solo existe durante la autenticación. No se persiste en tablas funcionales, logs, analytics, session replay ni payloads de diseño.
- REQ-SBX-B2B-R-AUTH-SESSION-AFTER-AUTH: Solo se crea o confirma una sesión autenticada cuando el resultado funcional sea AUTHENTICATED. La creación y rotación de sesión se ejecutan del lado servidor y consumen la política central de sesión; el cliente no decide TTL, concurrencia, rotación ni elevación de privilegios.
- REQ-SBX-B2B-R-AUTH-TIMEOUT: La autenticación consume la política central de timeout. Ante timeout o indisponibilidad se mantiene fail-closed y la respuesta funcional se normaliza como SERVICE_UNAVAILABLE; nunca se reclasifica como credenciales inválidas.
- REQ-SBX-B2B-R-ERROR-CODE: Todo error se relaciona con el catálogo de errores de la pantalla mediante su código canónico estable.
- REQ-SBX-B2B-R-ERROR-SAFE-MESSAGE: Mostrar qué ocurrió, acción sugerida, CTA y código de referencia; ocultar detalles técnicos.
- REQ-SBX-B2B-R-ERROR-TRACE: Cada ocurrencia de error se registra del lado servidor con trace_code y correlation_id. El cliente nunca inserta ocurrencias directamente. En errores pre-autenticación solo se conserva contexto redactado y no identificante.
- REQ-SBX-B2B-R-INT-EMAIL-LOGIN: Integración del sandbox (no es regla de LF): el servicio de login existente (POST /api/auth/login) acepta el correo electrónico como identificador; el usuario de prueba tiene el correo demo@sandbox.test. No se crea un segundo servicio de login; el acceso por usuario existente sigue funcionando.
- REQ-SBX-B2B-R-PRIVACY-TELEMETRY: Analytics, logs, replay y errores no reciben PII.
- REQ-SBX-B2B-R-RATE-LIMIT: Todo límite de frecuencia o cantidad de solicitudes se obtiene de la política central. En el sandbox rige la política del login existente (sesión de 30 minutos y bloqueo tras 5 fallos durante 15 minutos); los valores de sesión y rate limit B2B no aplican (decisión del owner 2026-11-16).
- REQ-SBX-B2B-R-SESSION-CONCURRENCY: La rotación de sesión y los límites de concurrencia se obtienen de la política central de sesión. En el sandbox rige la política del login existente (sesión de 30 minutos y bloqueo tras 5 fallos durante 15 minutos); los valores de sesión y rate limit B2B no aplican (decisión del owner 2026-11-16).
- REQ-SBX-B2B-R-SESSION-IDLE: La expiración de la sesión se rige por la política central de sesión. En el sandbox rige la política del login existente (sesión de 30 minutos y bloqueo tras 5 fallos durante 15 minutos); los valores de sesión y rate limit B2B no aplican (decisión del owner 2026-11-16).
- REQ-SBX-B2B-R-UX-PASSWORD-MANAGERS: El Login permite gestores de contraseñas y pegado de credenciales mediante controles estándar. El correo usa autocomplete=username y la contraseña autocomplete=current-password, en el mismo formulario. El valor de la contraseña nunca se envía a telemetría.
- REQ-SBX-B2B-R-UX-PASSWORD-VISIBILITY: El campo Contraseña permite alternar entre contenido visible y enmascarado mediante control de visibilidad, sin modificar el valor ni enviarlo a telemetría.

Frentes:

- F3-c1743642ff99da50: API_CONTRACT (CLOSED)

### FRONTEND

Requisitos:

- REQ-SBX-B2B-R-A11Y-CONTRAST: Ningún estado depende únicamente del color.
- REQ-SBX-B2B-R-A11Y-FORCED-COLORS: En modo de colores forzados o alto contraste la pantalla conserva toda su funcionalidad, foco y estados.
- REQ-SBX-B2B-R-A11Y-INTERACTION: Controles con área táctil mínima, foco visible, navegación por teclado y etiquetas.
- REQ-SBX-B2B-R-A11Y-MOTION: Se respeta la preferencia de movimiento reducido del usuario. Cuando esté activa, las animaciones y transiciones no esenciales se reducen o eliminan; ningún estado, error, progreso ni acción depende exclusivamente del movimiento.
- REQ-SBX-B2B-R-DESIGN-NO-HARDCODE: Pantallas y componentes no almacenan HEX, RGB ni medidas directas; los consumen desde los tokens.
- REQ-SBX-B2B-R-DESIGN-TOKENS: Toda definición visual consume los tokens del sistema de diseño de la pantalla (color, tipografía, espaciado, componentes). Está prohibido gobernar la pantalla mediante valores locales no registrados.
- REQ-SBX-B2B-R-INT-HOME: Integración del sandbox: existe una pantalla de inicio en /home que solo muestra el título Welcome. Requiere una sesión válida, verificada por el servidor; sin sesión válida se redirige a /sbx-b2b-login con next=/home.
- REQ-SBX-B2B-R-INT-RETURN: Integración del sandbox (no es regla de LF): tras iniciar sesión se navega a la ruta interna indicada en el parámetro next de /sbx-b2b-login; si no hay next o no es una ruta interna del sitio, se navega a la pantalla de inicio /home. Nunca se redirige a un dominio externo.
- REQ-SBX-B2B-R-INT-ROUTE: Integración del sandbox (no es regla de LF): la pantalla de login vive en la ruta /sbx-b2b-login. La pantalla protegida existente /sbx-rem-list, cuando no hay sesión, redirige a /sbx-b2b-login?next=/sbx-rem-list en vez de a /login.
- REQ-SBX-B2B-R-INT-SESSION-STORE: Integración del sandbox (no es regla de LF): tras un resultado AUTHENTICATED, el token devuelto por el backend se guarda en sessionStorage con la clave sbx-session-token, que es la que leen las pantallas protegidas existentes. Nunca se guarda la contraseña.
- REQ-SBX-B2B-R-LAYOUT-COMPOSITION: La pantalla se compone por regiones (cabecera con logo y contexto, decorativa con marca de agua, principal y pie) según la composición del contrato visual: orden, alineación, anchos, alturas y separaciones salen de los tokens registrados (incluidos los de layout), con una tolerancia de 8 px respecto de los lienzos de referencia 1440×900, 834×1112 y 390×844. El logo y la marca de agua se usan desde los archivos registrados en brand_assets, nunca se recrean. La marca de agua cambia de posición según la variante y se oculta en móvil. No se usa tarjeta contenedora ni barra lateral.
- REQ-SBX-B2B-R-RESP-BREAKPOINTS: La pantalla tiene variantes desktop, tablet y móvil.
- REQ-SBX-B2B-R-THEME-LIGHT: La pantalla usa el tema claro del sistema de diseño (el modo noche queda fuera de alcance en este sandbox).
- REQ-SBX-B2B-R-UX-ACTIONS: Las acciones del Login son: iniciar sesión, mostrar u ocultar contraseña, recuperación de contraseña, Términos y condiciones, Política de privacidad y Contáctanos. Recuperación, Términos, Privacidad y Contáctanos se muestran como enlaces sin destino funcional en esta pantalla.
- REQ-SBX-B2B-R-UX-RECOVERY: El Login muestra una acción visible de recuperación inmediatamente asociada al campo Contraseña. La recuperación se resuelve en un flujo separado (fuera de alcance de esta pantalla) y no se ejecuta dentro del formulario de Login.
- REQ-SBX-B2B-R-UX-SINGLE-FLIGHT: Mientras exista una solicitud de autenticación pendiente, se ignoran envíos duplicados y el CTA permanece en estado procesando.

Frentes:

- F3-25c89fbd88f8c3e6: UI_VISUAL (CLOSED)

## Reutilización

| Requisito | Decisión | Archivos | Motivo |
| --- | --- | --- | --- |
| REQ-SBX-B2B-R-A11Y-CONTRAST | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-A11Y-FORCED-COLORS | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-A11Y-INTERACTION | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-A11Y-MOTION | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-AUTH-DENY-DEFAULT | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-AUTH-ENVELOPE | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-AUTH-FAIL-CLOSED | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-AUTH-GENERIC | REUSE_AS_IS | apps/time-service/src/main/java/lf/sandbox/time/auth/AuthController.java | declared_screen_dependency |
| REQ-SBX-B2B-R-AUTH-OUTCOMES | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-AUTH-REQUEST | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-AUTH-RUNTIME-PASSWORD | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-AUTH-SESSION-AFTER-AUTH | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-AUTH-TIMEOUT | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-DATA-ATTEMPTS | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-DATA-SESSIONS | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-DATA-USER-STORE | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-DESIGN-NO-HARDCODE | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-DESIGN-TOKENS | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-ERROR-CODE | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-ERROR-SAFE-MESSAGE | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-ERROR-TRACE | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-INT-EMAIL-LOGIN | EXTEND | apps/time-service/src/main/java/lf/sandbox/time/auth/AuthController.java, apps/time-service/src/main/java/lf/sandbox/time/auth/AuthService.java | declared_screen_dependency |
| REQ-SBX-B2B-R-INT-HOME | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-INT-RETURN | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-INT-ROUTE | EXTEND | frontend/src/app/sbx-rem-list/page.tsx, frontend/src/lib/sbx-rem-list.ts | declared_screen_dependency |
| REQ-SBX-B2B-R-INT-SESSION-STORE | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-LAYOUT-COMPOSITION | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-PRIVACY-TELEMETRY | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-RATE-LIMIT | REUSE_AS_IS | apps/time-service/src/main/java/lf/sandbox/time/auth/AuthController.java | declared_screen_dependency |
| REQ-SBX-B2B-R-RESP-BREAKPOINTS | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-SESSION-CONCURRENCY | REUSE_AS_IS | apps/time-service/src/main/java/lf/sandbox/time/auth/AuthController.java | declared_screen_dependency |
| REQ-SBX-B2B-R-SESSION-IDLE | REUSE_AS_IS | apps/time-service/src/main/java/lf/sandbox/time/auth/AuthController.java | declared_screen_dependency |
| REQ-SBX-B2B-R-THEME-LIGHT | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-UX-ACTIONS | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-UX-PASSWORD-MANAGERS | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-UX-PASSWORD-VISIBILITY | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-UX-RECOVERY | BUILD_NEW | Ninguno consignado | sin coincidencias |
| REQ-SBX-B2B-R-UX-SINGLE-FLIGHT | BUILD_NEW | Ninguno consignado | sin coincidencias |

## Lotes en orden

| Lote | Área | Rutas a escribir | Dependencias |
| --- | --- | --- | --- |
| SOL-Icb7267b7c8c3 | INFRA | apps/time-service/pom.xml, apps/time-service/src/main/resources/application.properties | Ninguno consignado |
| SOL-003 | DATA | apps/time-service/src/main/resources/db/migration/V1__sbx_b2b_login.sql, apps/time-service/src/main/resources/db/rollback/U1__sbx_b2b_login.sql | SOL-Icb7267b7c8c3 |
| SOL-Cf376a709e8a9 | CONTRATO | contracts/sbx-b2b-login.openapi.yaml | Ninguno consignado |
| SOL-002 | BACKEND | apps/time-service/src/main/java/lf/sandbox/time/auth/AuthController.java, apps/time-service/src/main/java/lf/sandbox/time/sbxb2blogin/SbxB2bLoginController.java, apps/time-service/src/main/java/lf/sandbox/time/sbxb2blogin/SbxB2bLoginService.java | SOL-003, SOL-Cf376a709e8a9 |
| SOL-001 | FRONTEND | frontend/src/app/home/page.tsx, frontend/src/app/sbx-b2b-login/page.tsx, frontend/src/app/sbx-rem-list/page.tsx, frontend/src/lib/sbx-b2b-login.ts | SOL-002, SOL-Cf376a709e8a9 |

Solo evidencia fuente; no acredita autoridad productiva.
