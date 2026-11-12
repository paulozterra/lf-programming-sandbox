# CP3.2 — entrada simulada de orquestador

Esta entrada usa el paquete **ANALYSIS_IMPLEMENTATION_PACKAGE_V1** candidato de LF (A1–A9), con metadatos explícitos `analysis_mode` y `request_sha256`. No se ejecuta Análisis real ni se crea un PG-01 gobernado: se llama al preflight PG-01 C4/V3 fijado y se conserva su rechazo de autoridad bajo `FIXTURE_UNATTESTED`.

Para correr el ejemplo: `python3 pilot/orchestrator/intake.py --request-id sample-reminder-note`. El hash corresponde al UTF-8 de `request.md` normalizado a LF. `state.json` es estable byte a byte y no habilita etapas posteriores. No usar aquí el pedido real de login.

## CP3.3 — planificación determinista sobre productores fijados

Se llaman directamente los productores de `pilot/lf_producers_pinned/` PG-02 (clasificación), PG-03 (estrategia), PG-04 (partición, cobertura C7, DoD y revisión) y PG-05 (C1–C5 y handoff candidato). La integración original `pg05_profile_assignment_bridge_v1.py` declara áreas y rutas, consulta el selector experimental SQL PostgreSQL y verifica `pg06_currentness`. **No** se afirma que la proyección PG-07 de rol/skills se haya ejecutado: eso requiere los bindings de CP3.4.

La fuente `planning_fixture.json` explicita rutas exactas y preferencias de perfil del pedido simulado, sin fingir que A9 real las investigó. La selección definitiva del candidato se valida a través del selector experimental *original*. PG-01 sigue `FIXTURE_UNATTESTED`, y nunca hay autorización de escritura/ejecución.

Las pruebas de integración levantan PostgreSQL 17 en loopback del runner, cargan las migraciones, funciones y semillas fijadas y dejan la DB al final. No hay Supabase ni claves reales. El `lots.json` de `sample-three-area-notes` es una copia **exacta** del resultado de CI #43093724239 y se comprueba byte por byte en una nueva corrida.

Entradas: `pilot/runs/<pedido>/request.md`, `analysis.json`, `planning_fixture.json`, `state.json` previamente aceptado por CP3.2. Salidas: `lots.json`, `state.json` en `LOTS_PLANNED`. Repetir la planificación debe conservar los mismos bytes. Si falta SQL selector local, se bloquea con `SELECTOR_REQUIERE_ENTORNO`.
