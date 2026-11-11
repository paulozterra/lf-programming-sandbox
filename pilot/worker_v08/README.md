# LF Worker v0.8 — piloto gobernado

**Estado:** PR draft, únicamente revisión estática. No se ha ejecutado el workflow pagado ni instalado secretos ni cargado saldo. El ensayo gratuito original con FakeModel fue calificado como PASS por Claude (evidencia reportada por Paulo).

## CP1.1 — PostgreSQL 17 desechable para ambos modos (2026-11-11)

Los jobs `worker-native.yml` (híbrido) y `worker-pilot.yml` (API) disponen de Node 22, npm y PostgreSQL 17 **solo dentro del runner efímero** de GitHub Actions. La conexión de pruebas es:

```text
postgresql://pilot:pilot@127.0.0.1:5432/pilot
```

Usuario: `pilot`. Contraseña: `pilot`. Base: `pilot`. Host: `127.0.0.1`, puerto: `5432`. **Es una credencial fija ficticia, no es un secreto ni debe reutilizarse en infraestructura persistente o productiva.** Las tareas y los exámenes del sandbox que necesiten Postgres usan explícitamente esta URL. No apunta a Supabase ni a otra BD real.

El Worker vendorizado filtra las variables de entorno a `SAFE_ENV_KEYS` y **no** transmite `PGPASSWORD` a los procesos de prueba. Por eso el smoke test de CP1.1 ejecuta `psql -w` con la URL completa dentro de `env -i`, conservando únicamente `PATH`, `HOME` y `LANG`: verifica conectividad sin depender de `PGPASSWORD` ni de una variable inyectada al Worker. El mensaje `CP1_1_ISOLATED_TOOLCHAIN_PASS` solo se emite después de una consulta SQL exitosa. El servicio se descarta al terminar el job.

## 1. Fuente, procedencia y aislamiento

El Worker **original** de `cristhianlujan/programming-agent` en el commit `298307e2f9cac72abfde2b181f3554b0e28bad24` está copiado exactamente en `vendor/programming-agent/`. Únicamente contiene `src/`, `pyproject.toml` y el archivo adicional de auditoría `PROVENANCE.json`: **72 archivos fuente, 675415 bytes**. Se verificó que los SHA-1 de Git de los 72 blobs copiados coinciden con los del commit original; `PROVENANCE.json` registra además SHA-256, tamaño y ruta de **cada** archivo.

Antes de instalar cualquier paquete, el workflow ejecuta:

```bash
python3 pilot/worker_v08/verify_vendor.py --root vendor/programming-agent
python3 pilot/worker_v08/test_verify_vendor.py
```

La verificación falla si hay contenido alterado, archivo faltante o adicional, symlink, SHA-256/SHA-1 distinto o tamaño no esperado. Para evitar que pip ensucie el árbol git, **se copia el vendor verificado a `RUNNER_TEMP`** y se instala desde esa copia exacta. No se usa checkout remoto ni token para Worker.

El adaptador de costo de #3676 está incluido separadamente y **sin alteraciones** en `pilot/worker_v08/cost_adapter/`, con sus tres archivos (`pg07_to_worker_v1_adapter.py`, `worker_cost_report_v1.py`, `pricing_v1.json`) y `PROVENANCE.json` que verifica sus SHA-1 de Git. Commit fuente `5c981dfc77f8ffee1aa3cd66ab08a3b4d0051e2e`. Tampoco requiere checkout ni token remoto en el workflow.

## 2. Ejecutor y alcance EXACTO

`pilot/worker_v08/run_live_pilot.py` llama a **`run_verified_worker` REAL** del Worker vendorizado con `AnthropicMessagesClient`, NO al CLI endurecido ni a `run_programming_quality_worker_hardened`. El artefacto/recibo candidato declara **`QUALITY_CLI_NOT_USED=true`**; ningún baseline ficticio se crea ni se necesita. Esto NO significa que se haya superado el pipeline de calidad endurecido.

