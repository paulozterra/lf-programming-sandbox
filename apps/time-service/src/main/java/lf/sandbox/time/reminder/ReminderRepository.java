package lf.sandbox.time.reminder;

import java.time.LocalTime;
import java.util.List;
import java.util.Optional;

public interface ReminderRepository {
    Reminder save(String text, LocalTime at);

    List<Reminder> findAll();

    Optional<Reminder> findById(long id);

    boolean deleteById(long id);

    List<Reminder> findByTextContaining(String query);

    Optional<Reminder> update(long id, String text, LocalTime at);
}
