# Recordatorios — especificación (sandbox, datos ficticios)
Paquete: lf.sandbox.time.reminder. Sin base de datos: almacenamiento en memoria.

## Lote A — modelo y repositorio
REM-A1 `public record Reminder(long id, String text, java.time.LocalTime at)`.
REM-A2 `public interface ReminderRepository { Reminder save(String text, LocalTime at); List<Reminder> findAll(); Optional<Reminder> findById(long id); }`
REM-A3 `@Repository public class InMemoryReminderRepository implements ReminderRepository`, con constructor público sin argumentos.
REM-A4 Los id empiezan en 1 y suben de 1 en 1. `findAll()` los devuelve ordenados por id ascendente, en una lista **no modificable** (una copia).
REM-A5 `text` se guarda con `strip()`. Si es null o queda vacío, o si tiene más de 140 caracteres después del strip, se lanza `IllegalArgumentException`. Si `at` es null, también. `at` se trunca a segundos. Un save que falla no guarda nada.
REM-A6 Debe ser seguro con varios hilos: guardados concurrentes dan id únicos y consecutivos.
REM-A7 El lote A NO crea controladores ni toca archivos fuera de su alcance.

## Lote B — API REST (usa el repositorio del lote A; no lo modifica)
REM-B1 `ReminderController` (@RestController) en el mismo paquete. Recibe `ReminderRepository` **por constructor**: sin `@Autowired` y sin `new InMemoryReminderRepository`.
REM-B2 `POST /api/reminders` con el cuerpo JSON `{"text":"...","at":"HH:mm:ss"}`:
- responde **201**, con `Location: /api/reminders/{id}` y el cuerpo `{"id":N,"text":"...","at":"HH:mm:ss"}` (exactamente esas 3 claves);
- responde **400** si text está vacío o tiene más de 140 caracteres, si falta text o at, si at no tiene el formato exacto `HH:mm:ss` o es inválido, y si el JSON está mal formado.
REM-B3 `GET /api/reminders` responde 200 con un arreglo ordenado por id. `GET /api/reminders/{id}` responde 200 con el objeto, 404 si no existe y 400 si el id no es numérico.
REM-B4 Cualquier otro método sobre `/api/reminders` responde 405. `GET /api/time` sigue igual que en el ejercicio 3.
REM-B5 No modificar los archivos del lote A.

## Lote C — borrado y búsqueda (modifica archivos existentes)
REM-C1 Agregar a `ReminderRepository`: `boolean deleteById(long id)` y `List<Reminder> findByTextContaining(String query)`.
REM-C2 `deleteById`: devuelve true si existía y lo borró, y false si no existía. **Los id nunca se reutilizan**: después de borrar, el siguiente save sigue la numeración.
REM-C3 `findByTextContaining`: búsqueda sin distinguir mayúsculas de minúsculas (`Locale.ROOT`), con `strip()` aplicado a la consulta. Devuelve los resultados ordenados por id, en una lista no modificable. Si la consulta es null, lanza `IllegalArgumentException`.
REM-C4 Tanto el borrado como la búsqueda deben ser seguros con varios hilos, igual que save.
REM-C5 `GET /api/reminders?q=texto` filtra con findByTextContaining. Si `q` falta o está en blanco, devuelve todos.
REM-C6 `DELETE /api/reminders/{id}` responde 204 sin cuerpo si lo borró, 404 si no existía y 400 si el id no es numérico.
REM-C7 Solo se modifican `ReminderRepository.java`, `InMemoryReminderRepository.java` y `ReminderController.java`. No se crean archivos nuevos en `src/main`. Todo lo de los lotes A y B se mantiene.


## Norma de formato — reparación gobernada posterior al lote C

Para todo Java bajo `apps/time-service/src/main/java`, el formato canónico es **google-java-format 1.30.0 `--aosp`** (estilo AOSP, sangría de cuatro espacios). Se utilizará exclusivamente el JAR `google-java-format-1.30.0-all-deps.jar`, cuyo SHA-256 fijado es `f2239a8a234a240a54fdff7809d4b3e66702c21f590c77a0b6cf7b20c829e95a`.

Esta regla entra en vigor **después** del lote C ya fusionado en el commit `e76b213cb2f367f787e0eba3bf8ff74136edd883`. No modifica retroactivamente las pruebas, los recibos ni las huellas de los paquetes v1/v2. El ciclo N+1 `FORMAT_REMEDIATION` solo cambia estilo; se prohíben cambios funcionales. Antes de proponerlo se exige compilación de N y N+1 con `javac --release 21 -g:none` y comparación **byte a byte de todos los `.class`**; cualquier diferencia, archivo extra o faltante implica **BLOCK**. El paquete v3 reflejará el nuevo commit realmente fusionado y su linaje con N.

