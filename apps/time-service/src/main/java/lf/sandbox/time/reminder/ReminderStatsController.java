package lf.sandbox.time.reminder;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Clock;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.Map;

@RestController
public class ReminderStatsController {

    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm:ss");

    private final ReminderRepository repository;
    private final ReminderStatsService statsService;
    private final Clock clock;

    public ReminderStatsController(
            ReminderRepository repository, ReminderStatsService statsService, Clock clock) {
        this.repository = repository;
        this.statsService = statsService;
        this.clock = clock;
    }

    @GetMapping("/api/reminders/stats")
    public Map<String, Object> stats() {
        ReminderStats result = statsService.compute(repository.findAll(), LocalTime.now(clock));
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("total", result.total());
        body.put("earliest", format(result.earliest()));
        body.put("latest", format(result.latest()));
        body.put("next", nextResponse(result.next()));
        body.put("nextIsTomorrow", result.nextIsTomorrow());
        return body;
    }

    private static String format(LocalTime time) {
        return time == null ? null : time.format(TIME);
    }

    private static Map<String, Object> nextResponse(Reminder reminder) {
        if (reminder == null) {
            return null;
        }
        Map<String, Object> next = new LinkedHashMap<>();
        next.put("id", reminder.id());
        next.put("text", reminder.text());
        next.put("at", format(reminder.at()));
        return next;
    }
}
