package lf.sandbox.time.reminder;

import java.time.LocalTime;

public record Reminder(long id, String text, LocalTime at) {
}
