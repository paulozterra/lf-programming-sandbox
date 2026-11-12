package lf.sandbox.time.auth;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthController {

    private static final Map<String, String> GENERIC_ERROR = Map.of("error", "SBX-E-GENERIC");

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/api/auth/login")
    public ResponseEntity<?> login(@RequestBody(required = false) Map<String, Object> body) {
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

    @GetMapping("/api/auth/session")
    public ResponseEntity<?> session(@RequestHeader(name = "Authorization", required = false) String authorization) {
        return authService
                .session(authorization)
                .<ResponseEntity<?>>map(username -> ResponseEntity.ok(new SessionResponse(username)))
                .orElseGet(AuthController::unauthorized);
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
}
