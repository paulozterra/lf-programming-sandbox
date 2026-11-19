"""T54 phase 3c: Worker-side consumers read project config, equal for the sandbox.

legacy_* values are frozen copies of main@efc96c96 (before phase 3c).
"""
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "pilot/orchestrator", ROOT / "pilot/worker_v08",
              ROOT / "vendor/programming-agent/src"):
    sys.path.insert(0, str(extra))

from pilot.config import project_config as pc  # noqa: E402
import affected_tests  # noqa: E402
import contract_validate  # noqa: E402
import generated_conflict_recovery as gcr  # noqa: E402
import native_derived_generation as ndg  # noqa: E402
import playwright_gate  # noqa: E402
import register_task_context as rtc  # noqa: E402

PB = "apps/time-service/pom.xml"
GEN = "frontend/src/lib/api/generated"

LEGACY_FORMAT = {"name": "std-be-05-spotless-check",
                 "argv": ["mvn", "-B", "-q", "-f", PB, "spotless:check"],
                 "timeout_seconds": 600, "max_output_bytes": 16000}


def legacy_classify(value):
    if re.fullmatch(r"apps/time-service/src/main/resources/db/migration/V[0-9]+__[a-z][a-z0-9_]*[.]sql", value):
        return "DATA"
    if value.startswith("apps/time-service/src/main/java/") or value.startswith("backend/src/main/java/") \
            or value.startswith("backend/"):
        return "BACKEND"
    if value.startswith("apps/time-service/src/test/"):
        return "BACKEND"
    if value.startswith(("frontend/", "apps/web/")):
        return "FRONTEND"
    if value.startswith(("db/", "supabase/migrations/", "standards/kit-base/")):
        return "DATA"
    return "BLOCKED"


def classify(value):
    try:
        return rtc.classify_path(value)
    except rtc.ContextBlocked:
        return "BLOCKED"


PATHS = [
    "apps/time-service/src/main/resources/db/migration/V3__add_x.sql",
    "apps/time-service/src/main/resources/db/migration/V3__Bad.sql",
    "apps/time-service/src/main/resources/db/migration/README.md",
    "apps/time-service/src/main/java/lf/sandbox/time/auth/AuthService.java",
    "apps/time-service/src/test/java/lf/sandbox/time/AuthTest.java",
    "apps/time-service/visible-tests/java/X.java",
    "apps/time-service/pom.xml",
    "backend/src/main/java/a/B.java",
    "frontend/src/app/page.tsx", "apps/web/page.tsx",
    "db/V1__x.sql", "supabase/migrations/1.sql", "standards/kit-base/x.sql",
    "contracts/x.openapi.yaml", "docs/readme.md",
]


class Equivalence(unittest.TestCase):
    def test_format_command(self):
        self.assertEqual(rtc.format_command(), LEGACY_FORMAT)

    def test_classify_path(self):
        for value in PATHS:
            with self.subTest(value=value):
                expected = legacy_classify(value)
                # Documented tightening: "backend/" outside src/main/java is no
                # longer BACKEND (the area's configured root is backend/src/main/java/).
                if value.startswith("backend/") and not value.startswith("backend/src/main/java/"):
                    expected = "BLOCKED"
                self.assertEqual(classify(value), expected)

    def test_backend_outside_java_is_now_unclassified(self):
        self.assertEqual(legacy_classify("backend/pom.xml"), "BACKEND")
        self.assertEqual(classify("backend/pom.xml"), "BLOCKED")

    def test_generated_client(self):
        self.assertEqual(ndg.generated_root(), GEN + "/")
        self.assertEqual(ndg.generator_label(), "npm run gen:api")
        legacy = re.compile(r"frontend/src/lib/api/generated/(?:index|[a-z][a-z0-9-]*)\.ts\Z")
        for value in (GEN + "/index.ts", GEN + "/users.ts", GEN + "/Users.ts",
                      GEN + "/sub/x.ts", "frontend/src/lib/api/x.ts", GEN + "/index.tsx"):
            self.assertEqual(ndg.generated_output(value), bool(legacy.fullmatch(value)), value)

    def test_conflict_recovery_patterns(self):
        legacy = re.compile(r"git diff --exit-code -- frontend/src/lib/api/generated")
        log = "Run git diff --exit-code -- frontend/src/lib/api/generated\nexit 1"
        self.assertEqual(bool(gcr._ci_derived_gen().search(log)), bool(legacy.search(log)))
        self.assertEqual(gcr._generated_dir() + "/index.ts", GEN + "/index.ts")

    def test_test_roots(self):
        self.assertEqual(affected_tests.project_test_roots(), ("apps/time-service/src/test",))
        self.assertEqual(affected_tests.project_test_globs(), ("apps/time-service/src/test/**",))
        self.assertEqual(pc.affected_test_roots(), ("apps/time-service/src/test", "frontend/src"))

    def test_contract_validate_commands(self):
        calls = []

        class Done:
            returncode = 0
            stdout = ""

        def fake_run(argv, **kw):
            calls.append(argv)
            return Done()
        with patch.object(contract_validate.subprocess, "run", side_effect=fake_run):
            contract_validate.check_generated(Path("."))
        self.assertEqual(calls, [["npm", "--prefix", "frontend", "run", "gen:api"],
                                 ["git", "diff", "--exit-code", "--", GEN],
                                 ["git", "ls-files", "--others", "--exclude-standard", "--", GEN]])

    def test_playwright_commands(self):
        spawned = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "apps/time-service").mkdir(parents=True)
            (root / PB).write_text("<project/>")
            (root / "frontend").mkdir()
            (root / "frontend/package.json").write_text("{}")

            def fake_spawn(argv, where):
                spawned.append(argv)
                raise playwright_gate.BrowserBlocked("STOP_AFTER_SPAWN")
            with patch.object(playwright_gate, "available"), \
                 patch.object(playwright_gate, "_spawn", side_effect=fake_spawn):
                with self.assertRaises(playwright_gate.BrowserBlocked):
                    playwright_gate.verify(root, path="/", selector="body", text=None, title=None)
        self.assertEqual(spawned[0][:6], ["mvn", "-B", "-q", "-f", PB, "spring-boot:run"])

    def test_missing_frontend_build_file_still_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "apps/time-service").mkdir(parents=True)
            (root / PB).write_text("<project/>")
            with self.assertRaisesRegex(playwright_gate.BrowserBlocked, "APP_NO_ARRANCA"):
                playwright_gate.verify(root, path="/", selector="body", text=None, title=None)


