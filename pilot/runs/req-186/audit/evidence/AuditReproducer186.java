package lf.sandbox.time.reminder;

import java.time.*;
import java.util.*;
import lf.sandbox.time.auth.*;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

/** Audit reproducer for req-186 (commit 5b0430ef). Prints one JSON object per line. */
public class AuditReproducer186 {
    static class MutableClock extends Clock {
        Instant now = Instant.parse("2026-11-17T12:00:00Z");
        public ZoneId getZone() { return ZoneOffset.UTC; }
        public Clock withZone(ZoneId z) { return this; }
        public Instant instant() { return now; }
    }
    static String show(ResponseEntity<?> r) { return r.getStatusCode().value() + " " + r.getBody(); }
    static void out(String c, String k, Object v) {
        System.out.println("{\"case\":\"" + c + "\",\"" + k + "\":\"" + String.valueOf(v).replace("\"", "'") + "\"}");
    }
    public static void main(String[] a) {
        BCryptPasswordEncoder enc = new BCryptPasswordEncoder();
        MutableClock clock = new MutableClock();
        AuthUser user = new AuthUser("demo", enc.encode("pw"));
        AuthService auth = new AuthService(user, enc, clock, 5, 15, 30);
        InMemoryReminderRepository repo = new InMemoryReminderRepository();
        ReminderController c = new ReminderController(repo, auth);
        String bearer = "Bearer " + auth.login("demo", "pw").orElseThrow().token();

        // SESSION-REQUIRED: control — the list itself is protected.
        out("LIST_without_session", "response", show(c.listFiltered(null, null, null)));
        // defect — every other reminder endpoint works without any session.
        ResponseEntity<Object> created = c.create(new HashMap<>(Map.of("text", "anonimo", "at", "09:00:00", "priority", "HIGH")));
        out("CREATE_without_session", "response", show(created));
        long id = ((ReminderController.ReminderResponse) created.getBody()).id();
        out("GET_BY_ID_without_session", "response", show(c.get(String.valueOf(id))));
        out("SNOOZE_without_session", "response", show(c.snooze(String.valueOf(id), "5")));
        // owner scoping: what an anonymous caller created shows up in the user's list.
        out("LIST_with_session_includes_anonymous", "response", show(c.listFiltered(null, null, bearer)));
        out("DELETE_without_session", "response", show(c.delete(String.valueOf(id))));

        // PRIORITY-FILTER: control valid filter, defect body of the 400.
        c.create(new HashMap<>(Map.of("text", "alta", "at", "10:00:00", "priority", "HIGH")));
        c.create(new HashMap<>(Map.of("text", "baja", "at", "11:00:00", "priority", "LOW")));
        out("FILTER_HIGH_with_session", "response", show(c.listFiltered(null, "HIGH", bearer)));
        out("FILTER_invalid_with_session", "response", show(c.listFiltered(null, "URGENT", bearer)));

        // ERR: session expiry at thirty minutes (control).
        clock.now = clock.now.plus(Duration.ofMinutes(29));
        out("SESSION_at_29_min", "status", c.listFiltered(null, null, bearer).getStatusCode().value());
        clock.now = clock.now.plus(Duration.ofMinutes(1));
        out("SESSION_at_30_min", "response", show(c.listFiltered(null, null, bearer)));
        // ERR: generic error indistinguishable — compare failure bodies across endpoints.
        out("ERR_bodies", "list401|get404|create400", show(c.listFiltered(null, null, null)) + " | "
                + show(c.get("999")) + " | " + show(c.create(new HashMap<>(Map.of("text", "x")))));
    }
}
