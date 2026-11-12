package lf.sandbox.time.auth;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

@Configuration(proxyBeanMethods = false)
public class AuthConfiguration {

    @Bean
    public BCryptPasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public AuthUser authUser(
            @Value("${app.auth.default-username}") String username,
            @Value("${app.auth.default-password-bcrypt}") String passwordBcrypt) {
        return new AuthUser(username, passwordBcrypt);
    }
}
