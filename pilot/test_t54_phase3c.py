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
    """Only explicitly frozen code may still name the sandbox's components.

    Review of PR #362 (H1): derive_context and lot_preflight are *live*
    (register_task_context and native_run call derive/denial/check_task), so
    they are frozen per top-level symbol, not per file: only their historical
    exercise constants and functions may keep sandbox paths.
    """

    FROZEN_FILES = {
        # Historical experiment reproducers (never reached by native lots).
        "pilot/worker_v08/task_selector.py", "pilot/worker_v08/build_time_service_jar.py",
        "pilot/worker_v08/run_live_pilot.py",
        # Owner decision F5.1 (2026-11-12) and the pinned selector SQL seed.
        "pilot/orchestrator/package_to_lots.py", "pilot/orchestrator/selector_db.py",
        # Report labels only (classifies human interventions, never gates).
        "pilot/orchestrator/intervention_report.py",
    }
    FROZEN_SYMBOLS = {
        "pilot/worker_v08/derive_context.py": {"EX5C_WRITES", "EX5C_SPEC", "expected_ex5c"},
        "pilot/worker_v08/lot_preflight.py": {"LOT_PATH", "LOT_A", "check_handoff", "preflight"},
    }
    LITERAL = re.compile(r"apps/time-service|[\"'(]frontend(?:/|[\"'])")

    @staticmethod
    def _owner_by_line(source):
        import ast
        owners = {}
        for node in ast.parse(source).body:
            names = []
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = [t.id for t in targets if isinstance(t, ast.Name)]
            for line in range(node.lineno, node.end_lineno + 1):
                owners[line] = set(names)
        return owners

    def test_live_route_code_has_no_component_literals(self):
        offenders = []
        for path in sorted((ROOT / "pilot").rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if (rel.startswith(("pilot/config/", "pilot/lf_producers_pinned/"))
                    or path.name.startswith("test_") or path.name == "conftest.py"
                    or rel in self.FROZEN_FILES):
                continue
            source = path.read_text("utf-8")
            allowed = self.FROZEN_SYMBOLS.get(rel, set())
            owners = self._owner_by_line(source) if allowed else {}
            for number, line in enumerate(source.splitlines(), 1):
                if self.LITERAL.search(line) and not (owners.get(number, set()) & allowed):
                    offenders.append(f"{rel}:{number}")
        self.assertEqual(offenders, [])

    def test_frozen_symbols_are_not_reached_by_native_lots(self):
        """The frozen helpers are only called from historical entry points."""
        for rel, symbols in self.FROZEN_SYMBOLS.items():
            for symbol in symbols:
                for path in (ROOT / "pilot").rglob("*.py"):
                    other = path.relative_to(ROOT).as_posix()
                    if other == rel or path.name.startswith("test_") or other in self.FROZEN_FILES:
                        continue
                    text = path.read_text("utf-8")
                    module = Path(rel).stem
                    imported = re.search(r"from\s+(?:[\w.]+\.)?" + module + r"\s+import[^\n]*\b"
                                         + symbol + r"\b", text)
                    attribute = re.search(r"\b" + module + r"\." + symbol + r"\b", text)
                    self.assertFalse(imported or attribute, f"{symbol} used by live {other}")

    def test_live_denial_equals_legacy(self):
        import derive_context
        from pathlib import PurePosixPath

        def legacy(name):
            parts = PurePosixPath(name).parts
            if any(p.startswith(".env") for p in parts) and name != "apps/time-service/.env.example":
                return "DENIED_ENV"
            contract = bool(re.fullmatch(r"contracts/[a-z][a-z0-9-]*[.]openapi[.]yaml", name))
            if not contract and (not parts or parts[0] not in ("apps", "frontend", "db")
                                 and not name.startswith("supabase/migrations/")):
                return "DENIED_OUTSIDE_APPS"
            return None
        for name in ("apps/time-service/.env.example", "frontend/.env.example", "apps/x/a.java",
                     "frontend/a.ts", "db/a.sql", "db", "supabase/migrations/1.sql",
                     "supabase/migrations", "supabase/x", "backend/a.java",
                     "contracts/a.openapi.yaml", "docs/a.md", "apps", ".env", "apps/time-service/.env"):
            with self.subTest(name=name):
                self.assertEqual(derive_context.denial(name), legacy(name))


class NoMavenProject(unittest.TestCase):
    """Review H2: a project without a BACKEND maven component never needs Spotless."""

    def test_format_command_is_none_and_non_backend_admission_does_not_need_it(self):
        cfg = json.loads((ROOT / "pilot/config/projects/sandbox.json").read_text("utf-8"))
        del cfg["components"]["backend"]
        cfg["areas"]["BACKEND"]["project_roots"] = ["backend/src/main/java/"]
        cfg["areas"]["DATA"]["project_roots"] = ["db/"]
        cfg["areas"]["DATA"]["write_prefixes"] = ["db/"]
        cfg["areas"]["INFRA"]["project_roots"] = ["frontend/"]
        cfg["lot_policy"]["protected_base"] = [p for p in cfg["lot_policy"]["protected_base"]
                                               if not p.startswith("apps/")]
        cfg["lot_policy"]["areas"]["INFRA"].update(
            unprotect=[], protect=["frontend/src/**"], context_files=[])
        cfg["lot_policy"]["areas"]["DATA"].update(
            unprotect=["db/**"], protect=["db/**/test/**"])
        cfg["protected_paths"] = ["frontend/src/**/__tests__/**"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pilot/config/projects").mkdir(parents=True)
            (root / "pilot/config/projects/sandbox.json").write_text(json.dumps(cfg))
            (root / "pilot/config/active_project.json").write_text(json.dumps(
                {"schema_version": "LF_ACTIVE_PROJECT_V1", "project_id": "sandbox"}))
            with patch.object(pc, "CONFIG_ROOT", root):
                pc.load("sandbox", root=root)
                self.assertIsNone(rtc.format_command())
                import lf_rule_gate
                rows = [{"rule_id": "STD-BE-05", "coverage": "NO_VERIFICADO"}]
                visible = {"attempts": [{"acceptance": [
                    {"name": "std-be-05-spotless-check", "argv": ["true"], "status": "PASS"}]}]}
                declared = [{"name": "std-be-05-spotless-check", "argv": ["true"]}]
                out = lf_rule_gate.verified_visible_commands(rows, visible, declared)
                self.assertEqual(out[0]["coverage"], "NO_VERIFICADO")  # never attested


if __name__ == "__main__":
    unittest.main()
