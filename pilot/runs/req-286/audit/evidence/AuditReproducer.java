package lf.sandbox.time.auth;

import java.time.Clock;
import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

/** Audit reproducer for req-286 (commit ae20aeb). Prints JSON lines only. */
public class AuditReproducer {
    static final String EMAIL = "demo@sandbox.test", PASS = "correct-horse";
    static BCryptPasswordEncoder enc = new BCryptPasswordEncoder();
    static String hash = enc.encode(PASS);

    static AuthController fresh() {
        AuthUser user = new AuthUser("demo", hash);
        return new AuthController(new AuthService(user, enc, Clock.systemUTC(), 5, 15, 30), user, enc, EMAIL);
    }
    static ResponseEntity<?> call(AuthController c, String email, String pw) {
        Map<String, Object> b = new HashMap<>(); b.put("email", email); b.put("password", pw); return c.login(b);
    }
    static String body(ResponseEntity<?> r) { return r.getStatusCode().value() + " " + r.getBody(); }
    static double avgMs(AuthController c, String email, String pw, int n) {
        call(c, email, pw); long t = 0;
        for (int i = 0; i < n; i++) { long s = System.nanoTime(); call(c, email, pw); t += System.nanoTime() - s; }
        return t / 1e6 / n;
    }
    public static void main(String[] a) {
        // F-RATE-LIMITED-UNREACHABLE: positive = lock reached, observe 6th response
        AuthController c = fresh();
        for (int i = 0; i < 5; i++) call(c, EMAIL, "wrong");
        System.out.println("{\"case\":\"RATE_after_5_failures\",\"response\":\"" + body(call(c, EMAIL, PASS)) + "\"}");
        // negative control: unlocked fresh controller, correct password authenticates
        System.out.println("{\"case\":\"RATE_control_fresh_correct\",\"status\":" + call(fresh(), EMAIL, PASS).getStatusCode().value() + "}");
        // F-AUTH-TIMING-LOCKED: locked real account vs unknown email
        double locked = avgMs(c, EMAIL, "wrong", 20);
        double unknown = avgMs(c, "nobody@sandbox.test", "wrong", 20);
        double blank = avgMs(fresh(), EMAIL, "   ", 20);
        System.out.printf(Locale.ROOT, "{\"case\":\"TIMING\",\"locked_real_ms\":%.3f,\"unknown_email_ms\":%.3f,\"blank_password_real_ms\":%.3f}%n", locked, unknown, blank);
        // negative control: unlocked wrong password vs unknown email (both hash)
        double wrong = avgMs(fresh(), EMAIL, "wrong", 4);
        System.out.printf(Locale.ROOT, "{\"case\":\"TIMING_control_unlocked_wrong_ms\",\"value\":%.3f}%n", wrong);
        // F-ERROR-TRACE-MISSING: failing dependency -> 503, inspect envelope
        AuthUser user = new AuthUser("demo", hash);
        AuthService broken = new AuthService(user, enc, Clock.systemUTC(), 5, 15, 30) {
            @Override public synchronized Optional<LoginResult> login(String u, String p) { throw new IllegalStateException("db down"); }
        };
        ResponseEntity<?> r = new AuthController(broken, user, enc, EMAIL).login(Map.of("email", EMAIL, "password", PASS));
        System.out.println("{\"case\":\"TRACE_on_503\",\"response\":\"" + body(r) + "\",\"trace_code_in_body\":" + String.valueOf(r.getBody()).contains("SBX-2") + "}");
    }
}
