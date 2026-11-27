# Examinador automático (T58)

Procedimiento que sigue la tarea programada **"Examinador LF"** (una sesión de Claude que corre cada hora, privada, fuera de este repo). Sustituye el aviso manual "ya se abrió el `exam-request`".

El examinador es **independiente del constructor**: el constructor (GPT u otro) nunca ve este trabajo; solo el cifrado y su metadata llegan al repo (regla 4 de `CLAUDE.md`). El texto plano del examen, la referencia y los mutantes viven solo en la carpeta temporal de la sesión.

## 0. ¿Hay trabajo?

```bash
git clone https://github.com/paulozterra/lf-programming-sandbox main   # historial completo, nunca --depth
test "$(git -C main rev-parse --is-shallow-repository)" = false || exit 1   # EXAMINER_CLONE_SHALLOW
cd main && python3 pilot/orchestrator/examiner_queue.py > /tmp/queue.json
```

El clon debe tener historial completo: `lot_recovery.py` (CHG-0634) exige un repositorio no superficial y, con `--depth 1`, la cola clasifica como `stale` pedidos vigentes (caso #890, `req652backend22`).

- `pending` vacío → terminar sin hacer nada más (respuesta de una línea: "sin exámenes pendientes"). Es el caso normal y debe costar casi nada.
- `stale`: solicitudes de tareas ya no planificadas o de pedidos cerrados. **Nunca** se examinan. Se informan en el resumen final, no se tocan.
- `in_flight` (PR `exam/<task>` abierto o etiqueta `examiner-working`) y `blocked` (`examiner-blocked`): no se tocan.
- Como máximo **2 tareas por corrida**, en el orden de la cola (las demás quedan para la hora siguiente).

## 1. Reclamar la tarea

D22: desde un checkout de main vigente, con `GITHUB_REPOSITORY` apuntando al repositorio y `GH_TOKEN` autorizado para lectura, ejecutar `python3 pilot/orchestrator/request_lifecycle.py --request <req>` antes de reclamar, etiquetar, comentar, publicar archivos, abrir PR o despachar CI. Repetir justo antes de cada efecto, incluso tras una espera. Si devuelve `REQUEST_SUSPENDED`, `REQUEST_CLOSED` o `REQUEST_STATE_UNRESOLVED`, terminar sin publicación ni reintento. Una reserva ya existente no autoriza continuar; el owner debe coordinar su drenaje. La rutina externa debe adoptar este procedimiento antes de acreditar SUSPENDED.

Poner la etiqueta `examiner-working` al issue (evita que otra corrida la tome), quitar `exam-retry` si la tiene y comentar: "Examinador automático: escribiendo el examen".

Disparo: la rutina de evento reacciona a un issue `exam-request` **abierto** (examen nuevo) y a un issue **etiquetado** `exam-retry` (reintento). La ruta pone `exam-retry` cuando se integra un retiro E2; el owner la pone al desbloquear un `examiner-blocked`. La corrida horaria es solo respaldo.

Si el issue tiene un comentario "Examen retirado (E2)", el examen anterior se retiró porque su referencia no pasó el ensayo T40: leer el comando visible indicado y corregir la referencia para que lo pase (por ejemplo, implementar todas las operaciones del contrato asociadas a las reglas del lote).

## 2. Brief (sin explorar el repo)

```bash
python3 pilot/orchestrator/examiner_brief.py --request <req> --task <task> \
  --write-paths '<json>' --requirement-ids '<json>' --issue <n> --out /tmp/examiner/<task>
```

`brief.md` trae el objetivo del lote, las reglas de la ficha que el lote carga (con su `config`), las pruebas visibles, los archivos de contexto (contrato, esqueleto) y el contenido actual de las rutas de escritura (pedidos MODIFY). Leer solo lo que el brief no cubra (p. ej. una dependencia ya integrada que el lote consume).

## 3. Escribir examen, referencia y mutantes (en `/tmp/examiner/<task>/`)

- `exam.py`: script Python autocontenido que corre en la raíz del candidato. Define su propio `fail(code)` (imprime el código y `sys.exit(1)`); **sin `assert`**; cada `fail("CODIGO")` es una exigencia observable (build, arranque, HTTP, SQL, Playwright…). Debe caber en el límite del Worker (≈ 240 KB troceado).
- `trace.json`: `{CODIGO: "rule:<CODE>" | "contract:<ruta>" | "request:<req> <decisión>" | "env:<build/arranque>"}`. Un `rule:` solo puede citar una regla **del lote** (sus `REQ-<CODE>`) o un estándar `STD-*`; si no, `publish_exam.py` bloquea con `EXAM_TRACE_RULE_NOT_IN_LOT`. Nunca exigir lo que ninguna regla del lote pide.
- `ref/`: implementación de referencia, **solo** con archivos de las rutas de escritura del lote (`EXAM_REFERENCE_OUT_OF_SCOPE` si no). En BACKEND, formatear el Java de la referencia con `mvn -f <pom> spotless:apply` antes de copiarlo: el registro agrega `std-be-05-spotless-check` (STD-BE-05) y `publish_exam.py` lo corre en el preflight.
- `mut/<nombre>/`: al menos 3 mutantes plausibles (el error que cometería un constructor real), cada uno dentro de las rutas del lote, y cada uno debe hacer fallar el examen.
- Para BACKEND/DATA usar el PostgreSQL desechable de la sesión (`/usr/lib/postgresql/*/bin`, base temporal, variables `DB_URL`/`DB_USERNAME`/`DB_PASSWORD`) como hace el Worker.
- Credenciales ficticias del sandbox (p. ej. el usuario demo): leerlas de las variables `SBX_FIXTURE_*` (`os.environ`), declaradas en `pilot/config/fixture_credentials.json`. **Nunca** escribirlas literales en el examen ni en el argv: el Worker rechaza secretos probables. El Worker y `publish_exam.py` exponen esas variables. Si hace falta una credencial ficticia que no está declarada, bloquear con `EXAM_FIXTURE_CREDENTIAL_UNDECLARED` (decide el owner).

### Lote de caracterización (`lot_kind: CHARACTERIZATION` en el brief)

El lote no implementa nada: GPT debe **describir el comportamiento actual** de `characterized_file_content` como casos JSON de la suite visible (`frontend/visible-tests/`), con `covers` igual a sus `requirement_ids`.

- `exam.py`: corre `playwright_gate.py --suite <carpeta> --mutation-check` y `characterization_covers.py --suite-file <archivo> --requires <ids>` contra el candidato, **más** casos propios del examinador para las reglas de más riesgo (que el candidato no ve): así se detecta una suite que cubre las reglas solo de nombre. Cada `fail` traza a `rule:<CODE>` de esas reglas.
- `ref/`: solo el archivo JSON del lote, con casos que pasan contra `main` sin cambios.
- `mut/` (mínimo 3): `covers` incompleto; un caso solo de visibilidad o de texto trivial; un caso de CSS o caja con un valor que no corresponde al código actual. Todos dentro del único archivo del lote.

## 4. Validar y cifrar

```bash
git clone https://github.com/paulozterra/lf-programming-sandbox /tmp/examiner/<task>/main   # historial completo
python3 pilot/orchestrator/publish_exam.py --task <task> --request <req> \
  --script /tmp/examiner/<task>/exam.py --trace /tmp/examiner/<task>/trace.json \
  --family <area en minúsculas> --version v1 --worktree /tmp/examiner/<task>/main \
  --reference /tmp/examiner/<task>/ref --mutants /tmp/examiner/<task>/mut \
  --derived-from "ficha <fixture> (<códigos>)"
```

Exige que la referencia pase los comandos visibles del lote (`EXAM_REFERENCE_FAILS_VISIBLE:<comando>`), referencia PASS en el examen, todos los mutantes FAIL y cifrado verificado. Si bloquea: leer el código, corregir y repetir. **Máximo 3 vueltas** por tarea.

## 5. Publicar

Rama `exam/<task>` desde `main` con exactamente `pilot/holdouts/<task>.oracle.json.age`, `pilot/holdouts/<task>.reference.json.age` y `pilot/runs/<req>/claude_meta/<task>.json`. Commit `exam(<task>): examen oculto <ÁREA> (cifrado)`. PR a `main` con la etiqueta `ready-to-merge`: el ensayo T40 (`exam-rehearsal.yml`) corre la referencia con el Worker real y el Train integra. Comentar en el issue el número del PR y quitar `examiner-working`.

Si el ensayo T40 del PR falla: corregir en la misma rama (cuenta dentro de las 3 vueltas).

## 6. Si no se logra

Tras 3 vueltas sin éxito: etiqueta `examiner-blocked` en el issue, quitar `examiner-working`, comentario con el último código de bloqueo (sin contenido del examen). Es el único caso que requiere al owner, que al decidir quita `examiner-blocked` y pone `exam-retry`.

## 7. Resumen de la corrida

Una línea por tarea: `task → PR #n` o `task → examiner-blocked (<código>)`, más la lista `stale` si no está vacía.

## Nunca

- Subir texto plano del examen, la referencia o los mutantes, ni imprimirlos en comentarios, PRs o logs.
- Examinar una tarea `stale`, o rehacer un examen ya publicado (eso es una versión nueva, flujo `examiner_defects`).
- Modificar código de la ruta, workflows o permisos desde esta tarea.