`pilot/worker_v08/tasks.json` selecciona dos tareas autorizadas: ejercicio 1 (validación `check_branch()` en `checks.py`) y ejercicio 2 (`check_migrations()` nuevo más integración con `checks.py`). El manifiesto `manifest.json` conserva únicamente los parámetros heredados del ejercicio 1. Un WorkerTaskSpec V1 con **exactamente 14 campos** se valida con `parse_worker_task` original. Restricciones: **max_attempts hasta 3 (Haiku) / 1 (Sonnet), max_context_bytes=60000, max_patch_bytes=20000, max_changed_files=3, allow_deletions=false, max_output_tokens=8000**. Cualquier exceso BLOQUEA.

El Worker crea un repositorio desechable para pruebas y entrega un parche, NO realiza commits, pushes, merges ni PR. La admisión PG-07 permanece **false** sin evidencia auténtica de los contratos de esa etapa.

## 3. Examen oculto en base64, fuera del repositorio

El único secreto del examen en GitHub Actions es **`PILOT_HOLDOUT_B64`**: contenido completo del JSON del holdout codificado en base64, SIN líneas nuevas. El workflow decodifica con `base64.b64decode(...,validate=True)` y compara SHA-256 **de los bytes decodificados** con:

```
979a661f32627a6d5fb8585ca413835bed0242369887970798184b3a8d3ab821
```

El archivo se escribe con umask 077 y modo 0600 exclusivamente en `RUNNER_TEMP/lf-worker-pilot/holdout.oracle.json`, nunca en el repositorio ni el contexto del modelo, y no se carga como artefacto. La clave `ANTHROPIC_API_KEY` se entrega **solo al paso de ejecución** como secreto, sin echo ni `set -x`.

## 4. Actions fijadas por commit y candados del flujo

`.github/workflows/worker-pilot.yml` utiliza **únicamente `workflow_dispatch`**. Entradas de opción única: provider `anthropic`, modelo `claude-haiku-5-5`, max_attempts `1`. Permisos `contents: read`, ningún PR automático, concurrency singleton con `cancel-in-progress: false`, job de 10 minutos.

Las Actions están fijadas a SHA de commit verificadas a partir de sus etiquetas oficiales:

| Action | SHA exacto |
|---|---|
| actions/checkout v4 | `11d5960a326750d5838078e36cf38b85af677262` |
| actions/setup-python v5 | `a26af69be951a213d495a4c3e4e4022e16d87065` |
| actions/upload-artifact v4 | `ea165f8d65b6e75b540449e92b4886f43607fa02` |

El workflow instala el Worker vendorizado **después** de la prueba de integridad. Ejecuta únicamente el Worker original con el modelo real y un máximo de 8000 tokens de salida.

## 5. Recibos, límites de costo y exposición

Una envoltura de observación registra sin alterar el recibo visible sellado del Worker, porque el recibo verificado final no expone `attempts[].usage`. El adaptador de costo local de #3676 lee los contadores **reales** de entrada/salida; nunca inventa tokens. Si faltan, el job falla cerrado. Modelo resuelto desconocido también se bloquea.

La barrera final exige **costo estimado total USD ≤ 0.10**, con recibos/huellas originales intactos. Esta es una **barrera posterior**: no garantiza un límite bancario previo a una llamada que ya se cobró. Se conservan recibos y costo en artefactos incluso si se supera el tope y el job falla, pero el **parche solamente** se sube si el Worker retorna PASS y la barrera de costo también PASS.

Los únicos artefactos permitidos son recibos verificados/visibles, costo, logs de estado sin secretos y parche condicionado. El holdout y la clave nunca se suben.

## 6. Revisión gratuita antes de cargar saldo

```bash
python3 pilot/worker_v08/verify_vendor.py
python3 pilot/worker_v08/test_verify_vendor.py
python3 pilot/worker_v08/test_workflow_policy.py
```

Claude debe confirmar el resultado de estos comandos, la equivalencia byte a byte del Worker, el aislamiento del holdout y el fail-closed del presupuesto. **No invocar `workflow_dispatch`, no cargar saldo ni definir secretos antes de la aprobación de Claude.**

