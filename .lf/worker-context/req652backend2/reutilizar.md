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
## apps/time-service/src/main/resources/db/migration/V1__sbx_b2b_login.sql
SHA-256: e1beac1bdebb9d987d91feb519e8cf54cd82d8631c613d3b3ec876495b1bd3c5
## apps/time-service/src/main/resources/db/rollback/U1__sbx_b2b_login.sql
SHA-256: d921ec6633302d9a97824dcea0c7ba56562bd1bd6528d8a78f0cfdc89c6f2f2e
