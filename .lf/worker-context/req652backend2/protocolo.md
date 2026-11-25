<!-- Protocolo del constructor inyectado por la ruta (pilot/orchestrator/MODO_CONTINUO.md). No editar aqui. -->
# Modo continuo (default) — constructor GPT en el sandbox

Fuente de verdad para cualquier agente constructor (GPT u otro). Las instrucciones del proyecto de ChatGPT apuntan a este archivo.

## Regla
Cuando te pidan un pedido (`pilot/runs/<pedido>/`) o un lote, **llévalo hasta el final sin pedir permiso entre pasos**. Para pausar, el usuario escribe **"modo paso a paso"**.

## Entrada normal desde el chat (T9)

Cuando una persona pida implementar una pantalla o describa un pedido, GPT usa la conexión a GitHub para crear un **Issue** con la plantilla **Nuevo pedido** del repositorio `paulozterra/lf-programming-sandbox`. El campo **Pedido** contiene **literalmente** el texto de la persona: sin resumen, paráfrasis ni edición. GPT devuelve el enlace al Issue. No escribe `request.md`, no abre el PR y **no agrega etiquetas**: la plantilla y el workflow confiable del bot son responsables de ello.

Si la conexión no permite crear el Issue, GPT comunica el impedimento y entrega el texto exacto para pegarlo en el campo **Pedido** de **Nuevo pedido**, sin simular que se ha admitido la solicitud.

El bot `request-intake.yml` valida la autoría colaboradora, crea `lf/request/req-<issue>` y un PR normal con únicamente `pilot/runs/req-<issue>/request.md` y `request_meta.json`. Política C vuelve a leer el Issue y comprueba cada byte antes del Train. Después de la fusión, T7 recibe el pedido desde `main`; las restantes etapas siguen el modo continuo. El Issue se cierra únicamente cuando la ruta acredita estado terminal y un informe de intervención consultable. No confundir un H_REPORT candidato con finalización.

## Intérprete Python de aceptación (T13)

Los comandos Python generados por `generate_chain` usan `lf-python`, enlazado por el Worker en `/usr/local/bin/lf-python` al intérprete fijo `/tmp/lf-python-runtime/bin/python`. El entorno se crea desde `pilot/worker_v08/python_runtime_requirements.txt` en los workflows native y API. El PATH aislado del Worker (`/usr/local/bin:/usr/bin:/bin`) resuelve `lf-python` sin depender del Python del sistema. Para los exámenes independientes, puede utilizarse directamente `/tmp/lf-python-runtime/bin/python`; el navegador sigue en `/tmp/lf-playwright-browsers`.

## Bucle por lote
1. Toma el siguiente lote listo: su PR `lf/native-registration/*` está fusionado y existe `pilot/runs/<pedido>/proposal_requests/<tarea>.task-pack.json`.
2. Programa la propuesta solo con ese paquete. Antes de enviar:
   - el `task_pack_sha256` coincide con el paquete registrado;
   - pasa el chequeo del área (Java: `mvn -f apps/time-service/pom.xml spotless:check package`).
3. **Envío nativo exacto:** consulta `<tarea>.proposal-request.json` → `submission` (ruta, campos exactos, esquema y ejemplo). El único archivo que debes comitear en `lf/native-proposal/<tarea>` es `pilot/native_proposals/<tarea>.json`, con las cuatro claves exactas `task_pack_sha256`, `proposal_sha256`, `proposal`, `author`. `author` es `"GPT_NATIVE"`. `proposal` es un objeto JSON con exactamente `schema_version: 1`, `summary` no vacío, `patch` (git unified diff UTF-8 del cambio autorizado) y `changed_paths` (rutas ordenadas y únicas). No incluyas rutas de código fuente como archivos del commit de propuesta: el parche va dentro de `proposal.patch`. `proposal_sha256` es SHA-256 de `json.dumps(proposal, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')`; `task_pack_sha256` se copia sin cambios del proposal-request publicado. **Base:** crea una rama nueva desde el `main` confiable *actual* (no solo desde `task_spec.base_head_sha`); el guard exige que todos los commits desde ese main modifiquen solamente el mismo sobre, sin merges, y falla con código exacto si no se respeta. Haz push y espera el resultado del Worker.
4. **Falla y quedan intentos (máx. 3):** consulta el **Issue original del pedido** (`#<número>`): el Worker publica un comentario con marcador `<!-- LF_NATIVE_VISIBLE_FEEDBACK:<tarea>:<SHA-de-propuesta>:<intento> -->`, el resultado y el contenido exacto de `public/feedback.json` (únicamente aceptación visible). Usa ese comentario del Issue para corregir **solo** con el feedback visible y reenvía, sin pedir permiso. Si el comentario todavía no aparece, el siguiente sweep CP3.6 recupera el artifact de una corrida ya ejecutada y publica el mismo comentario; no relances el Worker ni cuentes un intento nuevo por esa publicación.
   **Fallo de infraestructura de la ruta:** cuando el comentario del Issue acredita `ROUTE_DEFECT` (herramienta de aceptación bloqueada por dependencia del entorno, no por la propuesta), ese run queda en el historial sin consumir intento. No reenvíes ni cambies `lf/native-proposal/<tarea>`: el siguiente sweep prepara un PR de registro corregido y, tras Train, reevalúa el mismo SHA. Si la compatibilidad del paquete/base no es verificable, el bot comenta `REENVÍO REQUERIDO` en ese Issue con la instrucción exacta.

5. **Pasa:** el PR de integración se abre, se etiqueta (política C, `pilot/auto_integrate.py`) y el Train lo fusiona solos. Luego el encadenamiento prepara el siguiente lote: vuelve al paso 1.
6. Sin lotes pendientes: entrega un resumen (lotes, intentos, corridas, PRs, H_REPORT).

## Parar y avisar solo si
- un lote falla 3 veces (la integración del intento 3 queda con `REVISION_HUMANA_REQUERIDA`);
- un bloqueo no se resuelve corrigiendo tu propio código (base inválida, paquete que no coincide, examen inválido, infraestructura);
- necesitarías tocar archivos protegidos o fuera del `write_scope`;
- pasan más de 30 minutos sin que aparezca el siguiente lote.

## Nunca
- Buscar, leer o descifrar exámenes ocultos (`pilot/holdouts/`).
- Poner etiquetas ni abrir o fusionar PRs a mano.
- Tocar `vendor/`, `pilot/holdouts/`, `.github/` ni `pilot/sandbox_train*.py`.

## Quién hace qué
| Paso | Responsable |
|---|---|
| Pedido, análisis y lotes | Análisis (A1–A9) + orquestador (`intake.py`, `package_to_lots.py`/`plan_lots.py`) |
| Exámenes ocultos cifrados | Claude (independiente del constructor) |
| Código de cada lote | Constructor (GPT), en modo continuo |
| Verificación | Worker v0.8 + examen oculto |
| Integración y fusión | CP3.5 + política C + Train (automático) |
| Revisión de calidad del pedido completo | Claude con el H_REPORT, hasta que exista la fase de Testing |
