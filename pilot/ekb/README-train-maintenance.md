# Mantenimiento gobernado de herramientas protegidas del Train

## Alcance
`standards/tools/` y `pilot/sandbox_train*.py` están protegidos por `check_tooling_unchanged`. El bloqueo BRANCH_CONFLICT_TOOLING_CHANGED es deliberado; no se elimina ni se reintenta como si fuera un fallo transitorio.

## Procedimiento excepcional propuesto al owner
1. Crear PR independiente con CHG, pruebas offline y diff acotado. No mezclar lotes, cambios funcionales ni artefactos de pedidos.
2. Acreditar CI exitoso del HEAD exacto, revisión independiente explícita del mismo HEAD y main vigente. Si cambia el HEAD, verificar nuevamente la evidencia.
3. El owner decide explícitamente la excepción. Si la protección de rama permite el merge, usar merge commit (dos padres) desde GitHub; nunca desactivar reglas, usar force push o conceder permisos adicionales. No etiquetar para reintentar un Train que rechaza por tooling.
4. Registrar PR, CHG, HEAD revisado, autorización, merge SHA y motivo INTERVENCION_MANUAL: SI. No fabricar recibo de Train ni afirmar que ocurrió su handoff.
5. Verificar que el merge contiene el HEAD revisado, que el código y CHG están en main y que el CI de push del SHA exacto pasa. Si no hay CI acreditado, bloquear las etapas dependientes; diagnosticar con evidencia.
6. Verificar si el cambio requiere algún evento posterior. Para cambios exclusivamente de infraestructura no inventar un lote o un recibo; usar únicamente mecanismos existentes de barrido sobre main con CI verde. Si no existe vía gobernada, elevar al owner.
7. Cerrar con evidencia de CI y registrar aprendizaje EKB mediante el workflow de registro catalogado, con readback. 

## Evidencia y límites
PR #771, CHG-0534: revisión y CI 45728448708 aprobados; Train 45731331972 rechazó pilot/sandbox_train.py por BRANCH_CONFLICT_TOOLING_CHANGED. El owner realizó merge commit 47145b9b5f1326c07049094a67350d9db6ca4520. La presencia del código en main fue comprobada; el CI de main requiere evidencia separada.
La excepción no autoriza merge de lotes, bypass de protecciones ni ejecución de código de PR con credenciales de escritura. Este documento propone un procedimiento, no altera permisos ni automatiza el merge.
