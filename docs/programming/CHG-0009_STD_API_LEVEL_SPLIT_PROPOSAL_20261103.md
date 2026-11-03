# CHG-0009 — Propuesta de clasificación STD-API por regla (C9 / PG-03_C2)

**Estado:** `DRAFT_FOR_INDEPENDENT_REVIEW`. **No aprobado como norma**, sin merge, sin publicación C3 y sin autorización productiva.  
**Decisión del owner:** 03/11/2026, acepta como **base de trabajo** 2 L1, 4 L2 y 3 mixtas, y ordena preparar C9 sin publicar ni fusionar antes de las revisiones. Esto **no** equivale a aprobar textos definitivos, división de IDs, clase de cambio o release.  
**Origen congelado:** `paulozterra/lf-programming-sandbox@ab361cf947fb9a34c874bf3e786b7f7478c85aa9`, `standards/catalog.json` v0.7.0 en BORRADOR. Inventario previo: PR #17 HEAD `75ae4b84d2a1d213985b2d60412b4bf507520713`. Se reutiliza, no se reemplaza.

## Matriz: nueve reglas completas, sin omisiones

| Regla fuente | Propuesta | Qué conservar / decisión a revisar |
|---|---|---|
| STD-API-01 | L2 | Convención de versión `/api/v1/` en REST propia y `_vN` en Supabase; sin debilitar compatibilidad de STD-API-09 |
| STD-API-02 | L2 | Rutas/params (recursos plurales, kebab-case, excepciones contractuales) |
| STD-API-03 | L2 | `snake_case` según D3, sin renombrar contratos legados sin migración |
| STD-API-04 | MIXTA | L1 no exponer stack trace, SQL ni secretos/detalles internos; L2 forma exacta de errores sujeta a D1/D2 y contratos actuales |
| STD-API-05 | MIXTA | L1 garantías de idempotencia, trazabilidad y limitación/protección de abuso **cuando apliquen al riesgo/operación**; L2 convenciones concretas de headers, respuestas 429 y `Retry-After` según contratos D8/D9 |
| STD-API-06 | L1 | Contrato antes de la implementación de API o RPC **cuando se crea o modifica la interfaz**; no implica crear API inexistente |
| STD-API-07 | L2 | Convenciones para `page,size,sort` y `p_limit,p_offset` |
| STD-API-08 | MIXTA | L1 precisión y seguridad de cálculos/montos; L2 transporte como string decimal, currency y `numeric(18,2)` según D10 y contrato vigente; no cambiar representación sin migración |
| STD-API-09 | L1 | Compatibilidad con consumidores ante cambios incompatibles; no romper API previa en silencio; versionado concreto subordinado a contrato existente |

Distribución **2 L1, 4 L2 y 3 MIXTAS**. La severidad `BLOCK/WARN` **no** determina el nivel. El catálogo actual no contiene campo `rules[].level` para este dominio; nunca atribuir valores actuales a la fuente.

## Diseño de la descomposición (ID provisional; sujeto a revisión)

El catálogo aún no contiene IDs secundarios. Proponer separaciones internas de las tres reglas, sin eliminar el ID original antes de aprobar migración de referencias:

| Regla | Propuesta L1 | Propuesta L2 | Trazabilidad y cobertura |
|---|---|---|---|
| STD-API-04 | `STD-API-10` protección de información interna | `STD-API-11` formato de error | preservar referencias REG_TEC_010, D1/D2 |
| STD-API-05 | `STD-API-12` garantías operativas aplicables | `STD-API-13` nomenclatura/protocolo | preservar REG_API_005, D8/D9, idempotencia, request/correlation ID, rate limit |
| STD-API-08 | `STD-API-14` precisión monetaria | `STD-API-15` representación bajo contrato | preservar D10, decimal y currency |

**H01 — IDs propuestos, no normativos:** se proponen seis identificadores `STD-API-10` a `STD-API-15`, compatibles con la expresión `^STD-[A-Z]+-[0-9]{2}$` del validador vigente. Estos identificadores siguen **provisionales y sin reservar**; la auditoría definitiva debe confirmar que no colisionan con un HEAD posterior y aprobar el mapa `04→10/11`, `05→12/13`, `08→14/15`. Las referencias de consumidores, Skills, tests y waivers requieren migración explícita. No se debe mantener simultáneamente el original mixto y ambos desdobles como reglas operativas sin política de transición y cobertura.

## Remedios de H01–H04 propuestos para revisión (sin modificación normativa)

**H01 — IDs y migración:** asignar provisionalmente `STD-API-10` (04 seguridad L1), `11` (04 formato L2), `12` (05 garantías L1), `13` (05 protocolo L2), `14` (08 exactitud monetaria L1), `15` (08 representación L2). Confirmar que no colisionan con la revisión vigente cuando se aplique el cambio y que cada consumidor/Skill/waiver/tests/refs se migra de forma íntegra. No deshabilitar silenciosamente referencias antiguas. Conservar el catálogo v0.7.0 sin cambios hasta la aprobación final.

