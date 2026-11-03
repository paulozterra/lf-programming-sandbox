# PG-03_C1→C3 — ejecución local con fuente original verificada (2026-11-03)

**Estado:** `C1_C3_SYNTHETIC_LOCAL_PASS / C2_NOT_EXECUTED / FULL_CHAIN_NOT_ATTESTED`.

## Fuentes y huellas

- C1: `cristhianlujan/claude-persona-lf-patch` PR #3497 HEAD `e51b2a20a00e46fa30ef78f7d53fc37687505002`, archivo `pg03_stack_source_v1.py`; el archivo local reconstruido desde su contenido consultado en GitHub tiene **git blob SHA** `bb50afcb20e0522eb8996ac08ce1b89c3c0883fb`, igual al declarado por la API del repositorio.
- C3: original de PR #3498 HEAD `1a3dfe22a8ceaed4306a719e9391694d122342a2`, con el parche de validación de scopes aplicado **solo en copia local** (guard no upstream).
- La prueba no usó el selector C2 ni el binding #3519: no se extrapola un PASS de C1→C3 a C1→C2→C3.

## Prueba efectivamente ejecutada

Se generó un Git temporal con `pom.xml` sintético, commit real de Git y `git show COMMIT:pom.xml`. La función original `resolve_stack()` leyó el objeto Git a SHA fija, emitió el digest SHA-256 del archivo y la evidencia `status=CANDIDATE_NOT_ADMITTED / authority=false`. Se entregó **esta evidencia real de C1**, no un diccionario fabricado, a `prepare_strategy()` original con guard de scopes aplicado localmente.

Salida literal de `python3 /mnt/data/pg03_cross_probe/run_c1_c3.py`:

```text
PASS_C1_REAL_GIT_OBJECT_SOURCE=1 sha256_verified=true authority=false
PASS_C1_TO_C3_SYNTHETIC=1 deterministic=true source_bound=true authority=false
PASS_C1_C3_NEGATIVE=duplicate_scope
PASS_C1_C3_NEGATIVE=invalid_scope
PASS_C1_C3_NEGATIVE=missing_stack
PASS_C1_C3_NEGATIVE=not_ready
C2_EXECUTED=false FULL_C1_C2_C3_CHAIN_EXECUTED=false
```

Script fuente local: `/mnt/data/pg03_cross_probe/run_c1_c3.py`, SHA-256 `a9d522d17ee6764d8c829019ac042b3e72446a3426a60b861fbfab9478f33669`. Archivo C1 reconstruido local: SHA-256 `69e9b4d29b11b4d18e589cea9ec7f54143e1bccc341cd77cb5fd846119f52f46`. Ambos `py_compile` correctos.

La ejecución desde contenedor de `git ls-remote https://github.com/paulozterra/lf-programming-sandbox.git HEAD` falló con `Could not resolve host: github.com`. Los archivos C2, catálogo completo y Skill originals no están en un checkout local. Su código sí está disponible a través del conector GitHub, pero eso no equivale a un checkout ni acredita su ejecución.

## Siguiente trabajo crítico, sin crear otros motores

Ejecutar el arnés existente `standards/tools/pg03_cross_repo_chain_probe_v1.py` en un entorno con los dos checkouts. **Aunque ese ensayo pase**, C3 todavía no recibe ni exige un recibo C2. Una admisión técnica de la vinculación obligatoria requiere comprobar misma ejecución, SHA de commit, dominios y selección, reutilizando el binding #3519; un `test_only_preconditions` no constituye gate del runtime. No editar el repositorio de Cristhian, Supabase o main para el ensayo.
