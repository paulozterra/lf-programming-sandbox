# Ejercicio 2 — Contrato `check_migrations`

**Fuente normativa de este ejercicio:** este documento. El Worker debe implementar la función desde cero en `standards/tools/migrations.py` y conectarla al subcomando `migrations` de `standards/tools/checks.py`. **No modificar** este documento, los tests, `vendor/` ni el pipeline.

## Interfaz y alcance

```python
def check_migrations(paths: list[str]) -> list[str]:
    ...
```

`paths` contiene nombres/rutas de archivos *declarados*, no directorios para recorrer. Analizar exclusivamente el **nombre final** de cada ruta (por ejemplo, de `db/V1__init.sql` extraer `V1__init.sql`). No leer el sistema de archivos ni ejecutar SQL. Devolver una lista de diagnósticos `str`, sin imprimir desde la función. Cada diagnóstico comienza con el ID de regla correspondiente (`MIG-01`…`MIG-07`) e incluye el **nombre del archivo completo** que lo originó. La lista vacía `[]` se considera válida y devuelve `[]`.

### Reglas verificables

**MIG-01 — Forma del nombre.** Todo archivo que termine exactamente en `.sql` debe seguir `V<n>__<desc>.sql`, con `V` mayúscula, separador de **dos** guiones bajos, y `n` como decimal positivo. Un nombre que no permite reconocer número de versión informa `MIG-01`. Ejemplo: `V1__init.sql` válido; `migration_1.sql` → `MIG-01`.

**MIG-02 — Descripción.** `desc` contiene **solo** `[a-z0-9_]` y mide entre **1 y 60 caracteres** inclusive. La validación es por caracteres del nombre, no por bytes de la ruta. Si la estructura y versión permiten identificar `desc` pero esta es inválida, informar `MIG-02`. Ejemplo: `V1__create_table.sql` válido; `V1__Bad.sql` → `MIG-02`.

**MIG-03 — Versiones únicas.** Entre las migraciones con número de versión identificable, cada valor entero de versión aparece solo una vez. En duplicados, informar `MIG-03` para **cada archivo repetido después del primero**, siendo «primero» el de nombre completo lexicográficamente menor; la numeración se compara como entero. Ejemplo: `V1__a.sql`, `V2__b.sql` válido; `V1__a.sql`, `V1__b.sql` → `MIG-03` en `V1__b.sql`.

**MIG-04 — Secuencia desde 1.** Las versiones enteras identificables deben formar la secuencia `1, 2, …, N` **sin huecos**. Si falta `1` o una versión intermedia, informar `MIG-04` para el **primer archivo de la siguiente versión existente**, incluyendo el nombre y la versión faltante en el mensaje; solo un error por hueco detectado. Ejemplo: `V1__a.sql`, `V2__b.sql` válido; `V1__a.sql`, `V3__c.sql` → `MIG-04` asociado a `V3__c.sql`, por ausencia de `2`.

**MIG-05 — Ceros iniciales.** Una versión numérica no admite ceros a la izquierda (`V01` o `V001`), aunque su valor entero coincida con otra. Informar `MIG-05` conservando el nombre original. Ejemplo: `V1__a.sql` válido; `V01__a.sql` → `MIG-05`.

**MIG-06 — Otros archivos ignorados.** Cualquier nombre que no termine exactamente en `.sql` se ignora; no cuenta para duplicados ni secuencias y **no produce diagnósticos**. La extensión se compara de forma sensible a mayúsculas. Ejemplo: `README.md` o `V2__notes.SQL` se ignoran; `V2__notes.sql` sí se analiza.

**MIG-07 — Orden determinista y mensajes.** Ordenar todos los diagnósticos **por versión numérica ascendente y luego por nombre completo de archivo ascendente**; dentro de un mismo archivo, ordenar por ID `MIG-01`…`MIG-07`. Los nombres SQL sin versión reconocible se colocan **después** de las versiones numéricas y se ordenan por nombre. No depender del orden de entrada ni de la iteración de un `set`. Cada diagnóstico incluye el nombre completo del archivo. Ejemplo: con `["V3__b.sql", "V1__a.sql", "V3__a.sql"]`, cualquier diagnóstico de `V1__a.sql` precede a los de `V3__a.sql`, y estos a los de `V3__b.sql`.

## Decisiones de interoperabilidad

- Para `MIG-03` y `MIG-04`, las versiones válidas sintácticamente pero con descripción defectuosa o cero inicial siguen contando por su **valor entero**; se informa además su problema específico.
- Una ruta con nombre `.sql` imposible de analizar produce `MIG-01` y se omite de la secuencia por carecer de versión identificable.
- Por cada archivo puede haber más de un diagnóstico (por ejemplo, `MIG-05` y `MIG-03`).
- Si la lista es vacía, o solo contiene archivos no `.sql`, devolver `[]`.
- `checks.py` debe añadir el subcomando `migrations <archivo>...`, llamar a `check_migrations(args)`, imprimir un diagnóstico por línea y devolver `1` si hay errores o `0` si no. El subcomando debe aceptar lista vacía, que es válida. Mantener los subcomandos existentes intactos.

## Fronteras del piloto

La tarea visible incluye esta especificación, `standards/tools/checks.py` y `standards/tests/test_migrations.py`. **Solo** están autorizados como escritura `standards/tools/migrations.py` (nuevo) y `standards/tools/checks.py` (integración). `standards/tests/**` está protegido. Claude diseñará el examen oculto **fuera del repositorio** y entregará su SHA-256 antes de habilitar la tarea. Ni el examen ni sus casos se publican en este PR.
