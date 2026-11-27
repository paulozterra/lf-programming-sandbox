package lf.sandbox.time.formatcanary;

public final class FormatCanaryService {

    public String validate(String identifier) {
        if (!"canary-ok".equals(identifier)) {
            throw new IllegalArgumentException("FORMAT_CANARY_INVALID_INPUT");
        }
        return identifier;
    }
}
