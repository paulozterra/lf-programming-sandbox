# Reutilizar componentes verificados
Usar los componentes citados sin modificarlos ni reimplementarlos.
Las rutas de reutilización son solo contexto protegido.
## apps/time-service/src/main/java/lf/sandbox/time/auth/AuthService.java
SHA-256: 402d1c7fe84c5315ee1af41ddc39c02086e6ac02a6e9e0ca876c0e8769722100
- method:LoginResult(String token, Instant expiresAt):record
- method:login(String username, String password):Optional<LoginResult>
- method:session(String authorization):Optional<String>
- type:AuthService
- type:LoginResult
