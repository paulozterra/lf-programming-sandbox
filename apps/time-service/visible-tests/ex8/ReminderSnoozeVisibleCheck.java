import java.time.LocalTime;
import lf.sandbox.time.reminder.InMemoryReminderRepository;
import lf.sandbox.time.reminder.Reminder;

/** Visible check for REM-F1 (a few cases only). */
public class ReminderSnoozeVisibleCheck {
    static void check(boolean condition, String code) {
        if (!condition) {
            throw new AssertionError(code);
        }
    }

    public static void main(String[] args) {
        InMemoryReminderRepository repo = new InMemoryReminderRepository();
        Reminder water = repo.save("water", LocalTime.of(8, 0));
        Reminder snoozed = repo.snooze(water.id(), 30).orElseThrow();
        check(snoozed.id() == water.id(), "VISIBLE_SNOOZE_KEEPS_ID");
        check(snoozed.at().equals(LocalTime.of(8, 30)), "VISIBLE_SNOOZE_MOVES");
        check(snoozed.text().equals("water"), "VISIBLE_SNOOZE_KEEPS_TEXT");
        check(repo.snooze(99, 5).isEmpty(), "VISIBLE_SNOOZE_MISSING");
        boolean invalid = false;
        try {
            repo.snooze(water.id(), 0);
        } catch (IllegalArgumentException e) {
            invalid = true;
        }
        check(invalid, "VISIBLE_SNOOZE_RANGE");
        System.out.println("EX8_VISIBLE_OK");
    }
}
