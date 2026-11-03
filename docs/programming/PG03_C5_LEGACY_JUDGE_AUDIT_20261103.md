# PG-03_C5 — auditoría del juez determinista legacy y reglas GLOBAL

**Fecha:** 2026-11-03 · **Modo:** técnico/source-only; sin escritura de Supabase, merge, ni cambio de repo propietario.

## Reutilización verificada

- C5 base: `cristhianlujan/claude-persona-lf-patch` PR #3500 (DRAFT), HEAD `f9dd41f6d49848962f10924017aac3952659c7a4`.
- Corrección **ya existente y NO repetida**: PR #3526, HEAD `ed7c2e9302b1b3707f95206e9fb77de582ddaaa6`, añade comprobación del SHA de proyección en **`deterministic_judge_complete`**, con nueve negativos.
- Archivo exacto `pg03_domain_judges_v1.py` consultado en HEAD #3526, Git blob `59dded8253c3f228b437f1fc047fd72db12fdb58`. Se reconstruyó localmente el archivo entero y `git hash-object` devolvió el **mismo blob SHA**.
- No se añadió juez, motor, adaptador, workflow ni clasificador paralelo.

## Hallazgos incrementales: función *legacy* `deterministic_judge` + `project_rules`

La función legacy es distinta de `deterministic_judge_complete` ya corregida. En el origen, su `PASS_CANDIDATE_ONLY` solo comprueba IDs suministrados por el caller, sin verificar SHA de proyección. El proyector permite un override `global_domains=()` que elimina reglas transversales del contexto.

Prueba contra la implementación original #3526, con catálogo y estrategia **sintéticos**, usando sus funciones originales:

```text
C5_BASELINE {'status': 'PASS_CANDIDATE_ONLY', 'code': 'DETERMINISTIC_STRUCTURAL_PASS_NOT_AUTHORIZED'}
C5_TAMPERED_TEXT {'status': 'PASS_CANDIDATE_ONLY', 'code': 'DETERMINISTIC_STRUCTURAL_PASS_NOT_AUTHORIZED'}
C5_MISSING_GLOBAL_WITH_CALLER_EMPTY_IDS {'status': 'PASS_CANDIDATE_ONLY', 'code': 'DETERMINISTIC_STRUCTURAL_PASS_NOT_AUTHORIZED'}
C5_GLOBAL_OVERRIDE ['B1']
C5_GLOBAL_OVERRIDE_JUDGE {'status': 'PASS_CANDIDATE_ONLY', 'code': 'DETERMINISTIC_STRUCTURAL_PASS_NOT_AUTHORIZED'}
```

El resultado es candidato no productivo, pero es una brecha de integridad y exhaustividad **de esta ruta legacy**. No afirmar explotación productiva o bypass de `deterministic_judge_complete` sin evidencia de qué consumidor invoca cada función.

## Corrección mínima preparada y ejecutada localmente

Parche: `docs/programming/patches/PG03_C5_LEGACY_JUDGE_GLOBAL_GUARD_20261103.patch`.

- `project_rules`: impide cambiar el dominio transversal `GLOBAL` desde el argumento opcional.
- `deterministic_judge`: prohíbe `mandatory_ids=[]` y valores no-string/vacíos; recalcula `projection_sha256` y `estimated_tokens` antes del PASS, preservando el algoritmo original; obliga a que todos los IDs `GLOBAL` proyectados estén en `mandatory_ids`.
- No modifica el juez completo #3526 ni crea ninguno nuevo.

El archivo original exacto por Git blob se preservó localmente. Se aplicó la corrección en copia local, se ejecutó `python3 /mnt/data/pg03_c5_audit/test_legacy.py`, y el parche generado superó `git apply --check` sobre el árbol fuente original fijado:

```text
PASS_C5_LEGACY_JUDGE_POSITIVE=1
PASS_C5_LEGACY_NEGATIVE=tamper_text
PASS_C5_LEGACY_NEGATIVE=drop_global
PASS_C5_LEGACY_NEGATIVE=empty_required
PASS_C5_LEGACY_NEGATIVE=skip_global_required
PASS_C5_LEGACY_NEGATIVE=override_global
C5_LEGACY_SOURCE_ONLY_PASS positives=1 negatives=5 authority=false
```

**Limitación:** un hash local no acredita el catálogo publicado ni el productor; no se ejecutó juez semántico independiente ni se autenticaron recibos. Las pruebas son sobre código fuente del HEAD exacto, modificado solo en memoria/archivos locales.

## Estado y siguiente paso

**`PG03_C5_LEGACY_GUARD_LOCAL_PASS / C5_ORIGINAL_SOURCE_UNMODIFIED / C5_RUNTIME_POR_VERIFICAR`**.

La integración del parche en la rama propietaria requiere revisión independiente; mientras el sandbox es el único repo de trabajo, conservarlo como propuesta no aplicada. Siguiente checkpoint técnico independiente PG-03_C6 (suficiencia), tras comprobar sus PR y pruebas existentes. No reabrir PG-00/Análisis o reutilizar estados Supabase como progreso técnico.
