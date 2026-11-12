# F2: D-AN6(a) — admisión simulada A5→A6

**Candidato offline, exclusivamente sandbox.** Nunca cambia A1–A5 ni
certifica autoridad, CURRENT, un juez independiente o una aprobación de Paulo.

## Frontera y modo

`analysis/host/simulated_admission_gate.py` recibe las **salidas reales**
del runner F1, señales tipadas de A2 y un sobre con SHA-256 canónico de A1…A5.
El digest solo vincula los bytes: **no equivale a una firma autenticada**.
El modo `SIMULATED_SANDBOX_ONLY` y todos los flags falsos acompañan
el recibo de admisión y la salida A6. Nunca habilita A6 en producción.
Una vez exista A9, deberá conservar explícitamente este marcador y someter
su paquete completo al **validador y schema existente** del perfil.

La lista cerrada de levantamiento:
- `SOURCE_READBACK_CURRENTNESS_AND_AUTHORITY_NOT_ATTESTED` (A3).
- `A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED` (A4 reflejado en A5).
- `A2_TYPED_EVIDENCE_CURRENTNESS_OR_SPECIALIST_PENDING`: solo cuando
  el resto de señales tipadas tienen materialidad conocida LOW/MEDIUM/HIGH,
  alcance TRUE y reversibilidad conocida DEMONSTRATED/NOT_DEMONSTRATED, sin especialista, sin contradicción,
  sin impacto cruzado ni conteos pendientes.
- `GITHUB_CURRENT_IMPLEMENTATION_AND_AS_IS_MISSING`: únicamente
  `CREATE` con inventario vacío y destino de código inexistente.

**No se levantan** otras brechas o ninguna regla VIGENTE pendiente /
CANDIDATO. Cualquier código o estado fuera de los permitidos bloquea.
A5 original conserva `a6_allowed=false`. La puerta simulada es un
artefacto nuevo que **no** modifica ese resultado canónico.

## Caso positivo sintético explícito

La fixture `semantic_signals.json` de F1 estaba en materialidad UNKNOWN
y reversibilidad UNKNOWN: D-AN6(a) correctamente bloquea ese estado.
Para el ensayo positivo se cambian únicamente estos **dos campos ficticios**
a `HIGH` y `NOT_DEMONSTRATED`, y se actualiza su pin SHA-256. Los campos
`authority_state=UNKNOWN`, `currentness_decision=UNKNOWN_FAIL_CLOSED`
y `source_attested=false` permanecen como evidencia no atestada.
No se infiere LOW / DEMONSTRATED para ningún pedido real.

## A6 — obligatoria, no estrategia

`analysis/a6/implementability.py` lee el contrato F0 en
`sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_implementability_contract_v1.json`
(blob Git `d000e6900300e12bcc1e1e56490ca3acf40713d1`).
Respeta la estructura `IMPLEMENTABILITY_SCHEMA_V1`: requisitos con
`scope_refs`, `evidence_refs`, `acceptance_signals`, `blockers` y
arrays explícitos. Las seis obligaciones corresponden a los seis códigos
VIGENTE de A3, comprobados contra los perfiles de A5.

Los valores de área `BACKEND`/`FRONTEND` solo pueden venir de
`rule_layer_bindings` ya verificadas por A5; sin tal vínculo cada
obligación queda `UNKNOWN`. No se infiere DATA ni arquitectura.

El perfil copiado de F0 ya incluye
`schemas/runtime_output.schema.json` y
`validators/runtime_validate.py`. A6 **reutiliza y verifica la
disponibilidad** de esos mismos archivos; no crea un segundo validador.
Estos validan paquetes completos A9, no requisitos aislados A6. Su
ejecución sobre el paquete final se marca `DEFERRED_UNTIL_A9`,
sin falsificar un PASS anticipado.

## Ejecución

```bash
python3 -m pytest -q analysis/host analysis/a6
python3 -m analysis.host.run_a1_a6_fixture --output-dir /tmp/sbx-f2
```

La corrida conserva los cinco JSON originales y genera
`admission_envelope.json`, `admission.json`, `a6.json`
con huellas ligadas. No usa red, Supabase ni exámenes ocultos.

## Revisión Claude: seguridad HIGH

Login con bloqueo, BCrypt y política de logs es HIGH, sin inferir reversibilidad demostrada.
A2 acepta NOT_DEMONSTRATED en `analysis/programming_analysis/steps/a2/schemas/input.schema.json` líneas 92–96; `analysis/programming_analysis/steps/a2/validators/run.py` línea 243 considera sin resolver solo `UNKNOWN`. La puerta acepta LOW/MEDIUM/HIGH conocidos, y reversibilidad DEMONSTRATED/NOT_DEMONSTRATED; no rebaja riesgo.
La admisión y A6 propagan `materiality_level=HIGH`; cada obligación exige `requires_independent_exam=true`. SBX-R-ERR conserva una obligación con dos acceptance_signals independientes (error genérico; expiración).
