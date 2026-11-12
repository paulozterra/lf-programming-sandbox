# Modo continuo (default) — constructor GPT en el sandbox

Fuente de verdad para cualquier agente constructor (GPT u otro). Las instrucciones del proyecto de ChatGPT apuntan a este archivo.

## Regla
Cuando te pidan un pedido (`pilot/runs/<pedido>/`) o un lote, **llévalo hasta el final sin pedir permiso entre pasos**. Para pausar, el usuario escribe **"modo paso a paso"**.

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
