package lf.sandbox.time.auth;

import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthService {

    private static final int TOKEN_BYTES = 32;

    private final AuthUser user;
    private final BCryptPasswordEncoder passwordEncoder;
    private final Clock clock;
    private final int maxFailedAttempts;
    private final int lockMinutes;
    private final int sessionMinutes;
    private final SecureRandom random = new SecureRandom();
    private final Map<String, Session> sessions = new HashMap<>();

    private int consecutiveFailures;
    private Instant lockedUntil;

    public AuthService(
            AuthUser user,
            BCryptPasswordEncoder passwordEncoder,
            Clock clock,
            @Value("${app.auth.failed-attempts:5}") int maxFailedAttempts,
            @Value("${app.auth.lock-minutes:15}") int lockMinutes,
            @Value("${app.auth.session-minutes:30}") int sessionMinutes) {
        if (maxFailedAttempts <= 0 || lockMinutes <= 0 || sessionMinutes <= 0) {
            throw new IllegalArgumentException("Invalid authentication policy");
        }
        this.user = user;
        this.passwordEncoder = passwordEncoder;
        this.clock = clock;
        this.maxFailedAttempts = maxFailedAttempts;
        this.lockMinutes = lockMinutes;
        this.sessionMinutes = sessionMinutes;
    }

    public synchronized Optional<LoginResult> login(String username, String password) {
        if (username == null || username.isBlank() || password == null || password.isBlank()) {
            return Optional.empty();
        }

        Instant now = clock.instant();
        if (!user.username().equals(username)) {
            return Optional.empty();
        }
        if (lockedUntil != null) {
            if (now.isBefore(lockedUntil)) {
                return Optional.empty();
            }
            lockedUntil = null;
            consecutiveFailures = 0;
        }

        if (!passwordEncoder.matches(password, user.passwordBcrypt())) {
            consecutiveFailures++;
            if (consecutiveFailures >= maxFailedAttempts) {
                lockedUntil = now.plus(lockMinutes, ChronoUnit.MINUTES);
            }
            return Optional.empty();
        }

        consecutiveFailures = 0;
        byte[] randomBytes = new byte[TOKEN_BYTES];
        random.nextBytes(randomBytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(randomBytes);
        Instant expiresAt = now.plus(sessionMinutes, ChronoUnit.MINUTES);
        sessions.put(token, new Session(user.username(), expiresAt));
        return Optional.of(new LoginResult(token, expiresAt));
    }

    public synchronized Optional<String> session(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            return Optional.empty();
        }
        String token = authorization.substring("Bearer ".length());
        if (token.isBlank()) {
            return Optional.empty();
        }

        Session stored = sessions.get(token);
        if (stored == null) {
            return Optional.empty();
        }
        if (!clock.instant().isBefore(stored.expiresAt())) {
            sessions.remove(token);
            return Optional.empty();
        }
        return Optional.of(stored.username());
    }

    public record LoginResult(String token, Instant expiresAt) {}

    private record Session(String username, Instant expiresAt) {}
}
