# F4 · A9 simulated Analysis implementation package

Este productor prepara un **candidato offline** para
`pilot.orchestrator.intake.validate(package, request_raw)` y
`intake.accept(root, slug)` SIN modificar ningún productor de Programación.

## Límites de autoridad

`analysis_mode=SIMULATED_ANALYSIS`,
`simulation_mode=SIMULATED_SANDBOX_ONLY`,
`candidate_only=true`; todos los seis flags de autoridad permanecen
`false`. El resultado `INTAKE_ACCEPTED` significa **admisión simulada CP3.2**:
el PG-01 pinned preflight sigue `FIXTURE_UNATTESTED` / `verified=false`.
No se declara el contrato LF de ASOF persistido o handoff paritario
productivo completado.

## Proveniencia y huellas

- El pedido se calcula exclusivamente con `intake.normalized_request_bytes`
  y SHA256; CRLF se normaliza exactamente como el intake.
- A1..A8 usan `digest` de las salidas reales. El elemento A9 del
  `stage_trace` usa el digest del **recibo de construcción A9**
  (`A9_SIMULATED_PACKAGE_RECEIPT_V1`) para evitar una huella autorreferencial
  imposible del paquete que contiene el propio `stage_trace`.
- `snapshot_schema_digest_sha256` = digest JSON canónico de
  `programming_entry_contract_v1.json#programming_context_snapshot`.
- `authority_fingerprint_sha256` = digest de los vínculos de autoridad
  declarados, estado UNKNOWN, actualizaciones CURRENT vacías y
  `source_attested=false`.
- `source_snapshot_sha256` = digest de las salidas A3..A8 y sus
  `source_refs`/`currentness_refs`; se guarda la entrada exacta del
  digest para revalidarla.
- `programming_context_snapshot` retiene los materiales completos
  A5, A6, A7 y A8, reglas aprobadas A3, invariantes vacíos **sin fuente**,
  autoridad y currentness vacíos **sin atestación**, matriz
  frente-scope, readiness por scope y los campos requeridos del contrato
  `analysis_programming_handoff_parity_contract_v1.json`.

A9 **no inventa** capacidades ni decisiones. El requisito de generar
persistencia ASOF, resolver recepción y emitir recibo
`PROGRAMMING_CONTEXT_HANDOFF_RECEIPT_V1` no puede ser satisfecho por el
`intake.py` offline existente; se mantiene pendiente y nunca se marca
como cumplido.

## Intake compatible

Se producen `REQ-<codigo>` para cada obligación de A6. La cadena
`acceptance_signal` concatena todos los criterios con ` | `;
`acceptance_checks[]` conserva la lista desagregada sin pérdidas.
Cada frente A7 porta su `front_kind`, `scope_ids`, status, closure,
blockers y hint SANDBOX_HINT. Un solo scope Login incluye exactamente
todos sus frentes. `READY_CANDIDATE` se usa solo con A8 STOP y cero
frentes BLOCKED, aunque ello **no** equivale a PG-01 READY.

`material_unknowns` conserva el bloqueo residual de autoridad,
`decisions_pending` solo los owner decisions materialmente abiertos.
Los dos excludes de A3 nunca generan requisitos.

## Ejecución

```bash
python3 -m pytest -q analysis/host analysis/a9
python3 -m analysis.host.run_a1_a9_fixture --root /tmp/sbx-f4
python3 -m pilot.orchestrator.intake --root /tmp/sbx-f4 --request-id f4-login
```

Emite `pilot/runs/f4-login/request.md`, `analysis.json` y
`state.json` en el root suministrado. Es reproducible byte a byte y no
lee Supabase ni escribe ningún archivo de Programación en el repo.
