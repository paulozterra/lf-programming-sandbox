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

