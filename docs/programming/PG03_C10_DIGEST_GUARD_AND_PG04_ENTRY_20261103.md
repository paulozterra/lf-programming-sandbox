# PG-03_C10 — estrategia ↔ D15/D14, regresión local 2026-11-03

**Alcance:** ruta crítica técnica, no ledger Supabase. Ningún cambio al repo propietario, a main ni a producción.

## Fuente original verificada

Repositorio `cristhianlujan/claude-persona-lf-patch`, PR #3510 DRAFT, HEAD `3076a37d42716833294875425335f16b7a832a0e`.
- `pg03_architecture_d15_v1.py` Git blob `cb5a9cd265ef197e158c5e63ca173498c0d337e1`.
- `test_pg03_architecture_d15_v1.py` Git blob `ec632d8330f0f10c10c3572a9ec0046c3b3b8079`.
- `git hash-object` de ambos archivos reconstruidos localmente coincidió exactamente con estos blobs.

```text
$ cd /mnt/data/pg03_c10_audit
$ python -m unittest -q test_pg03_architecture_d15_v1.py
Ran 12 tests in 0.001s
OK
```

## Brecha, sin duplicación

`assess_architecture` recibe `strategy` C3, y comprueba status/flags pero no recalcula `candidate_sha256`; una alteración de la estrategia no invalida la evaluación candidata. Esta brecha es **integridad interna de candidato**, no autenticación D15 ni despliegue productivo. No se halló otro PR específico que ya la corrija.

Se preparó `docs/programming/patches/PG03_C10_STRATEGY_DIGEST_GUARD_20261103.patch`, generado como diff desde los archivos originales y probado en copia local. Reutiliza `hashlib/json`, comprueba digest SHA-256 canónico de estrategia C3 (sin el propio campo digest); en drift devuelve `STRATEGY_DIGEST_MISMATCH`. Amplía el test original con tres casos: tamper, digest ausente y digest equivocado. Actualiza fixture para que use digest verdadero, no sintético inválido.

```text
$ cd /mnt/data/pg03_c10_audit/patched
$ python -m unittest -q test_pg03_architecture_d15_v1.py
Ran 15 tests in 0.001s
OK
```

SHA256 de copias locales corregidas:
- `pg03_architecture_d15_v1.py`: `1cbe9856b8c0d1c4b55e94ae25d3266ff3baddbb386895fa33d09d6e4b18815d`.
- `test_pg03_architecture_d15_v1.py`: `a86cbd3794aec09c166135e115bcb4abaf00b62a3ef4d73f18bac6b7a9193a26`.

El parche **no se aplicó a la rama de Cristhian**, y el CI upstream no puede darse por aprobado con esta prueba local. Cobertura exhaustiva de scopes no está establecida por este ensayo; no inventar requisito adicional sin leer la definición C10.

## PG-04 — reutilización antes de implementar

- PR #3387 DRAFT, HEAD `c410dd06fc7f1c9fc735b6b63868806f28dcd6b9`, contiene `pg04_materialization_order_candidate/materialization_circuit.py` y `test_materialization_circuit.py` (6 tests declarados en PR; verificar por ejecución propia).
- PR #1912 contiene el contrato canónico de partición por solución `PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1`; PG-03_C8 ya valida las asignaciones requerimientos/aceptaciones y DAG en modo candidato. **No crear otro particionador ni otro circuito de materialización.**
- Contratos de PG-01 auténtico, generador ciego, pruebas selladas y readiness se mantienen como dependencias de admisión operativa. Probar PG-04 offline sin esperar C3 productivo.

**Dictamen:** `PG03_C10_ORIGINAL_12_PASS / PATCH_LOCAL_15_PASS / UPSTREAM_PATCH_NOT_APPLIED / RUNTIME_NOT_ADMITTED`. Siguiente tarea: ejecutar 6 tests existentes del circuito PG04 y revisar su contrato.
