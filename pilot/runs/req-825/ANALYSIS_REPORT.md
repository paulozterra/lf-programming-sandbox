# Informe del análisis (candidato simulado)

## Pedido literal

```text
Implementa DEMO-FORMAT-CANARY
```

- Autor: paulozterra
- Issue: #825
- Fecha: 2026-11-26T21:45:34Z
- Pantalla: DEMO-FORMAT-CANARY
- Modo: SIMULATED_ANALYSIS

## Reglas de la ficha

| Código | Título | Descripción |
| --- | --- | --- |
| FORMAT-CANARY-VALIDATION | Validación de seguridad de identificador | El servicio Java aislado del canary valida un identificador no confiable mediante lista permitida: acepta únicamente la cadena exacta canary-ok y rechaza cualquier otra cadena o null con IllegalArgumentException, sin incluir la entrada en el mensaje. Sin persistencia ni interfaz. |

## Etapas A1–A9

| Etapa | Estado | Significado |
| --- | --- | --- |
| A1 | VALID_OUTPUT | La entrada del pedido produjo una salida estructurada válida |
| A2 | NEED_MORE_EVIDENCE | Falta evidencia suficiente para considerar acreditada la información |
| A3 | SOURCE_READBACK_PROCESSED_UNATTESTED | Se procesó la ficha fuente, sin acreditar autoridad de producción |
| A4 | PLANNED_BUILD_IMPACT_UNATTESTED | Se identificó impacto de implementación, pendiente de acreditación |
| A5 | UNRESOLVED | Las decisiones de gobierno o autoridad siguen sin resolverse |
| A6 | CANDIDATE_ONLY | Las obligaciones WHAT son candidatas, no aprobaciones productivas |
| A7 | CANDIDATE_ONLY | Los frentes y su alcance son candidatos, no autorizaciones |
| A8 | CANDIDATE_ONLY | La comprobación de cobertura permanece en estado candidato |
| A9 | SIMULATED_PACKAGE_CANDIDATE | Se produjo un paquete de implementación simulado |

## Clasificación

| Campo | Valor |
| --- | --- |
| authority_state | UNKNOWN |
| change_type | CREATE |
| depth | L3 |
| depth_reason_predicates | ["materiality_level=HIGH"] |
| implementation_state | NEW |
| target_granularity | SCREEN |

## Desconocidos

- {"code": "SIMULATED_SANDBOX_ONLY_NO_PRODUCTION_AUTHORITY", "source_ref": "fixture://DEMO-FORMAT-CANARY"}

## Decisiones pendientes

- Ninguno consignado

## Requisitos y frentes por área

### DATA

Requisitos:

- Ninguno consignado

Frentes:

- Ninguno consignado

### BACKEND

Requisitos:

- REQ-FORMAT-CANARY-VALIDATION: El servicio Java aislado valida un identificador no confiable mediante lista permitida: acepta únicamente canary-ok; cualquier otra cadena o null produce IllegalArgumentException con mensaje constante sin reflejar la entrada.

Frentes:

- F3-e48543c7875f8770: API_CONTRACT (CLOSED)

### FRONTEND

Requisitos:

- Ninguno consignado

Frentes:

- Ninguno consignado

## Reutilización

| Requisito | Decisión | Archivos | Motivo |
| --- | --- | --- | --- |
| REQ-FORMAT-CANARY-VALIDATION | BUILD_NEW | Ninguno consignado | sin coincidencias |

## Lotes en orden

| Lote | Área | Rutas a escribir | Dependencias |
| --- | --- | --- | --- |
| SOL-001 | BACKEND | apps/time-service/src/main/java/lf/sandbox/time/formatcanary/FormatCanaryController.java, apps/time-service/src/main/java/lf/sandbox/time/formatcanary/FormatCanaryService.java | Ninguno consignado |

Solo evidencia fuente; no acredita autoridad productiva.
