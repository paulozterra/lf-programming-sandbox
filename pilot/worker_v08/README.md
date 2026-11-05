# LF Worker v0.8 — piloto gratuito con modelo falso

**Estado: PRE-KEY / FAKE_ONLY / NO PRODUCTION.** Esta rama no contiene `ANTHROPIC_API_KEY`, no instala ningún trigger de GitHub Actions y no ejecuta un modelo pagado. No crear `.github/workflows/worker-pilot.yml` hasta que Claude reproduzca el ensayo real completo del Worker y apruebe sus controles.

## Evidencia de la tarea

Fuente **existente** (sin cambios en la rama): `standards/tools/checks.py`, función `check_branch` y su expresión `BRANCH`. Pruebas visibles **existentes**: `standards/tests/test_standards.py`, métodos `CheckTests.test_branch_positive` y `test_branch_negative`. Objetivo pequeño: rechazar work_code que tenga guion inicial/final o dos guiones consecutivos, sin cambiar el caso válido ya existente. Solo se permite parche candidato sobre `standards/tools/checks.py`.

Referencia Worker ORIGINAL: `cristhianlujan/programming-agent@298307e2f9cac72abfde2b181f3554b0e28bad24`, interfaces `run_verified_worker`, `parse_worker_task`, `load_hidden_oracle`, `validate_worker_receipt`, `validate_verified_worker_receipt`.

## Oráculo oculto, FUERA del repositorio

El manifiesto `lf_worker_pilot_branch_holdout_private_20261105.json` está **FUERA** de GitHub; no se almacena en el checkout ni se incorpora al contexto del modelo. Su SHA-256 es:

```
979a661f32627a6d5fb8585ca413835bed0242369887970798184b3a8d3ab821
```

El archivo se entrega por separado al auditor/Claude, no como parte del PR ni de los artefactos de salida. El runner lo exige en una ruta absoluta externa al repositorio y verifica bytes y SHA antes de llamar al Worker. Contiene una prueba de entradas de branch inválidas y preservación de un caso válido. El modelo falso solo recibe el contenido autorizado de `checks.py`, nunca el oráculo.

## Plan de calidad y readback

`run_fake_e2e.py` declara y genera **FUERA** del repositorio:

- `quality-plan.json`, esquema original 1: `task_id` y HEAD reales, ocho dimensiones de riesgo clasificadas con justificación, el riesgo security marcado APPLIES con vínculo al holdout y los cuatro preflights en orden `parse_compile`, `lint_static`, `setup_import`, `reachability`. Los otros riesgos declaran explícitamente N/A porque la función es un predicado local sin estado, no porque se hayan realizado pruebas de esos riesgos.
- `readback-manifest.json`, esquema original 2: `checks=[]` con `not_applicable_reason` documentado por ausencia de tablas/datos externos.
- `holdout.oracle.json`: provisto por el owner como archivo externo; se verifica con `load_hidden_oracle` original, no se fabrica en el repositorio.

Los lectores originales `load_quality_plan`, `load_readback_manifest` y `load_hidden_oracle` validan estos documentos, con hashes SHA-256 calculados sobre los bytes verdaderos. **El runner ejecuta el Worker real `run_verified_worker`, NO el CLI de calidad endurecida v7**: no se atribuye a esas validaciones un PASS del pipeline CLI completo. Esa etapa requiere otra calificación antes de usar claves.

## Ensayo gratuito de dos propuestas fijas

`FakeModel` devuelve `ModelResponse` conforme al patrón del `tests/test_worker.py` ORIGINAL. No usa ningún proveedor de red.

1. **Correcto:** parche regex restringido, pasan las pruebas visibles existentes + el holdout oculto; `run_verified_worker` debe emitir `PASS` y parche.
2. **Incorrecto:** parche sintácticamente válido y que conserva las pruebas visibles, pero sigue permitiendo work_code con doble guion; el holdout debe producir `FAIL` y `patch_delivered=false`, parche vacío.

Se validan ambos recibos reales con validadores originales. Un wrapper captura el recibo **sellado real** del Worker visible sin modificarlo. El costo se obtiene mediante el **adaptador real** `worker_cost_report_v1.price_receipt` de #3676, fijado al commit `5c981dfc77f8ffee1aa3cd66ab08a3b4d0051e2e`. Este admite expresamente el FakeModel original como proveedor de prueba sin facturación: USD 0 por intento con los contadores de `attempts[].usage` reales del Worker, `real_api_usage=false`, y sin alterar tarifas Haiku/Sonnet ni re-sellar el recibo.

El vínculo PG-07 se materializa solo como `PG07_WORKER_PILOT_RECEIPT_LINK_CANDIDATE_V1` con hashes genuinos de task, recibo y costo, y con `pg07_admitted=false`, `pg07_receipt_guard_executed=false`, `production_authority=false`. Sin sobre fuente PG-07 con aprobación real **no** se reclama un recibo admitido por la etapa 7.

## Comando para Claude (sin API)

El auditor necesita cuatro elementos: esta rama limpia, un checkout del Worker pinneado, un checkout de #3676 en el commit del adaptador de costo, y el oráculo entregado por separado fuera de los repositorios.

