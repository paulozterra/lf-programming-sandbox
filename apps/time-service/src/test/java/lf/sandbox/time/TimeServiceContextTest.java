package lf.sandbox.time;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class TimeServiceContextTest {
    @Autowired Clock clock;

    @Test
    void contextLoadsWithDefaultZone() {
        assertThat(clock.getZone().getId()).isEqualTo("America/Lima");
    }
}
