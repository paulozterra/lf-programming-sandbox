package lf.sandbox.time.reminder;

import java.time.LocalTime;

public record ReminderStats(int total, LocalTime earliest, LocalTime latest, Reminder next, boolean nextIsTomorrow) {}
