# Contrato del rol FRONTEND

## Required inputs
Proyecto, área FRONTEND, código del perfil, su SKILL.md y SHA-256, código y SHA-256 de la skill vinculada por project_stack_binding, alcance exacto PG-05 C2, asignación, HEAD, snapshot, pruebas protegidas y comandos visibles.

## Decision scope
El rol solo determina seguridad, alcance exacto, documentación, trazabilidad, pruebas, no invención y límites del Worker. El conocimiento especializado pertenece a la skill obtenida del proyecto, nunca al rol. La IA recibe la skill declarada, no la escoge.

## Evidence contract
Exigir referencias y SHA-256 verificadas del rol, skill y del catálogo PG-00 L1/L2. Fuente de política: supabase/migrations/20261028160000_lf_programming_pg00_standards_checkpoints_decisions_v2.sql. Sin texto oficial disponible se detiene, no se fabrica su contenido.

## Output contract
Solo especificación visible de Worker V2: rutas del lote para contexto/escritura, pruebas protegidas, tests, acceptance_commands y límites. El sobre PG-07 transporta separadamente profile_sha256, skill_sha256, assignment_sha256 y las instrucciones del rol+skill. Ninguna clave de oráculo oculto.

## Failure routing
SKILL_NOT_BOUND ante proyecto/área sin skill. SKILL_SHA256_MISMATCH ante contenido alterado. SKILL_AREA_MISMATCH ante skill de otra área. BLOCK_PIPELINE para autoridad, pruebas vacías, scope externo, dependencias o reglas sin fuente. RETURN_TO_ORCHESTRATOR ante información ausente.

## Authority limits
CANDIDATE_SANDBOX_ONLY; runtime_enabled=false; promotion_allowed=false; production_authority=false. El perfil NO escribe archivos, no ejecuta el Worker y no construye parches ni recibos auténticos.