La corrida histórica gratuita puede reproducirse aparte con `run_fake_e2e.py` y checkouts externos; ese script de demostración no es ejecutado por el workflow real.

**Autoridad:** `CANDIDATE_SANDBOX_ONLY`, `QUALITY_CLI_NOT_USED=true`, `PG07_ADMITTED=false`, `production_authority=false`.

## Límites preventivos autorizados tras la primera corrida real

Primera corrida (run `42114542965`): Haiku ×1, `PROPOSAL_INVALID` por formato del diff; entrada 2775, salida 546, USD 0.0005505. No se aplicó parche. **El Worker original y su prompt no se modifican**.

Paulo autorizó expresamente estos presupuestos máximos estimados, utilizando el pricing versionado existente del adaptador: Haiku 5.5 USD 0.10/0.50 y Sonnet 5.5 USD 2.00/10.00 por millón de tokens de entrada/salida, respectivamente. Sin cambiar los 60 000 bytes de contexto ni los 8000 tokens máximos de salida:

| Selección | Peor caso por corrida | Límite | Decisión |
|---|---:|---:|---|
| Haiku ×1 | USD 0.010 | USD 0.03 | PASS preventivo |
| Haiku ×2 | USD 0.020 | USD 0.03 | PASS preventivo |
| Haiku ×3 | USD 0.030 | USD 0.03 | PASS preventivo |
| Haiku ×4 | Fuera del tope de 3 intentos | USD 0.03 | BLOCK |
| Sonnet ×1 | USD 0.200 | USD 0.20 | PASS preventivo |
| Sonnet ×2 | USD 0.400 | USD 0.20 | BLOCK |
| Sonnet ×3 | USD 0.600 | USD 0.20 | BLOCK |

El cálculo anterior es `max_attempts × (60000 × precio_entrada + 8000 × precio_salida) / 1_000_000`; trata los bytes de contexto como unidades de tokens de entrada a favor de una cota conservadora, **no** es una garantía de facturación máxima ofrecida por Anthropic. `budget_gate.py` bloquea antes del paso con clave, y `run_live_pilot.py` repite la decisión tanto en prepare como en execute. El control posterior exige tokens reales y el mismo tope por modelo.

La tabla de precios en `pilot/worker_v08/cost_adapter/pricing_v1.json` **ya** incluía Sonnet y está vinculada a la huella inmutable del adaptador de #3676. No fue editada; su versión es `2026-11-05-owner-assumption`.

Pruebas estáticas para Claude (sin clave/modelo):

```bash
python3 pilot/worker_v08/test_budget_gate.py
python3 pilot/worker_v08/test_workflow_policy.py
python3 pilot/worker_v08/verify_vendor.py
```

Las opciones del selector son Haiku/Sonnet y 1/2/3, pero la autorización se determina por modelo y costo **antes de llamar a la API**. El error de formato del diff no justifica alterar el prompt del Worker: si persiste, se registra.

## Ejercicio 2 — migraciones (PR nuevo, sin solución anticipada)

Archivo normativo: `standards/tools/MIGRATIONS_SPEC.md`, SHA-256:

```
b699c77f46df4c1be31865d3568ee5c1f2673f6b0cfbe1745bba60d7b068251c
```

Define `check_migrations(paths: list[str]) -> list[str]` con siete reglas `MIG-01`…`MIG-07`: nombre `V<n>__<desc>.sql`, descripción `[a-z0-9_]` de 1–60 caracteres, unicidad de versión, secuencia desde 1, ceros iniciales prohibidos, ignorar no-`.sql` y ordenar diagnósticos por versión/nombre. Contiene un ejemplo por regla y reglas precisas para nombres sin versión y diagnósticos múltiples.

Las 14 pruebas **visibles** (`standards/tests/test_migrations.py`) incluyen una positiva y otra negativa por ID. Se dejan **deliberadamente RED** hasta que el Worker implemente el archivo nuevo `standards/tools/migrations.py` e integre el subcomando `migrations` en `standards/tools/checks.py`. El PR no contiene esa implementación. No se han visto ni creado casos del examen oculto; Claude lo diseña fuera de GitHub.

