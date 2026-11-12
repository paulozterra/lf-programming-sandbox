package lf.sandbox.time.auth;

public record AuthUser(String username, String passwordBcrypt) {

    public AuthUser {
        if (username == null || username.isBlank() || passwordBcrypt == null || passwordBcrypt.isBlank()) {
            throw new IllegalArgumentException("Invalid configured authentication user");
        }
    }
}
