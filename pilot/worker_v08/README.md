# LF Worker v0.8 — piloto gobernado

**Estado:** PR draft, únicamente revisión estática. No se ha ejecutado el workflow pagado ni instalado secretos ni cargado saldo. El ensayo gratuito original con FakeModel fue calificado como PASS por Claude (evidencia reportada por Paulo).

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

Tarea de ensayo declarada en `pilot/worker_v08/manifest.json`: editar solo `standards/tools/checks.py::check_branch`; pruebas visibles **ya existentes** `standards/tests/test_standards.py::CheckTests.test_branch_positive/test_branch_negative`. Un WorkerTaskSpec V1 con **exactamente 14 campos** se valida usando `parse_worker_task` del Worker original y `check_limits` del adaptador. Restricciones: **max_attempts=1, max_context_bytes=60000, max_patch_bytes=20000, max_changed_files=3, allow_deletions=false, max_output_tokens=8000**. Cualquier falta o exceso BLOQUEA.

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
