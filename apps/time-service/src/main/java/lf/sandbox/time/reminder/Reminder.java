package lf.sandbox.time.reminder;

import java.time.LocalTime;

public record Reminder(long id, String text, LocalTime at, String priority) {

    public Reminder(long id, String text, LocalTime at) {
        this(id, text, at, "MEDIUM");
    }

    public Reminder {
        if (priority == null || !(priority.equals("HIGH") || priority.equals("MEDIUM") || priority.equals("LOW"))) {
            throw new IllegalArgumentException("invalid priority");
        }
    }
}
