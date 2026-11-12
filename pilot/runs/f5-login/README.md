# F5.1 Login · intake ejecutado, PG04 detenido por falta de unión A6→DATA

Resultado del `analysis.json` original A9: `INTAKE_ACCEPTED`
(ver `state.json`). Los 6 requisitos y 19 frentes provienen de las
fixtures ficticias de F4, no de Supabase productivo.

**No existe `lots.json` de dos lotes**: `plan_lots.py` admite
exactamente un átomo por scope y exige requisitos para cada scope.
A9 emitió solo `SBX-AUTH-LOGIN` y ninguno de sus 6 requisitos A6 está
vinculado al frente `DATA_CONTRACT`. El código F5.1 falla con
`F51_DATA_REQUIREMENT_NOT_SOURCE_BOUND`, antes de convertir
las sugerencias de área en decisiones. No crea rutas SQL/Java,
no registra Worker y no ve ni escribe exámenes.

La evaluación `assignment_assessment.json` ofrece trazabilidad:
- BACKEND: 3 reglas explícitas de seguridad con área tipada;
- DATA: ninguna regla A6 vinculada;
- sin asignar: USER, PASS y ERR (front_kind OTHER/STATE_ERROR,
  execution_area_hint UNKNOWN);
- frentes materiales adicionales UNKNOWN: 8.

Se conservaron **dos bloques separados por candidato de tarea**
(`.lf/worker-context/f5data` y `f5backend`):
`reglas_tecnicas.json` tiene exclusivamente reglas de PG-00,
incluyendo STD-SEC y el dominio STD-DB/STD-BE según área;
`reglas_negocio.json` tiene únicamente reglas tipadas de A9.
Ambos son candidatos explícitamente `NOT_REGISTERED`.
El bloque de negocio DATA está vacío y bloqueado, no inventado.

**Dependencia de decisión para avanzar a 2 lotes**:
fuente vinculante que asigne al menos un requisito A6 y su criterio
al frente DATA, o nueva evidencia de PG-04 que establezca esa
partición sin inferir por texto libre. Se precisa además una
disposición explícita para los UNKNOWN. La nota exacta
`claude/nota-analisis-a-programacion-f5-20261112.md` no estuvo
disponible en los repositorios/archivos conectados al ejecutar
esta tanda; la revisión de su texto es un bloqueo adicional.

Esta preparación no modifica `analysis/`, `intake.py`,
`plan_lots.py`, productores fijados, P4, ex6, ex7 o ex8.
No se etiqueta ni se fusiona automáticamente.
