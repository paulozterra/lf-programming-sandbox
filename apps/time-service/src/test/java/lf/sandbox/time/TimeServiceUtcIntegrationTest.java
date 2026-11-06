package lf.sandbox.time;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Clock;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = "app.time.zone=UTC")
@AutoConfigureMockMvc
class TimeServiceUtcIntegrationTest {

    @Autowired Clock clock;
    @Autowired MockMvc mvc;

    @Test
    void configuredZoneIsUtcAndEndpointUsesIt() throws Exception {
        assertThat(clock.getZone().getId()).isEqualTo("UTC");
        mvc.perform(get("/api/time"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.zone").value("UTC"))
                .andExpect(jsonPath("$.timestamp").value(org.hamcrest.Matchers.matchesPattern(
                        "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:Z|\\+00:00)$")));
    }
}