## Lote D — estadísticas de recordatorios (ejercicio 6, modo nativo)

Solo se **agregan** tres archivos nuevos en `apps/time-service/src/main/java/lf/sandbox/time/reminder/`. No se modifica ningún archivo existente.

REM-D1 `public record ReminderStats(int total, java.time.LocalTime earliest, java.time.LocalTime latest, Reminder next, boolean nextIsTomorrow)`.

REM-D2 `@Service public class ReminderStatsService`, con constructor público sin argumentos y `public ReminderStats compute(List<Reminder> reminders, LocalTime now)`:
- `reminders` o `now` null → `IllegalArgumentException`. No modifica la lista recibida (puede ser no modificable).
- Lista vacía → `total=0`, `earliest=null`, `latest=null`, `next=null`, `nextIsTomorrow=false`.
- `now` se trunca a segundos. `earliest`/`latest` = menor/mayor `at`.
- `next` = el recordatorio con el menor `at` que sea **mayor o igual** que `now`; en empate de `at`, el de **menor id**. `nextIsTomorrow=false`.
- Si ninguno es mayor o igual que `now`, `next` = el de menor `at` (empate: menor id) y `nextIsTomorrow=true`.

REM-D3 `@RestController ReminderStatsController` con `GET /api/reminders/stats`:
- Recibe **por constructor** `ReminderRepository`, `ReminderStatsService` y `java.time.Clock` (sin `@Autowired`, sin `new`).
- Usa `repository.findAll()` y `LocalTime.now(clock)` (prohibido `LocalTime.now()` sin reloj u otro reloj del sistema).
- Responde 200 con exactamente estas claves: `{"total":N,"earliest":"HH:mm:ss"|null,"latest":"HH:mm:ss"|null,"next":{"id":N,"text":"...","at":"HH:mm:ss"}|null,"nextIsTomorrow":bool}`. Las horas siempre con el formato exacto `HH:mm:ss`, también cuando los segundos son cero.
- Las rutas existentes (`/api/reminders`, `/api/reminders/{id}`, `/api/time`) siguen igual; otros métodos sobre `/api/reminders/stats` → 405.

REM-D4 La prueba visible está en `apps/time-service/visible-tests/ex6/` (fuera de `src/test` a propósito, para no romper el CI de `main` antes de que exista el código). Formato del código: norma AOSP de este documento.

## Lote E — edición de recordatorios y duplicados (ejercicio 7, modo nativo)

Este lote **modifica archivos existentes**. Solo se pueden cambiar `ReminderRepository.java`, `InMemoryReminderRepository.java` y `ReminderController.java`. No se crean archivos nuevos en `src/main` y ningún otro archivo cambia, incluidos los del lote D.

REM-E1 Agregar a `ReminderRepository`: `Optional<Reminder> update(long id, String text, LocalTime at)`.
- Valida `text` y `at` exactamente igual que `save` (REM-A5). La validación va **antes** de buscar el id: datos inválidos lanzan `IllegalArgumentException` aunque el id no exista.
- Si el id no existe, devuelve `Optional.empty()` y no cambia nada.
- Si existe, reemplaza `text` (con `strip()`) y `at` (truncado a segundos), **conserva el id y su posición** (findAll sigue ordenado por id) y devuelve el recordatorio actualizado.
- Actualizar no consume ids: el siguiente `save` sigue la numeración normal.
- Seguro con varios hilos, igual que el resto del repositorio.

REM-E2 **No se permiten duplicados.** Dos recordatorios son duplicados si tienen el mismo `text` (después de `strip()`, sin distinguir mayúsculas de minúsculas con `Locale.ROOT`) y el mismo `at` (truncado a segundos).
- `save` de un duplicado lanza `IllegalStateException` y no guarda nada.
- `update` que dejaría un duplicado de **otro** recordatorio lanza `IllegalStateException` y no cambia nada. Un recordatorio nunca es duplicado de sí mismo: actualizarlo con sus mismos valores, o solo cambiando mayúsculas, está permitido.
- Mismo texto con otra hora, u otro texto con la misma hora, no son duplicados. Al borrar un recordatorio, su combinación vuelve a quedar libre.
- Las validaciones de REM-A5 se aplican antes que la de duplicados.

REM-E3 `PUT /api/reminders/{id}` con el mismo cuerpo JSON que el POST (`{"text":"...","at":"HH:mm:ss"}`, hora estricta):
- 200 con el objeto actualizado (`id`, `text`, `at`).
- 400 si el id no es numérico, si el cuerpo falta o es inválido, si la hora es inválida o si el texto no pasa REM-A5.
- 404 si el id no existe (solo cuando el cuerpo es válido: un cuerpo inválido responde 400 aunque el id no exista).
- 409 si el cambio crearía un duplicado (REM-E2).

