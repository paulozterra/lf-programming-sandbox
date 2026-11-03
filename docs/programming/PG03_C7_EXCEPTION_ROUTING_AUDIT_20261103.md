# PG-03_C7 — Auditoría técnica de excepciones y autoridad · 2026-11-03

**Ámbito:** ruta crítica técnica PG-03_C7 (no ledger Supabase). Sin cambios a Cristhian, `main`, Router, ni Análisis.

## Evidencia reutilizada

- Propietario: `cristhianlujan/claude-persona-lf-patch`, [PR #3508](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3508), DRAFT, HEAD `057330ddd3ddb6d0aeeb4fee25d0bc203adfc856`.
- Función `classify_exceptions()`: original `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_exception_routing_v1.py`, **Git blob** `253c77e2a8ba1ed09d0c787643d958b2602bd8e0`.
- Test original `test_pg03_exception_routing_v1.py`, **Git blob** `b77a4f55a639fe107b22fbc685ea0ee3850e39fe`.
- Ambos archivos reconstruidos localmente desde contenido de GitHub y comparados con `git hash-object`; **coinciden los dos blobs**.
- Se respeta el circuito de decisión existente de PG-10 (#1912). Ningún nuevo motor de aprobaciones/waivers.

## Comportamiento existente correcto

Las rutas de C7 siguen segregadas: `EVIDENCE_GAP → TARGETED_ANALYSIS_EVIDENCE`, `OWNER_DECISION → CHECK_EXISTING_CURRENT_DECISION_FIRST`, `TECHNICAL_STRATEGY → PG03_TECHNICAL_RESOLUTION`, `POLICY_DEVIATION → EXISTING_POLICY_AUTHORITY_REVIEW`. Ni el positivo ni las rutas de excepción permiten handoff o conceden waiver.

## Brechas reproducidas sobre C7 original

1. **Sin integridad de estrategia:** se aceptaba `strategy` candidata sin `candidate_sha256` (`status=CANDIDATE_NOT_ADMITTED` con `exceptions=[]`). Sin comprobación del sobre original C3, una mutación mantendría la clasificación.
2. **Flags de aprobación no tipados:** el veto original solo revisa `item.get('approved') is True` o `waiver_granted is True`; así el campo `approved='true'` cruza el clasificador, aunque la salida de la excepción continúe `status=BLOCKED`, `waiver_authorized=false` y `handoff_allowed=false`. **Esto no prueba bypass operacional**; sí es una ambigüedad de entrada que conviene rechazar.

## Parche incremental

Archivo en sandbox: `docs/programming/patches/PG03_C7_EXCEPTION_DIGEST_APPROVAL_GUARD_20261103.patch`.

- Recalcula `candidate_sha256` del sobre de estrategia según `json.dumps(sort_keys=True,separators=(',', ':'))` empleado por C3; rechaza ausencia, inconsistencia o alteración con `STRATEGY_DIGEST_MISMATCH`.
- Rechaza flags `approved` / `waiver_granted` con cualquier valor distinto de `None` o `False`; el clasificador no admite autorizaciones suministradas por caller.
- Modifica el fixture de test para tener digest válido y añade 3 métodos de regresión (tamper, digest ausente, flags no booleanos).
- Los dos hunks por archivo se contrastaron con los archivos originales del HEAD fijado: **`PATCH_STRUCTURAL_PASS`**. Parche **NO aplicado** al repositorio propietario.

## Ejecución local reproducible

Directorio local de prueba `/mnt/data/pg03_c7_audit`.

```text
# Original exact-source:
Ran 11 tests in 0.000s
OK

# Copia local corregida:
Ran 14 tests in 0.001s
OK

ORIGINAL_UNVERIFIED_APPROVAL_ACCEPTED= BLOCKED
ORIGINAL_MISSING_STRATEGY_DIGEST_ACCEPTED= CANDIDATE_NOT_ADMITTED
```

Los resultados muestran que un flag afirmativo textual se permitía **en la entrada**, pero **no otorgaba waiver**. La nueva suite comprueba la denegación como excepción, sin cambiar el resultado seguro que existía.

SHA-256 de archivos corregidos locales: `pg03_exception_routing_v1.py=84f78f456c9a145fa730b458db59c2bbe0ef1458ff458afcd120a6926baa228f`; `test_pg03_exception_routing_v1.py` después de igualar la última línea exacta del test original: verificar su SHA local si se requiere replay.

## Dictamen y próximo paso

`PG03_C7_BASELINE_11_PASS / C7_GUARD_LOCAL_14_PASS / PATCH_PREPARED / RUNTIME_AUTHORITY_NOT_ATTESTED`.

Limitaciones: SHA del propio productor no autentica fuente, A9 ni decisiones reales; la comprobación evita alteraciones silenciosas **solo entre C3 y C7**. Sin CI propietario ni aprobación de aplicación. Siguiente checkpoint independiente: **PG-03_C8**, previamente inventariado como posible `strategy_ref` que no vincula digest; verificar la implementación actual **antes de crear otro parche**.

Sin merge, sin escritura Supabase, sin edición de repositorio de Cristhian.
