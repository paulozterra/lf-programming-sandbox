# F1 — SBX-AUTH-LOGIN (100 % ficticio)

Contrato técnico **solo para pruebas offline**. No hay consultas a Supabase, secretos, aprobación ni atestación. Ninguna fuente corresponde a una pantalla real de LF.

## Identidad y procedencia: decisión D-AN4/D-AN5, opción A

Los productores A1–A5 del perfil fijo exigen el discriminador `business="LF"` y, para A3, referencias exactas `supabase://lf_ops.pantallas/SBX-AUTH-LOGIN` y `supabase://programacion.fn_input_effective_rule_links_v1/900001/INPUT_GOVERNANCE`. El host los aporta **exclusivamente como cadenas sintéticas de compatibilidad** para productores que no se alteran. No son fuentes consultadas, ni prueba de autoridad, ni credenciales. `SBX-AUTH-LOGIN` y todos los códigos de negocio empiezan por `SBX-`; los enteros 900001, 900002, 900081, etc. son sustitutos inventados porque A3 exige identificadores numéricos.

La **procedencia efectiva** de cada lectura se registra separadamente como `fixture://sbx_auth_login/<archivo>@<sha256>`. `fixture_manifest.json` fija la huella de los bytes y el nombre de la fuente simulada. El host rechaza archivos ausentes, hashes alterados y campos obligatorios ausentes. Todos los flags de autoridad y de atestación son `false`.

## Orden de fuentes, según el mapa A3 (8 necesidades)

1. Definición consolidada: `screen_contract.json` — `lf_ops.fn_screen_contract_v1`.
2. Reglas directas con decisión: `direct_rules.json` — `lf_ops.pantallas + lf_ops.reglas_pantallas + lf_ops.reglas`.
3. Directas y heredadas: `effective_rules.json` — `programacion.fn_input_effective_rule_links_v1`.
4. Políticas centrales y respaldo: `policies.json` — `lf_ops.pantallas_politicas + lf_ops.politicas_*`.
5. Elementos, estados, variantes y relaciones: `elements.json`, `states.json`, `variants.json`, `relations.json`.
6. Referencias de inventario e impacto: `inventory.json` — `inventory.*`. Pantalla nueva: **cero objetos**, no «impacto cero».
7. Contexto técnico / EKB / ADR: `ekb.json` y `adr.json`.
8. Decisión histórica ASOF: `decision_asof.json`.

`semantic_signals.json` es el artefacto explícito simulado del productor semántico externo de A1/A2. No implementa un intérprete de lenguaje natural.

## Escenarios y conservación de incertidumbre

El conjunto incluye seis reglas VIGENTE: credenciales requeridas, bloqueo cinco intentos durante quince minutos, BCrypt, error genérico, sesión de treinta minutos y exclusión de contraseñas de logs (heredada DERIVED_GLOBAL). Se incluyen otras dos reglas **no aplicables**: decisión pendiente y candidata con alerta. La política del bloqueo no está en `contract.policies` y debe resolverse solo en el respaldo de políticas. A4 conserva `IMPACT_UNKNOWN` al crear una pantalla nueva; A5 no obtiene permiso de ejecución.

Ejecutar con `python3 analysis/host/run_a1_a5_fixture.py --out /tmp/sbx-f1-out`. El runner guarda cada etapa en JSON. La única función de F1 es probar la proyección candidata A1–A5 de manera hermética: **no produce una entrada autorizada para PG-04**.
