# Reutilizar componentes verificados
Usar los componentes citados sin modificarlos ni reimplementarlos.
Las rutas de reutilización son solo contexto protegido.
## apps/time-service/src/main/java/lf/sandbox/time/auth/AuthController.java
SHA-256: b84729e36426d079ffe5bf140ea1155c5327a3820821a2fd72081d5d32162937
- GET /api/auth/session
- POST /api/auth/login
- method:B2bLoginFailure(String outcome, String correlation_id, String error_code):record
- method:B2bLoginResponse(String outcome, String correlation_id, String token):record
- method:LoginResponse(String token, String expiresAt):record
- method:SessionResponse(String username):record
- method:invalidLoginBody():ResponseEntity<Map<String, String>>
- method:login(@RequestBody(required = false):ResponseEntity<?>
- method:session(@RequestHeader(name = "Authorization", required = false):ResponseEntity<?>
- type:AuthController
- type:B2bLoginFailure
- type:B2bLoginResponse
- type:LoginResponse
- type:SessionResponse
## apps/time-service/src/main/java/lf/sandbox/time/auth/AuthService.java
SHA-256: 402d1c7fe84c5315ee1af41ddc39c02086e6ac02a6e9e0ca876c0e8769722100
- method:LoginResult(String token, Instant expiresAt):record
- method:login(String username, String password):Optional<LoginResult>
- method:session(String authorization):Optional<String>
- type:AuthService
- type:LoginResult
## apps/time-service/src/main/resources/db/migration/V1__sbx_b2b_login.sql
SHA-256: e1beac1bdebb9d987d91feb519e8cf54cd82d8631c613d3b3ec876495b1bd3c5
## apps/time-service/src/main/resources/db/rollback/U1__sbx_b2b_login.sql
SHA-256: d921ec6633302d9a97824dcea0c7ba56562bd1bd6528d8a78f0cfdc89c6f2f2e
## frontend/src/app/sbx-b2b-login/page.tsx
SHA-256: 0a0dbfe44f3562cbbce78145ee3e67258f025b58c37a87ba3ded76b7162efd83
- PAGE /sbx-b2b-login
- export:SbxB2bLoginPage
## frontend/src/app/sbx-rem-list/page.tsx
SHA-256: 86ad1e64a4fcc973c98a7643c6d627ad43795c3f1f37353ce674eca388d9a27a
- PAGE /sbx-rem-list
- export:SbxRemListPage
## frontend/src/lib/sbx-b2b-login.ts
SHA-256: 07faec9d3a30ded70f5b7294c1a835ff081218d8e57b312c4dd508de3073f6e0
- export:ErrorCode
- export:LOGIN_ROUTE
- export:REMINDERS_ROUTE
- export:Result
- export:SESSION_KEY
- export:authenticate
- export:errorCatalog
- export:returnPath
- export:tokens
## frontend/src/lib/sbx-rem-list.ts
SHA-256: 7da9814a82e2ad124b938c7fd28db9159f2e93ea84eb4f90dc72d8e747a4ca78
- export:Reminder
- export:ReminderPriority
- export:listReminders
