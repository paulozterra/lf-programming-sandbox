# TIME_SERVICE_SPEC — LF Worker pilot exercise-3

**Status:** NORMATIVE / SANDBOX-ONLY. **Owner:** Paulo. **Holdout:** external, unpublished, SHA-256 pending Claude.
**Reference dependency:** `backend/pom.xml` (read-only), Spring Boot parent `4.1.1`. 
**New project root:** `apps/time-service/`. Do not edit `backend/`, `vendor/`, previous exercises, this specification, or visible tests.

This specification is authoritative for the generated solution. The specification's SHA-256 is pinned separately in `pilot/worker_v08/tasks.json` and checked before execution. Do not insert an alleged self-hash into this file.

## TIME-01 — Independent Maven application
Create `apps/time-service/pom.xml` and application files beneath `apps/time-service/src/main/**` from scratch. Use `org.springframework.boot:spring-boot-starter-parent:4.1.1`, `java.version=21`, `groupId=lf.sandbox`, `artifactId=time-service`, and Java package `lf.sandbox.time`. Produce an executable Spring Boot JAR via `spring-boot-maven-plugin`. Use the Boot 4 MVC starter `spring-boot-starter-webmvc` and the Boot 4 test MVC starter `spring-boot-starter-webmvc-test` (test scope).

**Example:** `mvn -B -q -f apps/time-service/pom.xml verify` finishes successfully without reference to the existing backend module.

## TIME-02 — HTTP response
Expose exactly `GET /api/time`, HTTP `200`, content type compatible with `application/json`. The JSON object has exactly three keys: `time`, `timestamp`, `zone`. `time` is `HH:mm:ss` (24-hour clock, zero-padded), `timestamp` is a valid ISO-8601 offset date-time with seconds and numeric UTC offset, `zone` is a canonical Java `ZoneId.getId()` string.

**Example:** with fixed instant `2026-11-06T14:15:09Z` and zone `America/Lima`, body `{"time":"09:15:09","timestamp":"2026-11-06T09:15:09-05:00","zone":"America/Lima"}`.

## TIME-03 — Zone configuration
Read `app.time.zone` from Spring application configuration, defaulting to `America/Lima`. Resolve it using `ZoneId.of`; the selected zone must control the time, timestamp offset and `zone` field consistently. A custom zone such as `UTC` is supported.

**Example:** `--app.time.zone=UTC` at `2026-11-06T14:15:09Z` yields `{"time":"14:15:09","timestamp":"2026-11-06T14:15:09Z","zone":"UTC"}`. ISO-8601 `Z` is a valid zero UTC offset.

## TIME-04 — Injected clock
Provide an injectable Spring `@Bean java.time.Clock` configured with the selected zone. The endpoint must obtain the current instant through the injected `Clock` (e.g. `OffsetDateTime.now(clock)` or `ZonedDateTime.now(clock)`). Avoid direct `LocalTime.now()`, `Instant.now()`, `System.currentTimeMillis()` or `new Date()` in production code. A fixed Clock must make the JSON deterministic.

**Example:** `Clock.fixed(Instant.parse("2026-11-06T14:15:09Z"), ZoneId.of("America/Lima"))` produces the exact body in TIME-02.

## TIME-05 — Fail-fast zone validation
An invalid `app.time.zone` is a startup configuration error. Fail application context creation promptly with a clear error mentioning `app.time.zone` and the invalid value (without falling back silently). The invalid zone must not create a functional HTTP server.

**Example:** `--app.time.zone=Not/A_Real_Zone` exits nonzero with a clear configuration failure.

## TIME-06 — Port, independence and access
Use normal Spring Boot `server.port` (default `8080`); do not hard-code a port or introduce another configuration parameter. No database, network client, authentication service, or dependency on `backend/` is needed.

**Example:** `java -jar time-service.jar --server.port=9091 --app.time.zone=UTC` serves `http://localhost:9091/api/time`.

## TIME-07 — Test and scope isolation
The visible tests in `apps/time-service/src/test/**` are provided and protected. The Worker may modify only `apps/time-service/pom.xml` and `apps/time-service/src/main/**` (maximum six changed files); it must not modify any visible tests, this specification, `vendor/` or existing exercises. Acceptance uses Maven `verify`; the unseen holdout is supplied only outside the model context.

**Example:** adding a new test file under `src/test/` as part of a proposed patch is rejected even if `mvn verify` would pass.
