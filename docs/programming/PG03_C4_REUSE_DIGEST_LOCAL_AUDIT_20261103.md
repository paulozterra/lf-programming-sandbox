# PG-03_C4 — Auditoría incremental y corrección preparada (03/11/2026)

**Ruta crítica técnica, no estados oficiales de Supabase.** Se reutiliza C4 original, sin crear otro motor/gate.

## Fuente exacta

- Implementación original: `cristhianlujan/claude-persona-lf-patch` PR #3499 (DRAFT), HEAD `aff87f136252bac6f2f7572fc6789f44d8574949`.
- `pg03_reuse_binding_v1.py` Git blob: `417ee610d6a73b0724a5355f19c5501b37ec7093`; el archivo reconstruido para la prueba local produjo el **mismo** `git hash-object`.
- Test original `test_pg03_reuse_binding_v1.py` Git blob: `b7785b5045f07ba112b8ce7e9efa49993613b7ba`; coincidencia local exacta.
- C3 base: #3498; para este ensayo se usó la copia local de C3 con el parche de scope IDs aún **no integrado upstream**.

## Defecto reproducido

`validate_reuse()` conservaba `strategy.get("candidate_sha256")` como identificador **sin recalcular el digest** del sobre de estrategia. Se cambió `requirement_ids` de la estrategia, conservando `reuse_refs` y `candidate_sha256` originales. Antes del parche:

```
PG03_C4_EXISTING_POSITIVE_PASS authority=false deterministic=true
PG03_C4_TAMPER_ACCEPTED=true strategy_sha256_unchanged=True
```

Esto demostraba que el C4 source-only validaba paridad de reutilización pero no integridad del sobre de C3.

## Cambio mínimo propuesto

`docs/programming/patches/PG03_C4_STRATEGY_DIGEST_GUARD_20261103.patch`: recalcular SHA256 sobre la serialización JSON canónica que ya usa `prepare_strategy` (sin `candidate_sha256`) y exigir igualdad. Si no coincide: `StrategyBlocked("STRATEGY_DIGEST_MISMATCH")`.

**No se cambió el repositorio propietario**. El parche permanece como propuesta en sandbox.

## Ejecución local real

Con original C4 exacto, luego guarda aplicada únicamente a la copia local:

```
$ cd /mnt/data/pg03_cross_probe
$ python3 test_pg03_reuse_binding_v1.py
PG03_C3_STRATEGY_CANDIDATE_PASS positive=1 deterministic=1 negatives=11 authority=0
PG03_C4_REUSE_PARITY_PASS positive=1 deterministic=1 negatives=6 authority=0

$ python3 check_c4.py
PG03_C4_EXISTING_POSITIVE_PASS authority=false deterministic=true
PG03_C4_TAMPER_REJECTED=STRATEGY_DIGEST_MISMATCH
```

La suite base mantiene seis negativos y la prueba adversarial adicional rechaza alteración. SHA256 de C4 corregido local: `acefb803bb0cb5e000f60f896aea04c3fdf03edf8a1d6eab5aeb8e20b038f58f`.

## Límites y siguiente paso

- **Estado técnico:** `PG03_C4_REUSE_PARITY_LOCAL_PASS / C4_STRATEGY_DIGEST_GUARD_PATCH_PREPARED`. No es CI exact-HEAD de upstream ni atestación de origen A9.
- El SHA recalculado comprueba integridad interna, **no autentica que el productor o A9 sea real**.
- Integración del parche debe seguir una ruta acordada con propietario del código; no se copia ni reimplementa `validate_reuse` en sandbox.
- Siguiente checkpoint técnico después de documentar esta brecha: evaluar PG-03_C5 original contra fuente/catalogo y jueces existentes, evitando crear un evaluador paralelo.

Sin merge, sin Supabase write, sin cambio en `main`, sin modificación de repositorio de Cristhian.
