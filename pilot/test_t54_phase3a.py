"""T54 phase 3a: open component map and area roots, equivalent to today.

No consumer reads these yet (phase 3b/3c migrate them). These tests pin the
sandbox configuration to the constants the route uses today, so migrating a
consumer cannot silently change what it allows or protects.
"""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pilot/orchestrator"))

from pilot.config import project_config as pc  # noqa: E402
import native_write_scope  # noqa: E402

FIXTURE = json.loads((ROOT / "pilot/config/projects/sandbox.json").read_text("utf-8"))


def invalid(cfg):
    try:
        pc.validate(cfg, root=ROOT)
    except pc.ProjectConfigError as exc:
        return str(exc) == "PROJECT_CONFIG_INVALID"
    return False


class Equivalence(unittest.TestCase):
    def test_area_write_prefixes_equal_native_write_scope(self):
        for area, roots in native_write_scope.AREA_ROOTS.items():
            self.assertEqual(pc.area_write_prefixes(area, "sandbox"), roots, area)

    def test_area_project_roots_equal_native_lot_binding(self):
        # Frozen literal of native_lot_binding.REAL_ROOTS before phase 3b.
        real_roots = {
            "BACKEND": ("apps/time-service/src/main/java/", "backend/src/main/java/"),
            "FRONTEND": ("apps/web/", "frontend/"),
            "DATA": ("db/", "supabase/migrations/", "apps/time-service/src/main/resources/db/migration/",
             "apps/time-service/src/main/resources/db/rollback/"),
            "INFRA": ("apps/time-service/", "frontend/"),
            "CONTRATO": ("contracts/",),
        }
        self.assertEqual(set(real_roots), pc.AREAS)
        for area, roots in real_roots.items():
            self.assertEqual(pc.area_project_roots(area, "sandbox"), roots, area)

    def test_component_facts_equal_route_constants(self):
        backend = pc.component("backend", "sandbox")
        frontend = pc.component("frontend", "sandbox")
        self.assertEqual(backend["build_file"], "apps/time-service/pom.xml")
        self.assertEqual(backend["test_roots"],
                         ["apps/time-service/src/test", "apps/time-service/visible-tests"])
        self.assertEqual(backend["migrations_root"],
                         "apps/time-service/src/main/resources/db/migration")
        self.assertEqual(frontend["build_file"], "frontend/package.json")
        self.assertEqual(frontend["lock_file"], "frontend/package-lock.json")
        self.assertEqual(frontend["generated_client"],
                         {"dir": "frontend/src/lib/api/generated", "script": "gen:api",
                          "generator": "frontend/scripts/gen-api.mjs"})
        # t4_admission protects these test roots today (line ~371).
        self.assertTrue({"apps/time-service/src/test", "frontend/src"}
                        <= set(pc.all_test_roots("sandbox")))

    def test_protected_paths_unchanged(self):
        self.assertEqual(pc.protected_paths("sandbox"), (
            "apps/time-service/src/test/**", "apps/time-service/visible-tests/**",
            "frontend/src/**/__tests__/**", "frontend/visible-tests/**"))


class OpenMap(unittest.TestCase):
    def test_backend_only_project_is_valid(self):
        cfg = copy.deepcopy(FIXTURE)
        del cfg["components"]["frontend"]
        cfg["areas"]["FRONTEND"] = {"write_prefixes": ["apps/"], "project_roots": ["apps/time-service/"]}
        self.assertFalse(invalid(cfg))

    def test_extra_service_is_valid(self):
        cfg = copy.deepcopy(FIXTURE)
        extra = copy.deepcopy(cfg["components"]["backend"])
        for key in ("root",):
            extra[key] = "apps/billing"
        extra.update(build_file="apps/billing/pom.xml", source_roots=["apps/billing/src/main/java"],
                     resource_roots=[], test_roots=[], affected_test_roots=[], migrations_root=None, config_files=[])
        cfg["components"]["billing"] = extra
        cfg["write_roots"].append("apps/billing")
        self.assertFalse(invalid(cfg))

    def test_rejections(self):
        cases = []
        def case(fn):
            cfg = copy.deepcopy(FIXTURE)
            fn(cfg)
            cases.append(cfg)
        case(lambda c: c.__setitem__("components", {}))
        case(lambda c: c["components"].__setitem__("Bad Name", c["components"]["backend"]))
        case(lambda c: c["components"]["backend"].__setitem__("kind", "gradle"))
        case(lambda c: c["components"]["backend"].__setitem__("source_roots", []))
        case(lambda c: c["components"]["backend"].__setitem__("migrations_root", "frontend/db"))
        case(lambda c: c["components"]["backend"].__setitem__("generated_client",
             c["components"]["frontend"]["generated_client"]))  # maven cannot generate npm client
        case(lambda c: c["components"]["frontend"]["generated_client"].__setitem__("script", "rm -rf"))
        case(lambda c: c["components"].__setitem__("dup", copy.deepcopy(c["components"]["frontend"])))
        case(lambda c: c["areas"].__setitem__("EXTRA", c["areas"]["DATA"]))
        case(lambda c: c["areas"]["DATA"].__setitem__("write_prefixes", ["db"]))  # must end in /
        case(lambda c: c["areas"]["DATA"].__setitem__("write_prefixes", ["../db/"]))
        case(lambda c: c["areas"]["DATA"].__setitem__("project_roots", ["pilot/"]))  # not a write root
        case(lambda c: c["areas"]["BACKEND"].__setitem__("write_prefixes", []))
        for index, cfg in enumerate(cases):
            with self.subTest(index=index):
                self.assertTrue(invalid(cfg))

    def test_unknown_component_or_area_is_denied(self):
        with self.assertRaises(pc.ProjectConfigError):
            pc.component("mobile", "sandbox")
        with self.assertRaises(pc.ProjectConfigError):
            pc.area_write_prefixes("MOBILE", "sandbox")


if __name__ == "__main__":
    unittest.main()
