package lf.sandbox.time.reminder;

import java.time.LocalTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryReminderRepository implements ReminderRepository {

    private static final int MAX_TEXT_LENGTH = 140;

    private final List<Reminder> reminders = new ArrayList<>();
    private long nextId = 1;

    public InMemoryReminderRepository() {}

    private static String validatedText(String text) {
        if (text == null) {
            throw new IllegalArgumentException("text must not be null");
        }
        String stripped = text.strip();
        if (stripped.isEmpty() || stripped.length() > MAX_TEXT_LENGTH) {
            throw new IllegalArgumentException("text must have 1 to 140 characters");
        }
        return stripped;
    }

    private static LocalTime validatedTime(LocalTime at) {
        if (at == null) {
            throw new IllegalArgumentException("at must not be null");
        }
        return at.truncatedTo(ChronoUnit.SECONDS);
    }

    private static String validatedPriority(String priority) {
        if (priority == null || !(priority.equals("HIGH") || priority.equals("MEDIUM") || priority.equals("LOW"))) {
            throw new IllegalArgumentException("invalid priority");
        }
        return priority;
    }

    private boolean duplicates(long excludedId, String text, LocalTime at) {
        String key = text.toLowerCase(Locale.ROOT);
        for (Reminder existing : reminders) {
            if (existing.id() != excludedId
                    && existing.at().equals(at)
                    && existing.text().toLowerCase(Locale.ROOT).equals(key)) {
                return true;
            }
        }
        return false;
    }

    @Override
    public synchronized Reminder save(String text, LocalTime at) {
        return save(text, at, "MEDIUM");
    }

    @Override
    public synchronized Reminder save(String text, LocalTime at, String priority) {
        String normalizedText = validatedText(text);
        LocalTime normalizedTime = validatedTime(at);
        String normalizedPriority = validatedPriority(priority);
        if (duplicates(-1, normalizedText, normalizedTime)) {
            throw new IllegalStateException("duplicate reminder");
        }
        Reminder reminder = new Reminder(nextId, normalizedText, normalizedTime, normalizedPriority);
        reminders.add(reminder);
        nextId++;
        return reminder;
    }

    @Override
    public synchronized Optional<Reminder> update(long id, String text, LocalTime at) {
        String normalizedText = validatedText(text);
        LocalTime normalizedTime = validatedTime(at);
        return updateValidated(id, normalizedText, normalizedTime, null);
    }

    @Override
    public synchronized Optional<Reminder> update(long id, String text, LocalTime at, String priority) {
        String normalizedText = validatedText(text);
        LocalTime normalizedTime = validatedTime(at);
        return updateValidated(id, normalizedText, normalizedTime, validatedPriority(priority));
    }

    private Optional<Reminder> updateValidated(long id, String text, LocalTime at, String priority) {
        for (int i = 0; i < reminders.size(); i++) {
            Reminder existing = reminders.get(i);
            if (existing.id() == id) {
                if (duplicates(id, text, at)) {
                    throw new IllegalStateException("duplicate reminder");
                }
                Reminder updated = new Reminder(id, text, at, priority == null ? existing.priority() : priority);
                reminders.set(i, updated);
                return Optional.of(updated);
            }
        }
        return Optional.empty();
    }

    @Override
    public synchronized Optional<Reminder> snooze(long id, int minutes) {
        if (minutes < 1 || minutes > 1440) {
            throw new IllegalArgumentException("minutes must be between 1 and 1440");
        }
        for (int i = 0; i < reminders.size(); i++) {
            Reminder existing = reminders.get(i);
            if (existing.id() == id) {
                LocalTime newTime = existing.at().plusMinutes(minutes);
                if (duplicates(id, existing.text(), newTime)) {
                    throw new IllegalStateException("duplicate reminder");
                }
                Reminder updated = new Reminder(id, existing.text(), newTime, existing.priority());
                reminders.set(i, updated);
                return Optional.of(updated);
            }
        }
        return Optional.empty();
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

    @Override
    public synchronized boolean deleteById(long id) {
        return reminders.removeIf(r -> r.id() == id);
    }

    @Override
    public synchronized List<Reminder> findByTextContaining(String query) {
        if (query == null) {
            throw new IllegalArgumentException("query must not be null");
        }
        String needle = query.strip().toLowerCase(Locale.ROOT);
        List<Reminder> result = new ArrayList<>();
        for (Reminder reminder : reminders) {
            if (reminder.text().toLowerCase(Locale.ROOT).contains(needle)) {
                result.add(reminder);
            }
        }
        return List.copyOf(result);
    }
}
