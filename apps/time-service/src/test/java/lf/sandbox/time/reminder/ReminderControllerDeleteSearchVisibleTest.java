package lf.sandbox.time.reminder;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.lang.reflect.Method;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.DeleteMapping;

@SpringBootTest
@AutoConfigureMockMvc
class ReminderControllerDeleteSearchVisibleTest {
    @Autowired MockMvc mvc;

    @BeforeEach
    void requiresLotCController() {
        boolean hasDelete = false;
        for (Method m : ReminderController.class.getDeclaredMethods()) {
            if (m.isAnnotationPresent(DeleteMapping.class)) {
                hasDelete = true;
                break;
            }
        }
        Assumptions.assumeTrue(hasDelete, "REM-C API only exists after verified Worker patch");
    }

    @Test
    void deleteExistingThenReturnsNotFound() throws Exception {
        String location = mvc.perform(post("/api/reminders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"delete me\",\"at\":\"14:20:30\"}"))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getHeader("Location");
        org.assertj.core.api.Assertions.assertThat(location).isNotBlank();
        mvc.perform(delete(location)).andExpect(status().isNoContent());
        mvc.perform(delete(location)).andExpect(status().isNotFound());
    }

    @Test
    void getQueryFiltersRecords() throws Exception {
        mvc.perform(post("/api/reminders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"UniqueEx5Needle\",\"at\":\"14:20:30\"}"))
                .andExpect(status().isCreated());
        mvc.perform(get("/api/reminders").param("q", "needLE"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].text").value("UniqueEx5Needle"));
    }
}