class Schema(unittest.TestCase):
    def test_affected_test_roots_must_be_protected_test_roots(self):
        cfg = json.loads((ROOT / "pilot/config/projects/sandbox.json").read_text("utf-8"))
        cfg["components"]["backend"]["affected_test_roots"] = ["apps/time-service/src/main/java"]
        with self.assertRaises(pc.ProjectConfigError):
            pc.validate(cfg, root=ROOT)
        cfg = json.loads((ROOT / "pilot/config/projects/sandbox.json").read_text("utf-8"))
        del cfg["components"]["frontend"]["affected_test_roots"]
        with self.assertRaises(pc.ProjectConfigError):
            pc.validate(cfg, root=ROOT)

    def test_frontend_without_generated_client_blocks_contract_derivatives(self):
        cfg = json.loads((ROOT / "pilot/config/projects/sandbox.json").read_text("utf-8"))
        cfg["components"]["frontend"]["generated_client"] = None
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pilot/config/projects").mkdir(parents=True)
            (root / "pilot/config/projects/sandbox.json").write_text(json.dumps(cfg))
            (root / "pilot/config/active_project.json").write_text(json.dumps(
                {"schema_version": "LF_ACTIVE_PROJECT_V1", "project_id": "sandbox"}))
            with patch.object(pc, "CONFIG_ROOT", root):
                with self.assertRaises(pc.ProjectConfigError):
                    ndg.generated_root()


if __name__ == "__main__":
    unittest.main()


class NoComponentLiterals(unittest.TestCase):
    """Only explicitly frozen files may still name the sandbox's components."""

    FROZEN = {
        # Historical experiment reproducers (byte-exact replays of past runs).
        "pilot/worker_v08/task_selector.py", "pilot/worker_v08/derive_context.py",
        "pilot/worker_v08/build_time_service_jar.py", "pilot/worker_v08/run_live_pilot.py",
        "pilot/worker_v08/lot_preflight.py",
        # Owner decision F5.1 (2026-11-12) and the pinned selector SQL seed.
        "pilot/orchestrator/package_to_lots.py", "pilot/orchestrator/selector_db.py",
        # Report labels only (classifies human interventions, never gates).
        "pilot/orchestrator/intervention_report.py",
    }
    LITERAL = re.compile(r"apps/time-service|[\"'(]frontend(?:/|[\"'])")

    def test_live_route_code_has_no_component_literals(self):
        offenders = []
        for path in sorted((ROOT / "pilot").rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if (rel.startswith(("pilot/config/", "pilot/lf_producers_pinned/"))
                    or path.name.startswith("test_") or path.name == "conftest.py"
                    or rel in self.FROZEN):
                continue
            for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
                if self.LITERAL.search(line):
                    offenders.append(f"{rel}:{number}")
        self.assertEqual(offenders, [])
