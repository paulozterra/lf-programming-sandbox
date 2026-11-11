# F1 — Pantalla simulada SBX-AUTH-LOGIN

**Estado:** ensayo local de A1–A5. No se ejecutan RPC, SQL, red, producción, ni se habilita A6/PG-04. El caso es enteramente inventado.

## Identidad, negocio y procedencia (D-AN4 / D-AN5)

Los productores fijados A1–A5 aceptan **`business="LF"`** y algunos comparan literalmente rutas `supabase://`. El host conserva esos valores solo como **identidad de compatibilidad del contrato**, nunca como evidencia de una lectura real.

- Identidad de pantalla ficticia: `SBX-AUTH-LOGIN`; todos los códigos de reglas, elementos, variantes y estados tienen prefijo `SBX-`.
- Fuentes reales: exclusivamente archivos del directorio `analysis/fixtures/sbx_auth_login/`. Cada lectura está inventariada en `source_provenance` como `fixture://sbx_auth_login/<archivo>@<sha256>`, verificada contra `analysis/fixture_sha256_pins.json`.
- Cada fixture: `simulated=true`, `source_attested=false`, `authority_verified=false`. El host **no** otorga ni simula `CURRENT`, aprobación del owner, autoridad de producción, PG-01, ni lectura real de Supabase.
- `semantic_signals.json` es una entrada tipada simulada para A2; A1 recibe una representación estructurada del pedido y **no** se implementa un clasificador de lenguaje natural.

## Mapa de fuente canónica a archivo inventado

| Paso de mapa A3 | Fuente que se imita | Fixture |
|---|---|---|
| 1 | `lf_ops.fn_screen_contract_v1` | `screen_contract.json` |
| 2 | `lf_ops.pantallas + reglas_pantallas + reglas` | `direct_rules.json` |
| 3 | `programacion.fn_input_effective_rule_links_v1` | `effective_rules.json` |
| 4 | `contract.policies`, `pantallas_politicas`, `politicas_*` | `screen_contract.json`, `policies.json` |
| 5 | Elementos, estados, variantes y relaciones | `elements.json`, `states.json`, `variants.json`, `relations.json` |
| 6 | `inventory.*` | `inventory.json` |
| 7 | AS-IS GitHub autorizado | **No simulado como autoridad**; inventario vacío y ausencia de atestación dejan impacto desconocido |
| 8 | EKB, decisiones y ADR | `ekb.json`, `adr.json`, `decision_asof.json` |

Seis reglas vigentes candidatas: credenciales obligatorias, bloqueo 5 intentos/15 minutos, BCrypt, mensaje genérico, expiración 30 minutos y exclusión de contraseña de logs (esta última `DERIVED_GLOBAL`). Una regla pendiente y otra candidata con alertas se excluyen.

La política `SBX-POLICY-LOCKOUT` está ausente del arreglo `contract.policies` y solo aparece en el respaldo `policies.json`, con vínculo ficticio explícito. Las referencias `supabase://` internas que espera A3 son cadenas sintéticas para pasar la validación de forma. Su origen verdadero nunca cambia de `fixture://`.

## Ejecución

```bash
python3 analysis/host/run_a1_a5_fixture.py --out analysis/out/sbx_auth_login
python3 -m pytest -q analysis/host
```

El runner guarda `a1.json` a `a5.json` y `run.json`. Los artefactos quedan en el directorio local indicado, no se publican como cambios de código ni se graban en LF.

El F0 conserva sus 20 `xfail(strict=True)` heredados. La clase CHG-0055 es `EDITORIAL` según el alcance de `standards/tools/changes.py`: solo se cambian rutas de Analysis y su workflow de pruebas, no el estándar normativo ni la implementación de los productores.
