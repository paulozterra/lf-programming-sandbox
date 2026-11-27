package lf.sandbox.time.sbxb2blogin;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import lf.sandbox.time.auth.AuthUser;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SbxB2bLoginService {
    private final JdbcTemplate jdbc;
    private final BCryptPasswordEncoder encoder;
    private final Clock clock;
    private final AuthUser demo;
    private final String demoEmail;
    private final int maxFailures;
    private final int lockMinutes;
    private final int sessionMinutes;
    private final SecureRandom random = new SecureRandom();

    public SbxB2bLoginService(
            JdbcTemplate jdbc,
            BCryptPasswordEncoder encoder,
            Clock clock,
            AuthUser demo,
            @Value("${app.auth.b2b-demo-email:demo@sandbox.test}") String demoEmail,
            @Value("${app.auth.failed-attempts:5}") int maxFailures,
            @Value("${app.auth.lock-minutes:15}") int lockMinutes,
            @Value("${app.auth.session-minutes:30}") int sessionMinutes) {
        if (maxFailures <= 0 || lockMinutes <= 0 || sessionMinutes <= 0) {
            throw new IllegalArgumentException("Invalid authentication policy");
        }
        this.jdbc = jdbc;
        this.encoder = encoder;
        this.clock = clock;
        this.demo = demo;
        this.demoEmail = demoEmail;
        this.maxFailures = maxFailures;
        this.lockMinutes = lockMinutes;
        this.sessionMinutes = sessionMinutes;
    }

    @Transactional
    public B2bAuthOutcome authenticateB2b(String email, String password, String correlationId) {
        String normalized = email.strip().toLowerCase(Locale.ROOT);
        jdbc.update(
                "INSERT INTO sbx_b2b_accounts (email, password_hash, company_code, profile, status) "
                        + "VALUES (?, ?, 'DEMO', 'SBX_B2B_OPERADOR', 'ACTIVE') ON CONFLICT DO NOTHING",
                demoEmail.strip(),
                demo.passwordBcrypt());
        Instant now = clock.instant();
        List<Account> accounts = jdbc.query(
                "SELECT id, password_hash, status FROM sbx_b2b_accounts WHERE lower(email) = ?",
                (rs, i) -> new Account(rs.getLong("id"), rs.getString("password_hash"), rs.getString("status")),
                normalized);
        Account account = accounts.isEmpty() ? null : accounts.get(0);
        Long accountId = account == null ? null : account.id();
        Long failures = jdbc.queryForObject(
                "SELECT count(*) FROM sbx_b2b_login_attempts WHERE email_normalized = ? "
                        + "AND outcome = 'INVALID_CREDENTIALS' AND created_at > ?",
                Long.class,
                normalized,
                java.sql.Timestamp.from(now.minus(lockMinutes, ChronoUnit.MINUTES)));
        if (failures != null && failures >= maxFailures) {
            recordFailure(accountId, normalized, "RATE_LIMITED", correlationId, now);
            return new B2bAuthOutcome("RATE_LIMITED", null);
        }
        boolean valid = encoder.matches(password, account == null ? demo.passwordBcrypt() : account.passwordHash());
        if (!valid || account == null || !"ACTIVE".equals(account.status())) {
            recordFailure(accountId, normalized, "INVALID_CREDENTIALS", correlationId, now);
            return new B2bAuthOutcome("INVALID_CREDENTIALS", null);
        }
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        Instant expires = now.plus(sessionMinutes, ChronoUnit.MINUTES);
        jdbc.update(
                "INSERT INTO sbx_b2b_sessions (account_id, token_hash, created_at, last_seen_at, expires_at) "
                        + "VALUES (?, ?, ?, ?, ?)",
                account.id(),
                digest(token),
                java.sql.Timestamp.from(now),
                java.sql.Timestamp.from(now),
                java.sql.Timestamp.from(expires));
        return new B2bAuthOutcome("AUTHENTICATED", token);
    }

    @Transactional
    public Optional<String> checkB2bSession(String authorization) {
        String token = bearer(authorization);
        if (token == null) {
            return Optional.empty();
        }
        Instant now = clock.instant();
        List<String> accounts = jdbc.query(
                "SELECT a.email FROM sbx_b2b_sessions s JOIN sbx_b2b_accounts a ON a.id = s.account_id "
                        + "WHERE s.token_hash = ? AND s.revoked_at IS NULL AND s.expires_at > ? "
                        + "AND s.last_seen_at > ? AND a.status = 'ACTIVE'",
                (rs, i) -> rs.getString(1),
                digest(token),
                java.sql.Timestamp.from(now),
                java.sql.Timestamp.from(now.minus(sessionMinutes, ChronoUnit.MINUTES)));
        if (accounts.isEmpty()) {
            return Optional.empty();
        }
        jdbc.update(
                "UPDATE sbx_b2b_sessions SET last_seen_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                java.sql.Timestamp.from(now),
                digest(token));
        return Optional.of(accounts.get(0));
    }

    @Transactional
    public boolean logout(String authorization) {
        String token = bearer(authorization);
        if (token == null) {
            return false;
        }
        Instant now = clock.instant();
        return jdbc.update(
                        "UPDATE sbx_b2b_sessions SET revoked_at = ? "
                                + "WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?",
                        java.sql.Timestamp.from(now),
                        digest(token),
                        java.sql.Timestamp.from(now))
                == 1;
    }

    private void recordFailure(Long accountId, String email, String outcome, String correlationId, Instant now) {
        jdbc.update(
                "INSERT INTO sbx_b2b_login_attempts "
                        + "(account_id, email_normalized, outcome, correlation_id, created_at) VALUES (?, ?, ?, ?, ?)",
                accountId,
                email,
                outcome,
                correlationId,
                java.sql.Timestamp.from(now));
    }

    private static String bearer(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            return null;
        }
        String token = authorization.substring(7);
        return token.isBlank() ? null : token;
    }

    private static String digest(String token) {
        try {
            return HexFormat.of()
                    .formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }

    private record Account(long id, String passwordHash, String status) {}

    public record B2bAuthOutcome(String outcome, String token) {}
}
