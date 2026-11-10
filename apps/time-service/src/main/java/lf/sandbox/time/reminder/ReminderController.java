package lf.sandbox.time.reminder;

import java.net.URI;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReminderController {

    private static final DateTimeFormatter TIME =
            DateTimeFormatter.ofPattern("HH:mm:ss").withResolverStyle(ResolverStyle.STRICT);

    private final ReminderRepository repository;

    public ReminderController(ReminderRepository repository) {
        this.repository = repository;
    }

    private static LocalTime validBodyTime(Map<String, Object> body) {
        if (body == null || !(body.get("text") instanceof String) || !(body.get("at") instanceof String at)) {
            throw new IllegalArgumentException("invalid reminder body");
        }
        try {
            return LocalTime.parse(at, TIME);
        } catch (DateTimeParseException e) {
            throw new IllegalArgumentException("invalid reminder time", e);
        }
    }

    @PostMapping("/api/reminders")
    public ResponseEntity<Object> create(@RequestBody(required = false) Map<String, Object> body) {
        final Reminder saved;
        try {
            LocalTime time = validBodyTime(body);
            saved = repository.save((String) body.get("text"), time);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().build();
        } catch (IllegalStateException e) {
            return ResponseEntity.status(409).build();
        }
        return ResponseEntity.created(URI.create("/api/reminders/" + saved.id()))
                .body(toResponse(saved));
    }

    @PutMapping("/api/reminders/{id}")
    public ResponseEntity<Object> update(
            @PathVariable String id, @RequestBody(required = false) Map<String, Object> body) {
        final long value;
        try {
            value = Long.parseLong(id);
        } catch (NumberFormatException e) {
            return ResponseEntity.badRequest().build();
        }
        try {
            LocalTime time = validBodyTime(body);
            return repository
                    .update(value, (String) body.get("text"), time)
                    .<ResponseEntity<Object>>map(r -> ResponseEntity.ok(toResponse(r)))
                    .orElseGet(() -> ResponseEntity.notFound().build());
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().build();
        } catch (IllegalStateException e) {
            return ResponseEntity.status(409).build();
        }
    }

    // A variable {id} PUT mapping would otherwise turn PUT /stats into 400.
    // Keep the existing statistics endpoint's method contract (REM-D3/E5).
    @RequestMapping(
            value = "/api/reminders/stats",
            method = {RequestMethod.PUT, RequestMethod.POST, RequestMethod.DELETE, RequestMethod.PATCH})
    public ResponseEntity<Void> statsMethodNotAllowed() {
        return ResponseEntity.status(405).build();
    }

    @GetMapping("/api/reminders")
    public List<ReminderResponse> list(@RequestParam(name = "q", required = false) String q) {
        List<Reminder> found = (q == null || q.isBlank()) ? repository.findAll() : repository.findByTextContaining(q);
        return found.stream().map(ReminderController::toResponse).toList();
    }

    @GetMapping("/api/reminders/{id}")
    public ResponseEntity<Object> get(@PathVariable String id) {
        long value;
        try {
            value = Long.parseLong(id);
        } catch (NumberFormatException e) {
            return ResponseEntity.badRequest().build();
        }
        return repository
                .findById(value)
                .<ResponseEntity<Object>>map(r -> ResponseEntity.ok(toResponse(r)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @DeleteMapping("/api/reminders/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id) {
        long value;
        try {
            value = Long.parseLong(id);
        } catch (NumberFormatException e) {
            return ResponseEntity.badRequest().build();
        }
        if (repository.deleteById(value)) {
            return ResponseEntity.noContent().build();
        }
        return ResponseEntity.notFound().build();
    }

    private static ReminderResponse toResponse(Reminder r) {
        return new ReminderResponse(r.id(), r.text(), r.at().format(TIME));
    }

    public record ReminderResponse(long id, String text, String at) {}
}
