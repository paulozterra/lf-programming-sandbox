package lf.sandbox.time;

import java.time.Clock;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TimeController {

    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm:ss");

    private final Clock clock;

    public TimeController(Clock clock) {
        this.clock = clock;
    }

    @GetMapping("/api/time")
    public TimeResponse time() {
        ZonedDateTime now = ZonedDateTime.now(clock).truncatedTo(ChronoUnit.SECONDS);
        return new TimeResponse(
                now.format(TIME),
                now.toOffsetDateTime().format(DateTimeFormatter.ISO_OFFSET_DATE_TIME),
                now.getZone().getId());
    }

    public record TimeResponse(String time, String timestamp, String zone) {}
}
