# Contratos OpenAPI por funcionalidad

La ruta T2 genera un lote CONTRATO por funcionalidad con áreas BACKEND y FRONTEND.
Cada lote escribe `contracts/<module>.openapi.yaml` desde el paquete de Análisis,
sin inventar endpoints ni estados HTTP que no estén en la fuente. El validador
`pilot/orchestrator/contract_validate.py` verifica versión 3.x, cobertura
`x-requirement-ids`, errores declarados y ejemplos sin credenciales.
La ruta de CI coteja operaciones contra el servidor Spring Boot en ejecución
y verifica los tipos `frontend/src/lib/api/generated/`. No se incluyen
contratos de casos individuales como preparación global.
