# Reutilizar componentes verificados
Usar los componentes citados sin modificarlos ni reimplementarlos.
Las rutas de reutilización son solo contexto protegido.
## apps/time-service/src/main/java/lf/sandbox/time/auth/AuthController.java
SHA-256: 73443eb852d7e1fbd11dcc9ddcf471c97bea7779f3eb4b4faa9c36b6c2fecb78
- GET /api/auth/session
- POST /api/auth/login
- method:LoginResponse(String token, String expiresAt):record
- method:SessionResponse(String username):record
- method:invalidLoginBody():ResponseEntity<Map<String, String>>
- method:login(@RequestBody(required = false):ResponseEntity<?>
- method:session(@RequestHeader(name = "Authorization", required = false):ResponseEntity<?>
- type:AuthController
- type:LoginResponse
- type:SessionResponse
## apps/time-service/src/main/java/lf/sandbox/time/auth/AuthService.java
SHA-256: 402d1c7fe84c5315ee1af41ddc39c02086e6ac02a6e9e0ca876c0e8769722100
- method:LoginResult(String token, Instant expiresAt):record
- method:login(String username, String password):Optional<LoginResult>
- method:session(String authorization):Optional<String>
- type:AuthService
- type:LoginResult
## frontend/src/lib/sbx-rem-list.ts
SHA-256: 7da9814a82e2ad124b938c7fd28db9159f2e93ea84eb4f90dc72d8e747a4ca78
- export:Reminder
- export:ReminderPriority
- export:listReminders
