# PG-03 C3–C9 — Reutilización verificada sin duplicar implementaciones

**Fecha:** 2026-11-03. **Rol:** inventario de contratos candidatos y brechas de integración; no aprobación ni revisión independiente. **Repositorio de trabajo:** `paulozterra/lf-programming-sandbox`. No se modifica `cristhianlujan/claude-persona-lf-patch` ni Supabase.

## Fuentes existentes examinadas

Los siguientes candidatos ya están en PRs DRAFT del repositorio de integración (lectura únicamente):

| Checkpoint | PR existente | Contrato / función candidata | Pendiente real |
|---|---|---|---|
| C3 | [#3498](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3498) | `pg03_strategy_v1.py::prepare_strategy` | Entrada PG-02 real, identidad de scopes, autenticación de stack y cobertura |
| C4 | [#3499](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3499) | `pg03_reuse_binding_v1.py` | Handoff A real y verificación REUSE_AS_IS |
| C5 | [#3500](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3500), [#3526](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3526) | `pg03_domain_judges_v1.py` | Fuente C3 autenticada, precedencia, juez semántico separado |
| C6 | [#3507](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3507) | `pg03_sufficiency_v1.py` | Evidencias auténticas de preguntas, requisitos y aceptación |
| C7 | [#3508](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3508) | `pg03_exception_routing_v1.py` | Decisiones de owner y políticas vigentes |
| C8 | [#3509](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3509) | `pg03_handoff_boundary_v1.py` | Validación de origen de strategy_ref y aseguramiento independiente |
| C9 | [#3523](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3523), [#3524](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3524) | Binding de sujeto y probe de autoridad | Revisor independiente y fuente CURRENT del mismo run |

C10: [PR #3510](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3510) contiene `pg03_architecture_d15_v1.py`. No copiar estas funciones al sandbox: su existencia ya está acreditada, su publicación NO.

## Hallazgos concretos de revisión estática

**C3 — Identidad y cardinalidad de scopes, revisión requerida.** En la fuente del PR #3498, `prepare_strategy()` exige `scopes` lista no vacía y `state=READY_FOR_CLASSIFICATION`, pero compone `scope_ids=sorted(x["scope_id"] for x in rows)` sin comprobar duplicados, valores vacíos ni formato de cada `scope_id`. Casos negativos por ejecutar en el código propietario: `scope_id` duplicado, vacío, ausente/no-string; deben bloquearse de manera tipada y no emitir estrategia candidata.

**C8 — strategy_ref no vinculado, revisión requerida.** En la fuente del PR #3509, `prepare_pg04_handoff()` solo comprueba que cada `solution_coverage[].strategy_ref` sea string no vacío; no verifica identidad contra el sujeto `strategy.candidate_sha256` (ni una referencia gobernada equivalente). Caso negativo requerido: `strategy_ref` bien formado pero apuntando a otra estrategia debe bloquearse. Esta brecha no autoriza handoff (el candidato deja `handoff_allowed=false`), pero dificulta integridad documental de C8 antes de la publicación.

**C5 — compatibilidad de formato, antes de integración.** El proyector candidato `pg03_domain_judges_v1.py::project_rules()` espera reglas con `text`, mientras que el catálogo v0.7.0 del sandbox almacena contenido en `rule`. No asumir que se pueden conectar directamente; requiere adaptador contractual autenticado que no invente niveles L1/L2 ni fuente CURRENT. No se agrega un segundo proyector.

Estos hallazgos son de **lectura de código, no pruebas dinámicas sobre los PR externos**. No declararlos corregidos hasta la ejecución y revisión exact-HEAD de sus implementaciones.

## Avance propio independiente

[Sandbox PR #19](https://github.com/paulozterra/lf-programming-sandbox/pull/19) endurece el `standards/tools/skills.py` original (selección ambigua y ensamble con alcance inválido) y añade `select_and_assemble(evidence, active, pin)`: una sola operación que selecciona Skills, construye el contexto y devuelve recibo `CANDIDATE_NOT_ADMITTED`, `production_authority=false`, `pg02_source_verified=false`. Esta es una entrada potencial a C3 que **no reemplaza** su estrategizador ni otorga autoridad.

## Ruta de salida

1. Terminar CI del PR #19 y congelar HEAD probado.
2. Probar contratos C3 y C8 con los casos adversariales anteriores en el entorno de integración adecuado, sin portarlos a ciegas.
3. Conectar la salida offline del sandbox con la estrategia candidata C3 solo bajo contrato explícito y fuentes verificadas; hasta entonces entrada C3 no autorizada.
4. Consumir C4–C10 existentes, no abrir una nueva implementación si el trabajo ya está en PRs.
5. Los estados oficiales permanecen `PENDING` hasta recibir evidencia y autoridad real.

**Prohibido con este expediente:** declarar PG-00 terminado, PG-03 cerrado, publicar C3, fusionar PR o escribir en Supabase.
