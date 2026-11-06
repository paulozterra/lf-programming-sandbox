package lf.sandbox.time;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(TimeController.class)
@Import(TimeControllerWebMvcTest.FixedClock.class)
class TimeControllerWebMvcTest {

    @Autowired MockMvc mvc;

    @Test
    void exactJsonWithFixedLimaClock() throws Exception {
        mvc.perform(get("/api/time"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(content().json("""
                    {"time":"09:15:09","timestamp":"2026-11-06T09:15:09-05:00","zone":"America/Lima"}
                    """, true));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClock {
        @Bean
        Clock clock() {
            return Clock.fixed(Instant.parse("2026-11-06T14:15:09Z"), ZoneId.of("America/Lima"));
        }
    }
}
