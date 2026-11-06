package lf.sandbox.time.reminder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.LocalTime;
import org.junit.jupiter.api.Test;

class ReminderRepositoryVisibleTest {

    @Test
    void idsStartAtOneAndIncrease() {
        ReminderRepository repository = new InMemoryReminderRepository();
        assertThat(repository.save("first", LocalTime.of(9, 0)).id()).isEqualTo(1L);
        assertThat(repository.save("second", LocalTime.of(10, 0)).id()).isEqualTo(2L);
    }

    @Test
    void stripsTextAndTruncatesSeconds() {
        ReminderRepository repository = new InMemoryReminderRepository();
        Reminder saved = repository.save("  drink water  ", LocalTime.of(14, 20, 30, 987_000_000));
        assertThat(saved.text()).isEqualTo("drink water");
        assertThat(saved.at()).isEqualTo(LocalTime.of(14, 20, 30));
    }

    @Test
    void findAllIsOrderedAndUnmodifiable() {
        ReminderRepository repository = new InMemoryReminderRepository();
        Reminder first = repository.save("one", LocalTime.NOON);
        Reminder second = repository.save("two", LocalTime.NOON);
        assertThat(repository.findAll()).extracting(Reminder::id).containsExactly(first.id(), second.id());
        assertThatThrownBy(() -> repository.findAll().clear())
                .isInstanceOf(UnsupportedOperationException.class);
    }

    @Test
    void blankTextRejectedWithoutSaving() {
        ReminderRepository repository = new InMemoryReminderRepository();
        assertThatThrownBy(() -> repository.save("   ", LocalTime.NOON))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(repository.findAll()).isEmpty();
    }
}