```bash
export WORKER_CHECKOUT=/ruta/programming-agent
export COST_ADAPTER_CHECKOUT=/ruta/claude-persona-lf-patch-en-5c981dfc
export HOLDOUT=/ruta/externa/lf_worker_pilot_branch_holdout_private_20261105.json
test "$(git -C "$WORKER_CHECKOUT" rev-parse HEAD)" = "298307e2f9cac72abfde2b181f3554b0e28bad24"
test "$(git -C "$COST_ADAPTER_CHECKOUT" rev-parse HEAD)" = "5c981dfc77f8ffee1aa3cd66ab08a3b4d0051e2e"
sha256sum "$HOLDOUT"
python3 pilot/worker_v08/run_fake_e2e.py \
  --worker-checkout "$WORKER_CHECKOUT" \
  --adapter-checkout "$COST_ADAPTER_CHECKOUT" \
  --holdout "$HOLDOUT" \
  --output /tmp/lf-worker-v08-free-receipts
```

Debe devolver dos `PASS FAKE_E2E` (caso correcto PASS, caso incorrecto FAIL según las aserciones) y el informe final `FREE_FAKE_E2E_PASS`; no afirmar esto anticipadamente. Comprobar la limpieza de Git, recibos SHA, ausencia de parche en FAIL, salida sin secretos y costo USD 0. El directorio de salida contiene manifiestos de calidad/readback, recibos, enlaces candidato PG07 y parches; **no contiene el holdout**.

## Barrera para el workflow manual

**No se ha creado** `.github/workflows/worker-pilot.yml`. Para hacerlo después de un PASS independiente de Claude: solo `workflow_dispatch` (sin push/PR/schedule), provider Anthropic y modelo Haiku 5.5 declarado, `max_attempts=1`, máximos de 60 000 bytes contexto, 20 000 bytes parche, 3 archivos, 8 000 tokens salida, job timeout 10 min y concurrency=1; `ANTHROPIC_API_KEY` solo como GitHub secret, nunca impreso, logs ni artifacts; recibo sellado + uso/costo separado; PR draft solo con PASS. La autoría y revisión del workflow son tareas distintas y posteriores.

**Bloqueantes pendientes:** ejecución independiente gratuita no verificada todavía; aprobación de calidad real/PG07; CLI v7 endurecido no calificado para esta tarea; faltan los estándares normativos `STD-BE/FE/DB` en la cadena LF. No cargar saldo ni proporcionar clave.

## Workflow real propuesto — REVISAR ANTES DE CARGAR SALDO

El PR draft incorpora `.github/workflows/worker-pilot.yml` **sin ejecutarlo**. Su único disparador es `workflow_dispatch` con `anthropic / claude-haiku-5-5 / max_attempts=1` como únicas opciones. `contents: read`, concurrency singleton sin cancelación, job de 10 minutos. Los tres checkouts se separan (`source/`, `worker/`, `adapter/`) y Worker/adaptador quedan sujetos a commits exactos. La clave Anthropic solo entra en el paso de ejecución; el holdout se reconstruye exclusivamente desde `PILOT_HOLDOUT_JSON` en `RUNNER_TEMP`, con SHA-256 fijo, modo de archivo 0600 y sin impresión ni artefactos.

**Bloqueante real detectado:** el CLI endurecido de Worker `298307e` lee obligatoriamente `quality/programming_quality/baseline_v1.json`; este repositorio sandbox **no contiene esa ruta** en el HEAD auditado. El workflow **falla antes de habilitar secretos o efectuar llamadas de modelo** con `HARDENED_WORKER_QUALITY_BASELINE_MISSING_NO_MODEL_CALL`. No se crea una baseline ficticia. Para desbloquear requiere un baseline gobernado y evaluado aparte. Esto no invalida el PASS del piloto gratuito `run_verified_worker` (que no ejecutó el pipeline endurecido).

`run_live_pilot.py` construye un WorkerTaskSpec v1 de 14 campos y lo somete a `parse_worker_task` y `check_limits` del adaptador, fija max_attempts=1 / 60 KB / 20 KB / 3 archivos, y ejecuta el **CLI original de Worker** con argv emitido por `build_worker_command` (incluye `--max-output-tokens 8000`). Sin modificar Worker, una envoltura de observación conserva el recibo visible sellado para que `worker_cost_report_v1.price_receipt` extraiga tokens reales. Si no llega recibo o se desconoce el modelo resuelto, costo falla cerrado. El gate final rechaza `total_estimated_usd > 0.10` (cap de rechazo **posterior** a la llamada, no una garantía de límite bancario del proveedor). Solo se sube el parche en PASS del Worker y del gate de costo. El sobre PG-07 sigue **NO_ADMITTED** y no se crea PR automático. Los artifacts contienen únicamente recibos, costo, parche condicional y logs de estado sin secretos; el holdout permanece fuera.

**Antes de cargar saldo:** Claude debe revisar la política del YAML, calificar el baseline real y confirmar si el Worker puede llegar al modelo sin romper controles. No hay API call ni activación del workflow desde esta entrega.
