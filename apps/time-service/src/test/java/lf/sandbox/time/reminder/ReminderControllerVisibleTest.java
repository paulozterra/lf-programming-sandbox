package lf.sandbox.time.reminder;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assumptions;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/**
 * This protected visible test is staged in PR 2, after ex4a has passed.
 * The controller belongs exclusively to ex4b. Skip, rather than fail,
 * while the lot B controller class is absent from the real base commit.
 * It automatically executes when ex4b supplies ReminderController.
 */
@SpringBootTest
@AutoConfigureMockMvc
class ReminderControllerVisibleTest {

    @Autowired MockMvc mvc;

    @BeforeEach
    void requireLotBController() {
        boolean controllerExists;
        try {
            Class.forName("lf.sandbox.time.reminder.ReminderController");
            controllerExists = true;
        } catch (ClassNotFoundException e) {
            controllerExists = false;
        }
        Assumptions.assumeTrue(controllerExists, "REM-B controller is created by ex4b only");
    }

    @Test
    void postCreatedAndGetOrderedList() throws Exception {
        mvc.perform(post("/api/reminders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"  take a break  \",\"at\":\"13:20:30\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", org.hamcrest.Matchers.matchesPattern("/api/reminders/\\d+")))
                .andExpect(jsonPath("$.text").value("take a break"))
                .andExpect(jsonPath("$.at").value("13:20:30"))
                .andExpect(jsonPath("$.*", hasSize(3)));

        mvc.perform(get("/api/reminders"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", org.hamcrest.Matchers.hasSize(org.hamcrest.Matchers.greaterThanOrEqualTo(1))))
                .andExpect(jsonPath("$[0].text").value("take a break"));
    }

    @Test
    void invalidPostReturnsBadRequest() throws Exception {
        mvc.perform(post("/api/reminders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"at\":\"13:20:30\"}"))
                .andExpect(status().isBadRequest());
    }
}
