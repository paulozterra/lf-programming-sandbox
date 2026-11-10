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
import org.springframework.web.bind.annotation.RequestBody;
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

    @PostMapping("/api/reminders")
    public ResponseEntity<Object> create(@RequestBody(required = false) Map<String, Object> body) {
        if (body == null || !(body.get("text") instanceof String text) || !(body.get("at") instanceof String at)) {
            return ResponseEntity.badRequest().build();
        }
        LocalTime time;
        try {
            time = LocalTime.parse(at, TIME);
        } catch (DateTimeParseException e) {
            return ResponseEntity.badRequest().build();
        }
        Reminder saved;
        try {
            saved = repository.save(text, time);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().build();
        }
        return ResponseEntity.created(URI.create("/api/reminders/" + saved.id()))
                .body(toResponse(saved));
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
