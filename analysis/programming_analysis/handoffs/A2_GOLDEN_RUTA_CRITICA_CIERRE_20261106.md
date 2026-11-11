# LF — A2 Golden | Ruta crítica de cierre (2026-11-06)

**Decisión operativa:** detener expansión transversal y terminar A2 dentro de `PROGRAMMING_ANALYSIS_LF`, sin crear skill A2 independiente, alterar Router ni modificar gobernanza oficial por atajo. Este plan registra la **cantidad de entregables pendientes**, NO acredita completitud ni autoriza un despliegue.

## Estado contrastado con PR #3624, Supabase y fuentes locales

- PR #3624, HEAD de partida `a7ec1106ba81b69e482294c089c37c35de2953e0`, DRAFT y sin merge.
- Implementado como código candidato: `steps/a2/validators/run.py`, clasificación L3>L2>L1 basada exclusivamente en los predicados del contrato canónico `analysis_change_classification_contract_v1.json` (blob `0f07d3603c1bf3e4d2a4b9de5d6c3a3968bb4051`); preserva negocio y bloquea señales inválidas.
- El contrato canónico `ANALYSIS_CHANGE_CLASSIFICATION_V1` no contiene una salida dimensional 12/59. **No reescribir ese contrato** sin proceso gobernado; diseñar extensión separada/adaptación compatible con A3 y verificar la fuente.
- Artefacto Golden local separado, `A2_GOLDEN_CATALOGO_DIMENSIONAL_v0_2.json`, SHA256 `67c235e0b855086176a5f6b0f348095bdb96f711187c5772fd48987d2d1ef6ba`: 12 dimensiones, 59 elementos, 33 siempre activos y 26 condicionales, IDs únicos 59/59 y equivalencia exacta entre `dimensions[].element_ids` y `elements[].id`. **Solo DESIGN_ONLY_NOT_IMPLEMENTED**, ninguno de los 59 es contrato oficial.
- `A2_GOLDEN_CONTRATO_Y_TRAZABILIDAD_v0_3.md` es propuesta derivada: 23 predicados canónicos, ambos ejes aplicabilidad/cumplimiento y handoff dirigido. `A2_GOLDEN_MATRIZ_DIMENSIONAL_DINAMICA_v0_2.md` documenta correcciones P0. Son insumos locales del diseño, NO pruebas de implementación.
- Supabase real: 0 catálogo READY para `PROGRAMMING_ANALYSIS_LF`, 0 authority activo perfil→`EJECUCION_SKILL_LF`, 0 RUN de skill, 0 invocaciones, binding `false`, juez de operación con `judge_sha=NULL` y `pass_if=[]/fail_if=[]`.
- PR #3681 (Edge genérico) es un proyecto **infraestructura transversal**, separado. Sus 4 RPC/OIDC, matriz genérica de 23 invariantes y despliegue total NO equivalen a avances de A2 funcional. Consumir solo la mínima ruta gobernada indispensable.

## Cuatro hitos pendientes para cierre A2 operativo

| Hito | Trabajo exacto | Evidencia de aceptación | Estado |
|---|---|---|---|
| H1 — Completar A2 Golden | Implementar extensión tipada de 12/59 elementos, 2 ejes y 26 triggers sobre clasificador L1/L2/L3; sin N/A por UNKNOWN; emitir preguntas dirigidas A3. No duplicar reglas del catálogo. | 59/59 elementos, 12/12 dimensiones, 26 triggers y pruebas positivas/negativas con referencia exacta al catálogo; no ampliar el contrato canónico por atajo. | SOURCE_CANDIDATE_IMPLEMENTED; operacional PENDING |
| H2 — Entrada y fuente | Vincular A1 real, señales/evidencias de A2 y negocio exacto, con productor/snapshot y currentness acreditados por host; distinguir DECLARED vs VERIFIED. | READBACK del origen y 9 señales; rechazo de LF↔SALY, source drift y target no atestado. No inferir CURRENT de un texto. | PENDING (dependencia A1) |
| H3 — Juez A2 y reparación | Invocar juez semántico **existente** con independencia y recibo de output SHA, retroalimentación por elemento; original+2 correcciones máximo; no A3 en FAIL. | 1 PASS y reintentos reales con hashes/lineage; tres FAIL bloquean A3; pruebas adversariales sin juez autodeclarado. No confundir juez del RUN paso 70 con gate interno antes de A3. | PENDING |
| H4 — RUN nativo y E2E | Abrir `EJECUCION_SKILL_LF` desde perfil autorizado en el caller gobernado; paso 0, recorder común, readback e idempotencia, A2 PASS→A3 exactamente una vez. | Parent+child RUN, step 0, autoridad, fuente y juez verificados en Supabase, y E2E con caso real controlado; solo entonces permitir transición. | PENDING |

**Avance:** productor dimensional 12/59, 26 triggers y salida propuesta v0.3 implementados como código candidato con 41 pruebas locales PASS; H1 operacional aún PENDING. Clasificación L1/L2/L3 está implementada como candidato y ha tenido regresiones locales, pero **0/4 hitos Golden están cerrados con evidencia operacional**. No usar un porcentaje positivo como READY.

## Ejecución en lotes cortos

1. **Lote inmediato H1:** codificar únicamente modelo dimensional y tests; registrar exact source hashes, resultados y diff. Bloquear si catálogo local no está disponible/atestable en fuente versionada.
2. **Luego H2:** salida real A1, nueve señales y fuente auditada; no inventar recibos.
3. **Luego H3:** juez, reparación, PASS/fail y hash del mismo RUN.
4. **Finalmente H4:** solo la apertura mínima autorizada, sin convertir READ_ONLY en WRITE_GOVERNED, y E2E A1→A2→A3.

**Fuera del camino crítico A2** (seguir en PR #3681): calificación de todas las skills del catálogo, las cuatro RPC genéricas para todos los efectos, soporte para todas las fuentes no-GitHub, matrices universales y ampliaciones OIDC que no sean requisito del primer caso autorizado. No declarar como requisito A2 sin demostrar dependencia.

## Cierre gobernado

Cada hito requiere código, test ejecutado exact-HEAD, readback independiente, EKB consultada y resultado binario. El estado candidato no se promociona por fixtures. Main, Supabase, juez, Router, permisos y workflow oficial sin cambios en este documento. Cualquier admisión/despliegue o edición de fuente oficial exige trámite gobernado y aprobación correspondiente.
