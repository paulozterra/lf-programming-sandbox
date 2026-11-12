# F1 — Pantalla sintética SBX-AUTH-LOGIN (solo sandbox)

**D-AN4 / D-AN5, opción A aprobada por Paulo el 11/11/2026.**

El identificador de negocio **LF** es un parámetro técnico obligatorio en los
productores canónicos A1–A5; **no representa un negocio LF real** en estas
fixtures. El target, las reglas, políticas y códigos de pantalla son ficticios,
con prefijo SBX-. No se accede a Supabase ni a GitHub desde el host.

## Frontera doble de referencias

- En campos que los productores validan literalmente, `supabase://lf_ops...`
  designa solo una **identidad sintética compatible** con el contrato A3; no es
  una lectura real ni referencia de autoridad.
- Cada archivo de origen queda registrado como
  `fixture://sbx_auth_login/<archivo>@<sha256>` en
  `fixture_provenance`, calculado sobre los bytes del archivo; los hashes
  esperados están fijados en `SOURCE_PIN.json`.
- Cualquier ausencia, incoherencia del archivo o digest alterado bloquea
  con `SBX_* `. Los flags `source_attested`, `currentness_attested`,
  `production_authority`, `a6_allowed` permanecen `false`.
- Los campos `LF` y `supabase://` no pueden reutilizarse como credenciales,
  autoridad, recibos de lectura real ni insumos operativos fuera de F1.

## Lecturas simuladas

| Archivo | Fuente cuya forma reproduce |
|---|---|
| screen_contract.json | lf_ops.fn_screen_contract_v1 |
| direct_rules.json | lf_ops.pantallas + reglas_pantallas + reglas |
| effective_rules.json | programacion.fn_input_effective_rule_links_v1 |
| policies.json | lf_ops.pantallas_politicas + politicas_* (respaldo tipado) |
| elements.json | lf_ops.pantalla_elementos |
| states.json | lf_ops.pantallas_estados |
| variants.json | lf_ops.pantalla_variantes |
| relations.json | lf_ops.relaciones_b2b |
| inventory.json | inventory.objects + grafos de impacto/dependencias |
| ekb.json | EKB exacto |
| adr.json | ADR existentes |
| decision_asof.json | public.fn_lf_decision_context_asof_resolve_v1 |
| semantic_signals.json | Productor semántico externo A1 y señales A2, sin ejecutar modelo |

## Alcance y limitación A1

El pedido está escrito en lenguaje natural, pero el productor A1 sin
revisor semántico **no permite transformar automáticamente texto crudo en una
clasificación aprobada**. Por ello `semantic_signals.json` contiene explícita
la estructuración ficticia y las señales tipadas. El host solo las reproduce
si el pedido coincide *exactamente* con el declarado: no intenta interpretar,
generar heurísticamente ni fingir revisión independiente. Se usa el modo
`PRESTRUCTURED_UNATTESTED` del A1 existente.

Las seis reglas vigentes incluyen campos de credenciales, bloqueo,
hash BCrypt, no registrar contraseñas, respuesta genérica y expiración.
`SBX-R-PENDING` se excluye por decisión pendiente, y `SBX-R-CAND`
por estado candidato. `SBX-R-LOG` proviene de `DERIVED_GLOBAL`.
`SBX-R-ERR` resuelve su vínculo a la política 71 desde respaldo,
sin reclamar autoridad. Inventario vacío implica cambio CREATE
planificado con impactos externos desconocidos, nunca ausencia de impacto.

## Ejecución aislada

```bash
python3 analysis/host/run_a1_a5_fixture.py --output-dir /tmp/sbx-f1
python3 -m pytest -q analysis/host
```

El runner guarda `a1.json`…`a5.json` y `source_provenance.json`.
F1 no produce el paquete final A9, no llama a CP3.2 y no autoriza PG-04.
