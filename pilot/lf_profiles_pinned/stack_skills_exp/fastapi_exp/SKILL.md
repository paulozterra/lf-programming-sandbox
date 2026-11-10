# FastAPI — stack skill de ENSAYO
**Estado:** CANDIDATE_SANDBOX_ONLY. **Área declarada:** BACKEND. **Código:** FASTAPI_EXP. **Versión:** 1.

## Vinculación
La skill se obtiene exclusivamente de project_stack_binding_exp por proyecto, área y versión con prioridad explícita; la IA no la escoge.

## Reglas expertas verificables
- **FA-01:** Definir rutas con APIRouter y dependencias mediante Depends según layout vigente del proyecto. **Fuente oficial:** https://fastapi.tiangolo.com/tutorial/dependencies/
- **FA-02:** Exigir validación de input y response_model de salida para preservar contratos HTTP y filtrar respuestas según el esquema. **Fuente oficial:** https://fastapi.tiangolo.com/tutorial/response-model/
- **FA-03:** Definir y probar HTTPException y manejo de errores sin divulgar información interna. **Fuente oficial:** https://fastapi.tiangolo.com/tutorial/handling-errors/
- **FA-04:** Probar rutas con TestClient y pytest cuando estén disponibles, incluyendo solicitudes válidas e inválidas. **Fuente oficial:** https://fastapi.tiangolo.com/tutorial/testing/
- **FA-05:** En pruebas reemplazar dependencias con app.dependency_overrides y limpiar overrides al terminar. **Fuente oficial:** https://fastapi.tiangolo.com/advanced/testing-dependencies-overrides/

## L1/L2 y L3
Familia `STD-BE` referenciada en `supabase/migrations/20261028160000_lf_programming_pg00_standards_checkpoints_decisions_v2.sql`, que NO contiene el texto normativo completo. `PG00_STANDARD_TEXT_UNAVAILABLE` hasta recuperar el catálogo canónico versionado con huella. Guías del stack no sustituyen normas internas LF.

## Salida y límites
Pasar al Worker visible un mínimo de tres reglas verificadas de esta skill, con ID y fuente; no incluir oráculo ni autoridad. `production_authority=false`; `runtime_enabled=false`; `promotion_allowed=false`.
