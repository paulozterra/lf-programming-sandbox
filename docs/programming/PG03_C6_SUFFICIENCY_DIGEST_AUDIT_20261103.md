# PG-03_C6 — Auditoría de suficiencia e integridad de estrategia · 2026-11-03

**Plan aplicado:** ruta crítica técnica en GitHub; NO usar checkpoints oficiales Supabase como progreso técnico. **Ámbito:** PG-03_C6 exclusivamente; ninguna modificación al repositorio propietario.

## Reutilización y fuentes fijadas

- Implementación existente: `cristhianlujan/claude-persona-lf-patch` [PR #3507](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3507), HEAD `c517136c9d5d4330ce51fad6a7a3de8c0d821775`, DRAFT.
- `pg03_sufficiency_v1.py` SHA Git blob original `50193d0efe304d285ec0973d65f3e1234770e016`.
- `test_pg03_sufficiency_v1.py` SHA Git blob original `233569b9c222cbd968caa218645c23ec35f6cefa`.
- Ambos blobs se reconstruyeron byte a byte localmente; `git hash-object` coincidió con GitHub **antes de aplicar cambios**.
- PG-01_C7 [PR #3516](https://github.com/cristhianlujan/claude-persona-lf-patch/pull/3516) verifica suficiencia material **antes** de estrategia y no sustituye este C6. No alterar PG-01/Análisis.

## Defecto probado en C6 original

`assess_sufficiency` valida el estatus y ciertos IDs de `strategy`, pero conserva `candidate_sha256` mediante `strategy.get(...)` **sin verificar integridad interna**.

Prueba con salida sintética del estrategizador C3 local existente, evidencia de requisitos, aceptación y pregunta resuelta: se modificó `capability_selector` a `UNAUTHORIZED_BUILD_ALL`, dejando intacto `candidate_sha256`. Respuesta original:

```text
BASE CANDIDATE_SUFFICIENT_NOT_ADMITTED
TAMPER_ACCEPTED CANDIDATE_SUFFICIENT_NOT_ADMITTED True
```

Esto no autentica entrada real de Análisis ni significa explotación productiva: el resultado C6 sigue sin autoridad. Sí demuestra que un contenido de estrategia alterado puede parecer suficiente para este validador.

## Corrección preparada sin duplicar motor

`docs/programming/patches/PG03_C6_STRATEGY_DIGEST_GUARD_20261103.patch` modifica **únicamente** el C6 original y su test original:

1. Calcula SHA256 sobre `json.dumps` ordenado con separadores `(',', ':')` sobre la estrategia sin `candidate_sha256`, igual al escritor C3.
2. Exige igualdad con el digest declarado; si falta/no coincide, bloquea con `STRATEGY_DIGEST_MISMATCH`.
3. Actualiza fixture sintético original del test para tener digest válido (antes contenía literal `'test'`).
4. Agrega 2 regresiones: estrategia alterada con digest antiguo y ausencia de digest.

**El parche permanece solo en sandbox; no instalado en fuente propietaria ni en main.** La comprobación estructural con el contenido Git original dio `PATCH_STRUCTURAL_PASS` en ambos archivos y todos los hunks.

## Pruebas locales realmente ejecutadas

Directorio de prueba: `/mnt/data/pg03_c6_audit`.

```sh
python3 -m unittest test_pg03_sufficiency_v1 -q
# Original exact-source: Ran 11 tests ... OK

# Aplicar solo en copia local la guarda y el fixture/test nuevo
python3 -m unittest test_pg03_sufficiency_v1 -q
# Patched local source: Ran 13 tests ... OK
```

Validaciones adicionales con salida de C3 local:
```text
PATCHED_POSITIVE_PASS
PATCHED_TAMPER_REJECTED STRATEGY_DIGEST_MISMATCH
PATCHED_NEGATIVE_PASS candidate_sha256
PATCHED_NEGATIVE_PASS active_domains
PATCHED_NEGATIVE_PASS acceptance_ids
PG03_C6_C3_DIGEST_GUARD_LOCAL_PASS positive=1 negatives=4 authority=false
```

SHA-256 de copias locales **corregidas**: `pg03_sufficiency_v1.py=8a14138d4f13f01c24a559292f5eccb34af5f28e6f020b49068307b4f477d421`, `test_pg03_sufficiency_v1.py=75820478b680a7168bb7bd3e1b087c77e71ef7b4f5facfd0f808152040c6f8ff`.

## Dictamen y siguiente trabajo

`PG03_C6_ORIGINAL_SUITE_PASS / C6_STRATEGY_DIGEST_PATCH_LOCAL_PASS / CROSS_REPO_RUNTIME_NOT_EXECUTED`.

- No se ejecutó el juicio semántico, A9 real, recibo de análisis ni writer productivo. Hash interno no equivale a procedencia autentificada.
- C6 **no** autoriza despacho ni handoff: `production_authority=false`, `handoff_allowed=false`.
- Integración del parche en su propietario requiere la ruta de revisión independiente acordada.
- Seguir PG-03_C7 tras inventario de código y PR existentes; mantener separado el cierre técnico local del estado oficial.

Sin merge, sin Supabase writes, sin cambios en repositorio de Cristhian.
