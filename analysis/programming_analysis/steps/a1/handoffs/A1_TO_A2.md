> **Nota de arquitectura 2026-11-04:** A1 es un paso **interno** de la única skill `PROGRAMMING_ANALYSIS_LF`. Este artefacto procede del antiguo candidato individual; sus referencias a ejecución/registro deben interpretarse a nivel de la **skill completa**. No documenta una habilidad A1 registrable ni recibos operativos.

# A1 → A2, solo contrato de contenido

A1 devuelve `payload: REQUEST_CONTEXT_V1` y la declaración `declared_intent_kind` sin interpretación. Si `status=VALID_OUTPUT`, el **perfil consumidor**, tras su validación de ticket/autoridad/receipt, decide cuándo llamar A2. A2 decide tipo de cambio, granularidad y L1/L2/L3. Ninguna llamada a A2 ocurre dentro de A1. `business` viaja en el envelope de transporte, nunca como campo extra en el contrato canónico de A1.

Si falta target: `NEED_MORE_EVIDENCE`, si hay ambigüedad material: `REQUIRES_DECISION`, entrada inválida/fuente sin respaldo: `BLOCKED`. No mover estados de implementación.