**H02 — seguridad vinculada a IDs:** `STD-API-04` está en `NON_WAIVABLE` (`standards/tools/policy_invariants.py`) y `SECURITY_IDS` (`standards/tools/changes.py`). En la eventual migración, proponer `NON_WAIVABLE += STD-API-10` y `SECURITY_IDS += STD-API-10, STD-API-11` **manteniendo el ID original protegido durante la transición**. `STD-API-10` debe conservar `waiver_policy.allowed=false`, y ninguna regla de seguridad debe admitir relajación por renombre. El futuro CHG debe tratar la mutación de 04 como `SECURITY`, activar el circuito de revisión independiente y la invalidación de pins exigida por C9. La propuesta **no aplica** esas modificaciones aún.

**H03 — matriz atómica y verificable, con alcance por contrato:**

| Fuente | Obligación original | Regla candidata | Referencia | Prueba requerida en cambio normativo |
|---|---|---|---|---|
| 04 | No exponer SQL, stack traces ni detalles internos | STD-API-10 L1 | REG_TEC_010 | negativos de filtración, no waiver |
| 04 | Formato de errores y códigos existentes | STD-API-11 L2 | D1, D2 | contrato REST/RPC, legado preservado |
| 05 | Idempotencia cuando la operación la requiera | STD-API-12 L1 | D8, REG_API_005 | reintento seguro y no duplicación de efecto |
| 05 | Request ID y correlación de punta a punta | STD-API-12 L1 | D9 | rastreo de la misma correlación sin datos sensibles |
| 05 | Limitación contra abuso cuando corresponda | STD-API-12 L1 | REG_API_005 | no bypass del control aplicable |
| 05 | Header concreto Idempotency-Key (o legado) | STD-API-13 L2 | D8 | compatibilidad de header y consumidores |
| 05 | X-Request-Id, X-Correlation-Id, 429, Retry-After | STD-API-13 L2 | D9, REG_API_005 | contrato de headers y tratamiento 429 |
| 08 | Exactitud: evitar errores de punto flotante en montos | STD-API-14 L1 | D10 | valores monetarios sin pérdida de precisión |
| 08 | Transporte amount como texto decimal + currency | STD-API-15 L2 | D10 | contrato API, backward-compatibility |
| 08 | numeric(18,2) y esquema BD asociado | STD-API-15 L2 | D10 | migraciones sin pérdida de datos |

**Cuidado semántico:** la ubicación L2 de un formato o de `numeric(18,2)` no permite una implementación que viole exactitud L1, ni saltarse un contrato existente. La idempotencia de una operación con efectos, la correlación y el rate limit deben tener aplicabilidad explícita y comprobada por contrato; no interpretar que toda API precisa el mismo conjunto de medidas.

**H04 — materialización C9:** `standards/changes/proposals/CHG-0009.draft.json` seguirá con `LF_STANDARD_CHANGE_PROPOSAL_V1`; no trasladarlo a `standards/changes/CHG-0009.json` ni inventar `approved_by`. En el futuro diff normativo determinar `change_class` real (incluida `SECURITY` por 04), conflicto `RELAXING/TIGHTENING`, posibles CHG separados, `security_pin_invalidation`, bump de versión y huellas/revisión del SHA exacto. Revisión separada del autor obligatoria antes de GO del owner.

## Orden de aprobación y criterios de NO-GO

1. Revisar contra el catálogo fuente exacto que ningún detalle de las nueve reglas o sus referencias desaparezca y que ninguna convención L2 rebaje un contrato legado VIGENTE o una obligación L1.
2. Revisar la semántica L1 de `STD-API-05`: riesgo/operación aplicable, no imponer idempotencia o rate limit indiscriminadamente a cualquier solicitud. Revisar L1 de `STD-API-06`: contrato primero cuando hay interfaz afectada. Revisar `STD-API-08` bajo D10 y autoridad de precisión monetaria.
3. Clasificar el *diff real* mediante `standards/tools/changes.py check` según C9. **El cambio toca una regla marcada de seguridad (`STD-API-04`)**: preparar revisión independiente de clase `SECURITY`, revisar invalidación de pins y separación de cambios RELAXING/TIGHTENING si aparecen. No escoger clase inferior por comodidad.
4. Registrar CHG activo **solo después de determinar diff normativo y revisión válida sobre SHA exacto**; `approved_by` en JSON no es recibo de GO. `CHG-0009` en este PR es un **expediente propuesto**, no `standards/changes/CHG-0009.json` activo.
5. Aplicar cambios normativos en un PR posterior o revisión del mismo PR solo bajo aprobación expresa; actualizar `standards/catalog.json`, regenerar `CATALOGO.md`, bump de versión según semver C9, actualizar tests, Skills y pins pertinentes; no alterar la fuente v0.7.0 por este expediente.
6. CI + negativos de seguridad, precedencia L1>A>B>L2 y migración de referencias; revisión independiente *exact HEAD*, decisión humana de merge, publicación gobernada en C3 y readback de `CURRENT`, digest y nivel por regla.
7. PG-03_C2 sigue `PENDING` hasta fuente vigente verificable y ejecución de selector/precedencia con vínculos del mismo run. PG-01_C6 real, L3 B real y despacho son dependencias separadas.

**Alcance de esta rama:** solo propuesta y prueba de su paridad con la fuente. No cambia `standards/catalog.json`, no crea CHG activo, no altera SQL/Router, no toca A1–A9, no hace merge ni publicación.
