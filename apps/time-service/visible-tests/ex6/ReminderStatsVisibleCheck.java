import java.time.LocalTime;
import java.util.List;
import lf.sandbox.time.reminder.Reminder;
import lf.sandbox.time.reminder.ReminderStats;
import lf.sandbox.time.reminder.ReminderStatsService;

/** Visible check for REM-D2 (a few cases only). */
public class ReminderStatsVisibleCheck {
    static void check(boolean condition, String code) {
        if (!condition) {
            throw new AssertionError(code);
        }
    }

    public static void main(String[] args) {
        ReminderStatsService service = new ReminderStatsService();
        ReminderStats empty = service.compute(List.of(), LocalTime.NOON);
        check(empty.total() == 0 && empty.next() == null && !empty.nextIsTomorrow(), "VISIBLE_EMPTY");
        List<Reminder> list =
                List.of(
                        new Reminder(1, "a", LocalTime.of(9, 0)),
                        new Reminder(2, "b", LocalTime.of(14, 0)));
        ReminderStats stats = service.compute(list, LocalTime.of(10, 0));
        check(stats.total() == 2, "VISIBLE_TOTAL");
        check(stats.earliest().equals(LocalTime.of(9, 0)), "VISIBLE_EARLIEST");
        check(stats.next().id() == 2 && !stats.nextIsTomorrow(), "VISIBLE_NEXT");
        ReminderStats wrap = service.compute(list, LocalTime.of(20, 0));
        check(wrap.next().id() == 1 && wrap.nextIsTomorrow(), "VISIBLE_WRAP");
        System.out.println("EX6_VISIBLE_OK");
    }
}
