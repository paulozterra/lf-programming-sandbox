package lf.sandbox.time.reminder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.LocalTime;
import org.junit.jupiter.api.Test;

class ReminderRepositoryVisibleTest {

    @Test
    void savesSequentialIdsAndReturnsOrderedSnapshot() {
        ReminderRepository repository = new InMemoryReminderRepository();
        Reminder first = repository.save("uno", LocalTime.of(9, 30));
        Reminder second = repository.save("dos", LocalTime.of(10, 0));
        assertThat(first.id()).isEqualTo(1L);
        assertThat(second.id()).isEqualTo(2L);
        assertThat(repository.findAll()).containsExactly(first, second);
        assertThat(repository.findById(2L)).contains(second);
    }

    @Test
    void stripsTextAndTruncatesTimeToSeconds() {
        ReminderRepository repository = new InMemoryReminderRepository();
        Reminder stored = repository.save("  mañana  ", LocalTime.of(12, 20, 30, 123456789));
        assertThat(stored.text()).isEqualTo("mañana");
        assertThat(stored.at()).isEqualTo(LocalTime.of(12, 20, 30));
    }

    @Test
    void rejectsEmptyTextWithoutSaving() {
        ReminderRepository repository = new InMemoryReminderRepository();
        assertThatThrownBy(() -> repository.save("   ", LocalTime.NOON))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(repository.findAll()).isEmpty();
    }
}
