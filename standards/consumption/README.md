# C11 — Consumo D16/D17 (contrato, no despliegue)

**Artefactos:** `pricing.json` y `policy.json` v0.1.0, `schema/usage-event.schema.json`, `ddl/model_usage.sql`. Modelo autorizado en PG-07, no aquí: todos `approved_for_use=false`. Precios verificados el 23/10/2026: OpenAI [pricing](https://developers.openai.com/api/docs/pricing), Anthropic [pricing](https://platform.claude.com/docs/en/about-claude/pricing). Los valores excluyen regiones y modificadores adicionales no medidos: ante tier no cubierto, no calcular. La selección de precio usa `occurred_at` y conserva `price_row_sha256`; no recalcular llamadas ya registradas.

**Excepción D10:** los montos de negocio siguen `numeric(18,2)`; únicamente costo técnico por tokens `numeric(24,12)`, expresado como decimal textual en JSON.

**Medición y clasificación:** `MEASURED` exige `provider_response_id`. El consumo tiene una fila por llamada; los eventos de reclasificación son nuevas filas. La clase efectiva se determina por `id`, no por `decided_at`. Vistas por lote, pedido y etapa; sumar costos solo por moneda y con evidencia. No almacenar prompts ni respuestas.

**Optimización:** solo `STANDARD` V1, palancas 1–4 activas y selección automática de modelo apagada. Presupuesto `POR_DEFINIR`: solo medición, `BUDGET_UNCONFIGURED_MEASURE_ONLY`. PG-16 decidirá monto. El modo jamás cambia estándares, revisión ni pruebas.

**Destino:** código y precios canónicos en el repositorio. Eventos persistentes y reclasificaciones en `programacion` vía Train cuando lo habilite Router; precios/política compartidos potencialmente en `transversal`. No se escribe en Supabase en C11.

**Pedidos para Cristhian (sin editar su repo):**
- Exponer `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens` y TTL desde las respuestas originales de cada proveedor, conservando ausencia como `UNMEASURED`.
- Incorporar `provider_response_id`, tier, modelo resuelto, fecha, recibo, correlación y persistencia vía Train con idempotencia por `event_id`.
- Para Anthropic, el `total_tokens` actual se calcula entrada+salida y excluye caché; debe incluir lectura/escritura o dejar de calcularse.
- Recibir el contrato de presupuesto/modo de PG-01, congelar cada costo registrado y permitir reclasificación posterior append-only.
- Medir cache-hit-rate sobre campos reales; no estimar tokens ni perder llamadas fallidas con uso medible.
