package lf.sandbox.time;

import java.time.Clock;
import java.time.DateTimeException;
import java.time.ZoneId;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfig {

    @Bean
    public Clock clock(@Value("${app.time.zone:America/Lima}") String zone) {
        try {
            return Clock.system(ZoneId.of(zone));
        } catch (DateTimeException e) {
            throw new IllegalStateException("Invalid app.time.zone value '" + zone + "'", e);
        }
    }
}
