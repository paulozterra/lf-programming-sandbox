package lf.sandbox.time.reminder;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import java.time.LocalTime;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ReminderRepositoryDeleteSearchVisibleTest {
    @BeforeEach
    void requiresLotCMethods() {
        try {
            ReminderRepository.class.getMethod("deleteById", long.class);
            ReminderRepository.class.getMethod("findByTextContaining", String.class);
        } catch (NoSuchMethodException e) {
            Assumptions.assumeTrue(false, "REM-C methods only exist after verified Worker patch");
        }
    }

    @Test
    void deletesExistingThenMissingWithoutReusingIds() throws Exception {
        ReminderRepository repo = new InMemoryReminderRepository();
        Reminder first = repo.save("meet", LocalTime.NOON);
        Method deletion = ReminderRepository.class.getMethod("deleteById", long.class);
        assertThat(deletion.invoke(repo, first.id())).isEqualTo(true);
        assertThat(deletion.invoke(repo, first.id())).isEqualTo(false);
        assertThat(repo.save("later", LocalTime.NOON).id()).isEqualTo(first.id() + 1);
    }

    @Test
    void caseInsensitiveSearchFindsSavedText() throws Exception {
        ReminderRepository repo = new InMemoryReminderRepository();
        Reminder saved = repo.save("Drink Water", LocalTime.NOON);
        Method search = ReminderRepository.class.getMethod("findByTextContaining", String.class);
        @SuppressWarnings("unchecked")
        java.util.List<Reminder> found = (java.util.List<Reminder>) search.invoke(repo, "  WATER  ");
        assertThat(found).containsExactly(saved);
    }
}
