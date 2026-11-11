# Ejemplo de resultado (no recibo operativo)

Entrada: `fixtures/valid_lf.json`.

`status = VALID_OUTPUT`, `skill_code = PROGRAMMING_ANALYSIS_LF`, `business = LF`, `payload.schema_version = REQUEST_CONTEXT_V1`, `payload.no_solution_inferred = true`, `next_capability = A2`.

`declared_intent_kind = UNKNOWN` no se convierte en nueva funcionalidad, evolución o mixto. La clasificación funcional pertenece a A2.

`external_authority_verified = false`, `operationally_integrated = false`, `effects_executed = false`. Ningún dato demuestra llamada del perfil, ticket consumido o escritura en Supabase.
