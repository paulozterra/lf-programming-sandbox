# PG-03_C9/C10 — Evidencia exact-source, calificación local · 2026-11-03

**Plan:** ruta crítica técnica Fase 2. No confundir PASS local con estado oficial ni autorización productiva. Sin cambios en Supabase, main o código propietario.

## C9 — Revisión independiente, sujeto exacto

Repositorio propietario: `cristhianlujan/claude-persona-lf-patch` [PR #3523](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3523), HEAD `10cbf9f5ed4e0c5713cad603f302d4965831ee6f`.

Se reconstruyeron **byte a byte** los cuatro archivos originales en `/mnt/data/pg03_c9_audit` y se comparó `git hash-object` con las respuestas de GitHub:
- `pg03_strategy_v1.py`: `4bbebe3d4d7cd7b48645b3033366122b0c8183d1`;
- `pg03_assurance_envelope_v1.py`: `0c1e6e14892e3873d75b2eab24669a6fc2213f0f`;
- `pg03_c9_subject_binding_v1.py`: `4f479f3a45b981dd766dd5b5e8782472b0b0161e`;
- `test_pg03_c9_subject_binding_v1.py`: `45e4f86857d922b864157f2e570caf90463c8785`.

Comando real: `cd /mnt/data/pg03_c9_audit && python test_pg03_c9_subject_binding_v1.py`.

Salida conclusiva literal:
```text
PG03_C9_BINDING_NEGATIVE_PASS=strategy_tamper
PG03_C9_BINDING_NEGATIVE_PASS=fake_strategy_authority
PG03_C9_BINDING_NEGATIVE_PASS=wrong_subject_digest
PG03_C9_BINDING_NEGATIVE_PASS=wrong_stack_head
PG03_C9_BINDING_NEGATIVE_PASS=self_review
PG03_C9_BINDING_NEGATIVE_PASS=missing_receipt
PG03_C9_BINDING_NEGATIVE_PASS=upstream_missing
PG03_C9_BINDING_NEGATIVE_PASS=upstream_wrong_run
PG03_C9_BINDING_NEGATIVE_PASS=false_review_required
PG03_C9_BINDING_NEGATIVE_PASS=duplicate_dimensions
PASS_PG03_C9_EXACT_SUBJECT_BINDING positive=1 negative=10 existing_assurance_reused=true candidate_digest_bound=true ledger_readback_verified=false semantic_judge_executed=false authority=NONE runtime_verified=false
```

**Dictamen:** `PG03_C9_EXACT_SOURCE_LOCAL_PASS`; no `C9_RUNTIME_PASS`. El código usa preflight/assurance existentes, valida SHA del candidato y el sujeto, pero acepta upstream synthetic fixture, no tiene ledger readback VERIFIED ni revisor real. El [PR #3524](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3524) ya mapea la ruta real y evidencia bloqueo previo PG01_C6 sin recibos reales; no duplicar estos componentes.

## C10 — D15/D14 arquitectura

Repositorio propietario: [PR #3510](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3510), HEAD `3076a37d42716833294875425335f16b7a832a0e`.

Ambos archivos reconstruidos localmente en `/mnt/data/pg03_c10_audit` con identidad exacta Git:
- `pg03_architecture_d15_v1.py`: `cb5a9cd265ef197e158c5e63ca173498c0d337e1`;
- `test_pg03_architecture_d15_v1.py`: `ec632d8330f0f10c10c3572a9ec0046c3b3b8079`.

Comando real: `cd /mnt/data/pg03_c10_audit && python -m unittest -q test_pg03_architecture_d15_v1`.

Salida:
```text
Ran 12 tests in 0.001s
OK
```

La implementación comprueba unidades, módulos, recursos D14 explícitos, scopes declarados y deriva del perfil D15 hacia propuesta de ADR, con `production_authority=false`, `deployment_allowed=false`, `handoff_allowed=false`.

### Dos comprobaciones adicionales sobre C10 original (sin parche)

```text
C10_UNUSED_SCOPE_ACCEPTED CANDIDATE_CONFORMANT_NOT_ADMITTED
C10_UNBOUND_STRATEGY_ACCEPTED CANDIDATE_CONFORMANT_NOT_ADMITTED
```

El primer caso añadió scope `S2` a la estrategia sin pieza asociada. **La exigencia de cobertura exhaustiva de scopes para C10 debe contrastarse con su contrato canónico antes de clasificarlo como defecto**: el C8 ya cubre requisitos/aceptación para el traspaso a PG04.

El segundo caso suministró un sobre C3 sintético con `candidate_sha256='f'*64` y `capability_selector='FORGED'`: C10 lo aceptó sin recalcular el digest. Es una **brecha de integridad del input interno**, no autenticación de D15 ni bypass de despliegue. Debe revisarse si el C10 propietario necesita una guarda mínima para estrategia C3, o si una capa obligatoria previa ya garantiza este vínculo. **No crear otro validador ni parche sin revisar propietario de esa verificación**.

**Dictamen:** `PG03_C10_ORIGINAL_12_LOCAL_PASS / STRATEGY_DIGEST_BINDING_GAP_OBSERVED / D15_SOURCE_UNAUTHENTICATED`.

## Estado técnico y continuación

- **PG-03_C1–C10:** todas las implementaciones candidatas identificadas; C8, C9, C10 tienen suites ejecutadas localmente; C4–C8 tienen parches source-only preparados en sandbox, **no integrados upstream**.
- **No declarar PG-03 cerrado:** siguen pendientes integración real C1→C2→C3, aplicación gobernada de correcciones, recibos auténticos PG01/PG02, C3 CURRENT, readback ledger y assurance independiente.
- CI sandbox [run #41699496913](https://github.com/paulozterra/lf-programming-sandbox/actions/runs/41699496913), commit `8d396ee726274f57cd919ee3029a9e53a754baeb`: 5 jobs SUCCESS. Ese CI no ejecuta C9/C10 cross-repo.
- **Siguiente ruta crítica:** confirmar brecha C10 con contrato D15 exacto y preparar mínima corrección si corresponde; luego avanzar PG-04 técnico por reutilización. No reabrir PG-00 ni análisis.

Este informe distingue evidencias ejecutadas, observaciones de auditoría y requisitos de autoridad.
