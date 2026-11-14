# Modo continuo (default) — constructor GPT en el sandbox

Fuente de verdad para cualquier agente constructor (GPT u otro). Las instrucciones del proyecto de ChatGPT apuntan a este archivo.

## Regla
Cuando te pidan un pedido (`pilot/runs/<pedido>/`) o un lote, **llévalo hasta el final sin pedir permiso entre pasos**. Para pausar, el usuario escribe **"modo paso a paso"**.

## Entrada normal desde el chat (T9)

Cuando una persona pida implementar una pantalla o describa un pedido, GPT usa la conexión a GitHub para crear un **Issue** con la plantilla **Nuevo pedido** del repositorio `paulozterra/lf-programming-sandbox`. El campo **Pedido** contiene **literalmente** el texto de la persona: sin resumen, paráfrasis ni edición. GPT devuelve el enlace al Issue. No escribe `request.md`, no abre el PR y **no agrega etiquetas**: la plantilla y el workflow confiable del bot son responsables de ello.

Si la conexión no permite crear el Issue, GPT comunica el impedimento y entrega el texto exacto para pegarlo en el campo **Pedido** de **Nuevo pedido**, sin simular que se ha admitido la solicitud.

El bot `request-intake.yml` valida la autoría colaboradora, crea `lf/request/req-<issue>` y un PR normal con únicamente `pilot/runs/req-<issue>/request.md` y `request_meta.json`. Política C vuelve a leer el Issue y comprueba cada byte antes del Train. Después de la fusión, T7 recibe el pedido desde `main`; las restantes etapas siguen el modo continuo. El Issue se cierra únicamente cuando la ruta acredita estado terminal y un informe de intervención consultable. No confundir un H_REPORT candidato con finalización.

## Bucle por lote
1. Toma el siguiente lote listo: su PR `lf/native-registration/*` está fusionado y existe `pilot/runs/<pedido>/proposal_requests/<tarea>.task-pack.json`.
2. Programa la propuesta solo con ese paquete. Antes de enviar:
   - el `task_pack_sha256` coincide con el paquete registrado;
   - pasa el chequeo del área (Java: `mvn -f apps/time-service/pom.xml spotless:check package`).
3. Envía a `lf/native-proposal/<tarea>` y espera el resultado del Worker.
4. **Falla y quedan intentos (máx. 3):** corrige **solo** con el feedback visible y reenvía, sin pedir permiso.
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
