# PG-03_C2 — Matriz de decisión de reglas STD-API L1/L2

**Fecha de auditoría:** 2026-11-03  
**Fuente exacta:** `paulozterra/lf-programming-sandbox` PR #13, commit `ab361cf947fb9a34c874bf3e786b7f7478c85aa9`, `standards/catalog.json`.  
**Estado:** `REQUIRES_OWNER_DECISION / NO_GO_PG03_C2`. Este inventario **no modifica el reglamento** ni determina niveles por inferencia.

## Regla de precedencia vigente en fuente

`L1 > A (Fase 1) > B (manifiesto del proyecto) > L2`.

El dominio `STD-API` tiene `level: "L1/L2"` en `domains[]`. Ninguna de sus nueve reglas trae `level` propio. Por eso no es demostrable cuál es el piso L1 frente a un tipo A o B, y el validador candidato de PG-03_C2 debe devolver `MIXED_DOMAIN_RULE_LEVEL_MISSING` para cada regla seleccionada hasta que exista una asignación gobernada.

| Regla | Contenido tomado de la fuente | Referencia fuente | Nivel verificado |
|---|---|---|---|
| STD-API-01 | Versionado de rutas /api/v1 y RPC _vN | antecedente REG_API_001 | SIN ASIGNAR |
| STD-API-02 | Convenciones de rutas y parámetros | No declara | SIN ASIGNAR |
| STD-API-03 | snake_case en contrato (D3) | D3 en texto | SIN ASIGNAR |
| STD-API-04 | Manejo de errores D1/D2; sin stack trace ni SQL | REG_TEC_010, D1/D2 | SIN ASIGNAR |
| STD-API-05 | Idempotencia, request/correlation ID y rate limit | REG_API_005, D8/D9 | SIN ASIGNAR |
| STD-API-06 | Contrato primero: OpenAPI o RPC | No declara | SIN ASIGNAR |
| STD-API-07 | Paginación, filtros y orden | No declara | SIN ASIGNAR |
| STD-API-08 | Montos decimales y currency (D10) | D10 en texto | SIN ASIGNAR |
| STD-API-09 | Cambios incompatibles exigen nueva versión | No declara | SIN ASIGNAR |

**Precaución:** `severity: BLOCK` no significa necesariamente `level: L1`; incluso una regla `WARN` puede tener un nivel de aplicación diferente. Las referencias a REG/ADR tampoco autorizan por sí solas clasificar automáticamente todo el contenido como L1.

## Decisión necesaria, sin asumir aprobación

El responsable del reglamento debe definir para **cada una** de las nueve reglas si es **L1** (piso no rebajable), **L2** (por defecto y subordinado a A/B) o si debe **descomponerse** porque reúne obligaciones de ambos niveles. Si se descompone, corresponde identificar IDs, referencias, clasificación y circuito C9 de actualización; una división no puede perder exigencias de seguridad.

Después de la decisión: registrar el CHG correspondiente y revisión independiente; actualizar el catálogo canónico y su vista generada; ejecutar validación negativa de seguridad, precedencia y regresión; publicar C3 por la ruta gobernada; y obtener un **readback independiente** de los niveles por regla antes de acreditar PG-03_C2.

## Dependencias separadas

El presente documento **no** certifica la ejecución del selector C6, las reglas L3 tipo B, los recibos PG-01_C6, la publicación de C3 ni la revisión semántica. Ningún PR debe fusionarse solo por estar verde el CI.

**Política de esta rama:** documento de evidencia y regresión informativa. No otorga `approved_by`, no crea `CHG` aprobado, no modifica `standards/catalog.json` y no autoriza producción.
