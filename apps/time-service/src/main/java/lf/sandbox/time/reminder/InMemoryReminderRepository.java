package lf.sandbox.time.reminder;

import java.time.LocalTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryReminderRepository implements ReminderRepository {

    private static final int MAX_TEXT_LENGTH = 140;

    private final List<Reminder> reminders = new ArrayList<>();
    private long nextId = 1;

    public InMemoryReminderRepository() {
    }

    @Override
    public synchronized Reminder save(String text, LocalTime at) {
        if (text == null) {
            throw new IllegalArgumentException("text must not be null");
        }
        if (at == null) {
            throw new IllegalArgumentException("at must not be null");
        }
        String stripped = text.strip();
        if (stripped.isEmpty() || stripped.length() > MAX_TEXT_LENGTH) {
            throw new IllegalArgumentException("text must have 1 to 140 characters");
        }
        Reminder reminder = new Reminder(nextId, stripped, at.truncatedTo(ChronoUnit.SECONDS));
        reminders.add(reminder);
        nextId++;
        return reminder;
    }

    @Override
    public synchronized List<Reminder> findAll() {
        return List.copyOf(reminders);
    }

    @Override
    public synchronized Optional<Reminder> findById(long id) {
        for (Reminder reminder : reminders) {
            if (reminder.id() == id) {
                return Optional.of(reminder);
            }
        }
        return Optional.empty();
    }
}
