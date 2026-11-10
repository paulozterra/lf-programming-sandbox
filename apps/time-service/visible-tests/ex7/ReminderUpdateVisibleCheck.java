import java.time.LocalTime;
import java.util.Optional;
import lf.sandbox.time.reminder.InMemoryReminderRepository;
import lf.sandbox.time.reminder.Reminder;

/** Visible check for REM-E1 and REM-E2 (a few cases only). */
public class ReminderUpdateVisibleCheck {
    static void check(boolean condition, String code) {
        if (!condition) {
            throw new AssertionError(code);
        }
    }

    public static void main(String[] args) {
        InMemoryReminderRepository repo = new InMemoryReminderRepository();
        Reminder first = repo.save("water", LocalTime.of(8, 0));
        repo.save("gym", LocalTime.of(18, 0));
        Optional<Reminder> updated = repo.update(first.id(), " tea ", LocalTime.of(9, 0));
        check(updated.isPresent(), "VISIBLE_UPDATE_PRESENT");
        check(updated.get().id() == first.id(), "VISIBLE_UPDATE_KEEPS_ID");
        check(updated.get().text().equals("tea"), "VISIBLE_UPDATE_STRIP");
        check(repo.update(99, "x", LocalTime.NOON).isEmpty(), "VISIBLE_UPDATE_MISSING");
        boolean duplicate = false;
        try {
            repo.save("GYM", LocalTime.of(18, 0));
        } catch (IllegalStateException e) {
            duplicate = true;
        }
        check(duplicate, "VISIBLE_DUPLICATE_SAVE");
        System.out.println("EX7_VISIBLE_OK");
    }
}
