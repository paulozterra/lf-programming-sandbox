# CP3.2 — entrada simulada de orquestador

Esta entrada usa el paquete **ANALYSIS_IMPLEMENTATION_PACKAGE_V1** candidato de LF (A1–A9), con metadatos explícitos `analysis_mode` y `request_sha256`. No se ejecuta Análisis real ni se crea un PG-01 gobernado: se llama al preflight PG-01 C4/V3 fijado y se conserva su rechazo de autoridad bajo `FIXTURE_UNATTESTED`.

Para correr el ejemplo: `python3 pilot/orchestrator/intake.py --request-id sample-reminder-note`. El hash corresponde al UTF-8 de `request.md` normalizado a LF. `state.json` es estable byte a byte y no habilita etapas posteriores. No usar aquí el pedido real de login.
