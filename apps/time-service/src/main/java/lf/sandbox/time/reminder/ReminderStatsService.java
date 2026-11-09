package lf.sandbox.time.reminder;

import java.time.LocalTime;
import java.time.temporal.ChronoUnit;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ReminderStatsService {

    public ReminderStatsService() {}

    public ReminderStats compute(List<Reminder> reminders, LocalTime now) {
        if (reminders == null || now == null) {
            throw new IllegalArgumentException("reminders and now must not be null");
        }
        if (reminders.isEmpty()) {
            return new ReminderStats(0, null, null, null, false);
        }

        LocalTime reference = now.truncatedTo(ChronoUnit.SECONDS);
        LocalTime earliest = null;
        LocalTime latest = null;
        Reminder first = null;
        Reminder upcoming = null;

        for (Reminder reminder : reminders) {
            LocalTime at = reminder.at();
            if (earliest == null || at.isBefore(earliest)) {
                earliest = at;
            }
            if (latest == null || at.isAfter(latest)) {
                latest = at;
            }
            if (first == null || earlier(reminder, first)) {
                first = reminder;
            }
            if (!at.isBefore(reference)
                    && (upcoming == null || earlier(reminder, upcoming))) {
                upcoming = reminder;
            }
        }

        boolean tomorrow = upcoming == null;
        return new ReminderStats(
                reminders.size(), earliest, latest, tomorrow ? first : upcoming, tomorrow);
    }

    private static boolean earlier(Reminder left, Reminder right) {
        int comparison = left.at().compareTo(right.at());
        return comparison < 0 || (comparison == 0 && left.id() < right.id());
    }
}
