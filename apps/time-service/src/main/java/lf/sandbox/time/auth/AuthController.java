package lf.sandbox.time.auth;

import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;
import lf.sandbox.time.sbxb2blogin.SbxB2bLoginService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthController {

    private static final Map<String, String> GENERIC_ERROR = Map.of("error", "SBX-E-GENERIC");
    private static final Pattern EMAIL_PATTERN =
            Pattern.compile("^[^@\\s.]+(?:\\.[^@\\s.]+)*@[^@\\s.]+(?:\\.[^@\\s.]+)+$");

    private final AuthService authService;
    private final AuthUser authUser;
    private final BCryptPasswordEncoder passwordEncoder;
    private final String demoEmail;
    private SbxB2bLoginService b2bService;

    public AuthController(
            AuthService authService,
            AuthUser authUser,
            BCryptPasswordEncoder passwordEncoder,
            @Value("${app.auth.b2b-demo-email:demo@sandbox.test}") String demoEmail) {
        this.authService = authService;
        this.authUser = authUser;
        this.passwordEncoder = passwordEncoder;
        this.demoEmail = demoEmail;
    }

    @Autowired(required = false)
    public void setB2bService(SbxB2bLoginService b2bService) {
        this.b2bService = b2bService;
    }

    @PostMapping("/api/auth/login")
    public ResponseEntity<?> login(@RequestBody(required = false) Map<String, Object> body) {
        if (body != null && body.containsKey("email")) {
            return loginWithEmail(body);
        }
        if (body == null
                || !(body.get("username") instanceof String username)
                || !(body.get("password") instanceof String password)) {
            return unauthorized();
        }
        return authService
                .login(username, password)
                .<ResponseEntity<?>>map(login -> ResponseEntity.ok(
                        new LoginResponse(login.token(), login.expiresAt().toString())))
                .orElseGet(AuthController::unauthorized);
    }

    private ResponseEntity<?> loginWithEmail(Map<String, Object> body) {
        String correlationId = UUID.randomUUID().toString();
        if (!(body.get("email") instanceof String suppliedEmail)
                || !(body.get("password") instanceof String password)) {
            return invalidCredentials(correlationId);
        }
        String email = suppliedEmail.strip();
        if (password.isEmpty()) {
            return invalidCredentials(correlationId);
        }
        try {
            if (b2bService != null) {
                SbxB2bLoginService.B2bAuthOutcome result = b2bService.authenticateB2b(email, password, correlationId);
                if ("AUTHENTICATED".equals(result.outcome())) {
                    return ResponseEntity.ok(new B2bLoginResponse("AUTHENTICATED", correlationId, result.token()));
                }
                if ("RATE_LIMITED".equals(result.outcome())) {
                    return ResponseEntity.status(429)
                            .body(new B2bLoginFailure("RATE_LIMITED", correlationId, "SBX-B2B-E-RATE"));
                }
                return invalidCredentials(correlationId);
            }
            boolean emailMatches =
                    email.length() <= 254 && EMAIL_PATTERN.matcher(email).matches() && matchesConfiguredEmail(email);
            if (!emailMatches) {
                // Execute the same password-hash work without creating a session.
                passwordEncoder.matches(password, authUser.passwordBcrypt());
                return invalidCredentials(correlationId);
            }
            return authService
                    .login(authUser.username(), password)
                    .<ResponseEntity<?>>map(login ->
                            ResponseEntity.ok(new B2bLoginResponse("AUTHENTICATED", correlationId, login.token())))
                    .orElseGet(() -> invalidCredentials(correlationId));
        } catch (RuntimeException exception) {
            return ResponseEntity.status(503)
                    .body(new B2bLoginFailure("SERVICE_UNAVAILABLE", correlationId, "SBX-B2B-E-NETWORK"));
        }
    }

    private boolean matchesConfiguredEmail(String email) {
        int at = email.lastIndexOf('@');
        int configuredAt = demoEmail.lastIndexOf('@');
        return at > 0
                && configuredAt > 0
                && email.substring(0, at).equals(demoEmail.substring(0, configuredAt))
                && email.substring(at + 1).equalsIgnoreCase(demoEmail.substring(configuredAt + 1));
    }

    private static ResponseEntity<?> invalidCredentials(String correlationId) {
        return ResponseEntity.status(401)
                .body(new B2bLoginFailure("INVALID_CREDENTIALS", correlationId, "SBX-B2B-E-CREDENTIALS"));
    }

    @GetMapping("/api/auth/session")
    public ResponseEntity<?> session(@RequestHeader(name = "Authorization", required = false) String authorization) {
        if (b2bService != null) {
            var persistent = b2bService.checkB2bSession(authorization);
            if (persistent.isPresent()) {
                return ResponseEntity.ok(new SessionResponse(persistent.get()));
            }
        }
        return authService
                .session(authorization)
                .<ResponseEntity<?>>map(username -> ResponseEntity.ok(new SessionResponse(username)))
                .orElseGet(AuthController::unauthorized);
    }

    @PostMapping("/api/auth/logout")
    public ResponseEntity<?> logout(@RequestHeader(name = "Authorization", required = false) String authorization) {
        return b2bService != null && b2bService.logout(authorization)
                ? ResponseEntity.noContent().build()
                : unauthorized();
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> invalidLoginBody() {
        return ResponseEntity.status(401).body(GENERIC_ERROR);
    }

    private static ResponseEntity<?> unauthorized() {
        return ResponseEntity.status(401).body(GENERIC_ERROR);
    }

    public record LoginResponse(String token, String expiresAt) {}

    public record SessionResponse(String username) {}

    public record B2bLoginResponse(String outcome, String correlation_id, String token) {}

    public record B2bLoginFailure(String outcome, String correlation_id, String error_code) {}
}