`pilot/worker_v08/tasks.json` contiene exclusivamente dos opciones fijadas para el selector manual, con:
- `exercise-1`: objetivo/ámbito/holdout existentes; SHA `979a661f…ab821`.
- `exercise-2`: contexto `MIGRATIONS_SPEC.md`, `checks.py` y prueba visible; escritura exclusiva `migrations.py` y `checks.py`; `standards/tests/**` protegido; objetivo incluye SHA normativo; **SHA registrado `44f75fa89fa6974cdcecc43bb2c2669d73eb4bf45fbebb3ec0f2308fce3551ee`** aportado por Claude, sin contenido del examen en el repositorio.

`task_selector.py` verifica la especificación por bytes, los dos scopes permitidos, tareas canónicas y la existencia del SHA por ejercicio **antes** de la instalación y de exponer secretos. Si alguna tarea no tiene SHA auténtico, el workflow se detiene sin API. El holdout del ejercicio 1 utiliza solo `PILOT_HOLDOUT_B64`; el del ejercicio 2 utiliza solo `PILOT_HOLDOUT_EX2_B64`, con pasos separados, sin fallback. Ambos se decodifican en `RUNNER_TEMP`; solo el SHA del ejercicio seleccionado se acepta.

Conserva los topes, el motor `run_verified_worker` original, el Worker vendorizado sin cambios, el flujo manual, el control preventivo/posterior de USD y el upload condicional del parche.

### Verificación offline

```bash
python3 pilot/worker_v08/test_workflow_policy.py
python3 pilot/worker_v08/test_budget_gate.py
python3 pilot/worker_v08/verify_vendor.py
python3 pilot/worker_v08/test_task_selector.py
```

Las tres primeras pruebas son la puerta solicitada. La cuarta demuestra que el ejercicio 2 permanece bloqueado sin el SHA del examen oculto.

**Bloqueo esperado si no existe el secreto correcto:** `PILOT_HOLDOUT_B64_MISSING` o `HIDDEN_HOLDOUT_SHA_MISMATCH`. El SHA del ejercicio 2 está registrado, pero la ejecución real requiere que el secreto privado corresponda exactamente a esa huella. No se ejecuta el modelo en este PR.

## Registro gobernado del examen oculto del ejercicio 2 (sin contenido)

- Única información recibida y registrada: SHA-256 `44f75fa89fa6974cdcecc43bb2c2669d73eb4bf45fbebb3ec0f2308fce3551ee`. No se ha visto ni almacenado el examen.
- `tasks.json` fija esa huella exclusivamente en `exercise-2`. `task_selector.py` rechaza que se sustituya por la del ejercicio 1 (`PILOT_EXERCISE2_HOLDOUT_SHA_DRIFT`).
- `run_live_pilot.py` obtiene SHA, contexto y alcance de escritura del ejercicio seleccionado en `tasks.json`, y mantiene las comprobaciones del manifiesto heredado para `exercise-1`.
- El workflow selecciona `PILOT_HOLDOUT_B64` solo en el paso `if: exercise-1` y `PILOT_HOLDOUT_EX2_B64` solo en el paso `if: exercise-2`; **no hay fallback entre secretos**. Cada paso comprueba la huella que exporta el selector.
- `standards/changes/CHG-0007.json` registra el cambio autorizado y `standards/CAMBIOS.md` es la vista generada. C9 no se desactiva.
- Las 14 pruebas visibles del ejercicio 2 se omiten **exclusivamente cuando todavía no existe** `standards/tools/migrations.py` en el PR preparatorio. Cuando el Worker crea ese módulo, vuelven a ejecutarse íntegramente; si hay un módulo roto o faltan dependencias distintas, el test no se omite.

Pruebas adicionales offline: `python3 pilot/worker_v08/test_preflight_routing.py` verifica la ruta de preflight de ambos ejercicios con una huella **simulada solo en la unidad de prueba**, sin usar ni reproducir los bytes reales del holdout. No equivale a validación criptográfica del secreto. La verificación SHA real se conserva en el workflow/preflight.
