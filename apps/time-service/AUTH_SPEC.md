# AUTH_SPEC — Login SBX-AUTH-LOGIN (sandbox, ficticio)

Contrato técnico del lote BACKEND del pedido `pilot/runs/f5-login/` (paquete A9).
Las **reglas de negocio** (valores) vienen del paquete: `.lf/worker-context/f5backend/reglas_negocio.json`.
Aquí solo se fija la **forma** de la API para que el lote sea verificable.

## Endpoints

### `POST /api/auth/login`
Cuerpo JSON: `{"username": "<texto>", "password": "<texto>"}`.

- **Éxito → 200** `{"token": "<opaco, ≥16 caracteres>", "expiresAt": "<instante ISO-8601 UTC>"}`.
  `expiresAt` = momento del login + duración de sesión de la regla `SBX-R-ERR`.
- **Cualquier fallo → 401** con **exactamente el mismo cuerpo**: `{"error":"SBX-E-GENERIC"}`.
  Incluye: usuario inexistente, contraseña errónea, usuario o contraseña ausentes o vacíos, cuerpo vacío
  y usuario bloqueado. Nunca se devuelve token ni se distingue el motivo.

### `GET /api/auth/session`
Cabecera `Authorization: Bearer <token>`.
- Sesión vigente → **200** `{"username": "<usuario>"}`.
- Sin cabecera, token desconocido o sesión vencida → **401** `{"error":"SBX-E-GENERIC"}`.

## Comportamiento (de las reglas del paquete)
- `SBX-R-USER`, `SBX-R-PASS`: usuario y contraseña obligatorios.
- `SBX-R-LOCK`: tras `failed_attempts` fallos **consecutivos** de un usuario existente, el acceso queda
  bloqueado `lock_minutes` desde el último fallo (incluso con la contraseña correcta). Un login exitoso
  reinicia el contador.
- `SBX-R-HASH`: la contraseña se verifica contra el hash BCrypt de configuración
  (`org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`, dependencia ya incluida). Nunca se
  guarda ni se compara en claro.
- `SBX-R-ERR`: error genérico indistinguible y sesión de `session_minutes`.
- `SBX-R-LOG`: la contraseña nunca aparece en ningún log.

## Técnico
- Usuario por defecto desde configuración: `app.auth.default-username` y `app.auth.default-password-bcrypt`
  (ver `src/main/resources/application.properties` y `.env.example`). No se escriben usuarios ni hashes en el código.
- **Todo cálculo de tiempo usa el bean `java.time.Clock`** de `lf.sandbox.time.TimeConfig` (inyectado).
- Estado en memoria (sin base de datos), igual que los recordatorios.
- Credenciales de desarrollo (ficticias, solo sandbox): `demo` / `Sandbox-Demo-2026`.
