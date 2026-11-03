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
| STD-API-04 | `STD-API-04-L1` protección de información interna | `STD-API-04-L2` formato de error | preservar referencias REG_TEC_010, D1/D2 |
| STD-API-05 | `STD-API-05-L1` garantías operativas aplicables | `STD-API-05-L2` nomenclatura/protocolo | preservar REG_API_005, D8/D9, idempotencia, request/correlation ID, rate limit |
| STD-API-08 | `STD-API-08-L1` precisión monetaria | `STD-API-08-L2` representación bajo contrato | preservar D10, decimal y currency |

**Los IDs anteriores son marcadores de propuesta, no IDs canónicos reservados.** El revisor debe resolver si el esquema de IDs acepta sufijos o requiere IDs nuevos `STD-API-10+` y proveer mapa de migración `old_id -> new_ids`. En toda variante, las referencias de Skills, tests, excepciones y consumidores deben migrar explícitamente, sin silenciosa pérdida de obligaciones. No se puede conservar como regla operativa simultáneamente el original mixto y sus desdobles sin política de precedencia/cobertura.

## Orden de aprobación y criterios de NO-GO

1. Revisar contra el catálogo fuente exacto que ningún detalle de las nueve reglas o sus referencias desaparezca y que ninguna convención L2 rebaje un contrato legado VIGENTE o una obligación L1.
2. Revisar la semántica L1 de `STD-API-05`: riesgo/operación aplicable, no imponer idempotencia o rate limit indiscriminadamente a cualquier solicitud. Revisar L1 de `STD-API-06`: contrato primero cuando hay interfaz afectada. Revisar `STD-API-08` bajo D10 y autoridad de precisión monetaria.
3. Clasificar el *diff real* mediante `standards/tools/changes.py check` según C9. **El cambio toca una regla marcada de seguridad (`STD-API-04`)**: preparar revisión independiente de clase `SECURITY`, revisar invalidación de pins y separación de cambios RELAXING/TIGHTENING si aparecen. No escoger clase inferior por comodidad.
4. Registrar CHG activo **solo después de determinar diff normativo y revisión válida sobre SHA exacto**; `approved_by` en JSON no es recibo de GO. `CHG-0009` en este PR es un **expediente propuesto**, no `standards/changes/CHG-0009.json` activo.
5. Aplicar cambios normativos en un PR posterior o revisión del mismo PR solo bajo aprobación expresa; actualizar `standards/catalog.json`, regenerar `CATALOGO.md`, bump de versión según semver C9, actualizar tests, Skills y pins pertinentes; no alterar la fuente v0.7.0 por este expediente.
6. CI + negativos de seguridad, precedencia L1>A>B>L2 y migración de referencias; revisión independiente *exact HEAD*, decisión humana de merge, publicación gobernada en C3 y readback de `CURRENT`, digest y nivel por regla.
7. PG-03_C2 sigue `PENDING` hasta fuente vigente verificable y ejecución de selector/precedencia con vínculos del mismo run. PG-01_C6 real, L3 B real y despacho son dependencias separadas.

**Alcance de esta rama:** solo propuesta y prueba de su paridad con la fuente. No cambia `standards/catalog.json`, no crea CHG activo, no altera SQL/Router, no toca A1–A9, no hace merge ni publicación.
