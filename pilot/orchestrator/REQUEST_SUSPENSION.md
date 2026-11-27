# D22 — suspensión gobernada por pedido (borrador de implementación)

El estado del issue y la evidencia funcional siguen intactos. El control versionado está vacío al introducirse; este PR no suspende req-652 ni autoriza la reanudación de ningún pedido.

- ACTIVE/ausente: ruta normal. SUSPENDING: denegar efectos nuevos y drenar trabajos anteriores. SUSPENDED: denegar efectos, después de verificar drenaje. CLOSED_CANCELLED y CLOSED_FINALIZED mantienen su significado. La etiqueta lf-request-blocked no es autorización ni suspensión.
- La lectura es fresca desde main mediante la API de confianza; ausencia del archivo, respuesta inválida, PR no integrado o huella histórica no coincidente bloquean. No se cambia el plan, registro ni presupuesto.
- Transiciones propuestas: ACTIVE → SUSPENDING → SUSPENDED → ACTIVE. Cada transición requiere PR separado con CHG, revisión independiente, CI y Train. No borrar entradas ni reutilizar números de PR. El owner debe acreditar el drenaje antes de SUSPENDED: enumerar corridas activas/pendientes, PR de examen e integración, reservas externas; esperar terminación o cancelación gobernada sin falsificar intentos. La comprobación anterior a un efecto no es una transacción atómica con GitHub; no declarar aislamiento efectivo hasta que no haya ejecutores antiguos.

## Estado de construcción

Núcleo y pruebas sintéticas en este PR. Antes de autorizar su merge faltan la integración del validador de transiciones con Train, cobertura de Policy C/Train de PR existentes, examinador y T9, pruebas de todas las fronteras (incluidas recuperación y eventos tardíos), adaptar dobles de API, CI verde y revisión independiente. No integrar una implementación parcial ni aplicar una suspensión hasta cumplir estos controles. No ejecutar Worker real para las regresiones.