REM-E4 `POST /api/reminders` de un duplicado responde **409** (antes respondía 201).

REM-E5 Todo lo anterior se mantiene. En particular: `PUT /api/reminders` sigue respondiendo 405 (REM-B4), y **`PUT /api/reminders/stats` debe seguir respondiendo 405** (REM-D3), no 400. `GET /api/reminders/stats` sigue funcionando igual.

REM-E6 La prueba visible está en `apps/time-service/visible-tests/ex7/` (fuera de `src/test` a propósito). Las pruebas existentes de `src/test` deben seguir pasando. Formato del código: norma AOSP de este documento.

## Norma vigente de formato — decisión D1 / Fase 2A (CHG-0029)

El formato canónico **desde la fusión de CHG-0029 en adelante** para todos los archivos `apps/time-service/src/main/java/**/*.java` es **palantir-java-format 2.102.0** con **spotless-maven-plugin 3.10.4**, conforme al texto literal de **STD-BE-05** de `standards/catalog.json` v0.6.1: sangría de 4 espacios, 120 columnas. Se utiliza `mvn -B -f apps/time-service/pom.xml spotless:apply` únicamente en la remediación gobernada; el gate CI aplica `mvn -B -f apps/time-service/pom.xml spotless:check` antes de compilar. Todo cambio de formato exige `javac --release 21 -g:none` sobre **todo** el árbol Java previo y posterior y comparación de nombres de .class y SHA-256 por clase; ninguna divergencia se permite.

**Linaje histórico conservado:** los recibos, verificadores y bundles de EX5C, EX6 y EX7 que fijan google-java-format 1.30.0 `--aosp` corresponden a sus ejecuciones pasadas, y **no deben reinterpretarse ni modificarse**. La norma AOSP anterior de este documento queda superada solo para futuros cambios. El contenido funcional REM-A a REM-E se mantiene inalterado. Las menciones históricas a AOSP en REM-D4 y REM-E6 describen el requisito de aquellos ejercicios al momento de ejecutarse, no una obligación vigente para una nueva versión.

## Lote F: posponer recordatorios (ejercicio 8, modo nativo con perfil y skills)

Este lote **modifica archivos existentes**. Solo se pueden cambiar `ReminderRepository.java`, `InMemoryReminderRepository.java` y `ReminderController.java`. No se crean archivos nuevos en `src/main` y ningún otro archivo cambia. El código debe cumplir el formato del proyecto: palantir-java-format verificado con `mvn spotless:check` (regla STD-BE-05).

REM-F1 Agregar a `ReminderRepository`: `Optional<Reminder> snooze(long id, int minutes)`.
- `minutes` debe estar entre 1 y 1440, ambos incluidos. Si no, lanza `IllegalArgumentException`. Esta validación va **antes** de buscar el id: un valor inválido lanza la excepción aunque el id no exista.
- Si el id no existe, devuelve `Optional.empty()` y no cambia nada.
- Si existe, mueve su hora `at` hacia adelante esa cantidad de minutos. **Si pasa de la medianoche, sigue desde 00:00** (23:50 + 15 da 00:05). **Los segundos se conservan.** El texto, el id y la posición en `findAll` no cambian, y no se consumen ids.
- Aplica la regla de duplicados de REM-E2: si el resultado sería duplicado de **otro** recordatorio, lanza `IllegalStateException` y no cambia nada. Un recordatorio nunca es duplicado de sí mismo; por ejemplo, posponer 1440 minutos lo deja a la misma hora y está permitido.
- Es seguro con varios hilos, igual que el resto del repositorio.

REM-F2 `POST /api/reminders/{id}/snooze?minutes=N` (sin cuerpo):
- 200 con el objeto actualizado (`id`, `text`, `at`).
- 400 si el id no es numérico, o si `minutes` falta o no es un entero válido. Un entero válido son solo dígitos decimales: sin signo, sin espacios y sin decimales. Los ceros a la izquierda se aceptan. También es 400 si `minutes` está fuera de 1..1440.
- 404 si el id no existe, solo cuando `minutes` es válido. Con `minutes` inválido responde 400 aunque el id no exista.
- 409 si el resultado crearía un duplicado (REM-E2).
- Con otros métodos sobre `/api/reminders/{id}/snooze` responde 405.

REM-F3 Todo lo anterior se mantiene (REM-A a REM-E), incluidas las estadísticas: `GET /api/reminders/stats` refleja las horas pospuestas.

REM-F4 La prueba visible está en `apps/time-service/visible-tests/ex8/`. Las pruebas de `src/test` deben seguir pasando y `mvn spotless:check` debe pasar.
