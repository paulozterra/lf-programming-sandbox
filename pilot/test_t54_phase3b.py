"""T54 phase 3b: lot planning/admission read project config, byte-equal today.

The legacy_* functions below are frozen copies of the code before phase 3b;
with the sandbox configuration every migrated consumer must return exactly
the same values, and a project lacking a component must fail closed.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pilot/orchestrator"))

from pilot.config import project_config as pc  # noqa: E402
import generate_chain as g  # noqa: E402
import native_write_scope as w  # noqa: E402
import native_lot_binding as b  # noqa: E402
import t4_admission as t  # noqa: E402
import atomize  # noqa: E402
import infra_validate  # noqa: E402

PB = "apps/time-service/pom.xml"


def legacy_protected(area, paths):
    protected=[".github/**",".lf/**","pilot/**","vendor/**",
               "apps/time-service/src/test/**","apps/time-service/visible-tests/**",
               "apps/time-service/pom.xml","apps/time-service/src/main/resources/**",
               "frontend/package.json","frontend/package-lock.json",
               "frontend/src/**/__tests__/**","db/**"]
    if area=="INFRA":
        for manifest in ("frontend/package.json", "frontend/package-lock.json"):
            if manifest in paths:
                protected.remove(manifest)
        protected.remove("apps/time-service/pom.xml")
        protected.remove("apps/time-service/src/main/resources/**")
        protected += ["apps/time-service/src/main/resources/db/**",
                      "frontend/src/**", "apps/time-service/src/main/java/**"]
    if area=="DATA":
        protected.remove("apps/time-service/src/main/resources/**")
        protected += ["apps/time-service/src/main/resources/application.properties",
                      "apps/time-service/src/main/resources/static/**"]
        protected.remove("db/**")
        protected.extend(["db/**/test/**","db/**/fixtures/**"])
    return protected


def legacy_acceptance_cmds(area, paths, has_contract=False):
    if area=="BACKEND":
        r=[["mvn","-B","-q","-f",PB,"package"]]
        if has_contract:
            r+=[["mvn","-B","-q","-f",PB,"spring-boot:start"],
                ["lf-python","pilot/orchestrator/contract_validate.py","--compare-live","http://127.0.0.1:8080/v3/api-docs"],
                ["mvn","-B","-q","-f",PB,"spring-boot:stop"]]
        return r
    if area=="FRONTEND":
        r=[["npm","--prefix","frontend","ci"]]
        if has_contract:
            r+=[["npm","--prefix","frontend","run","gen:api"]]
        return r
    if area=="INFRA":
        argv=["lf-python","pilot/orchestrator/infra_validate.py","--check-infra","--root","."]
        if "apps/time-service/src/main/resources/application.properties" in paths:
            argv+=["--database"]
        r=[argv]
        if PB in paths:
            r.append(["mvn","-U","-B","-q","-f",PB,"-DskipTests","package"])
        if "frontend/package.json" in paths:
            r+= [["npm","--prefix","frontend","ci"],["npm","--prefix","frontend","run","gen:api"]]
        return r


LEGACY_AREA_ROOTS = {"CONTRATO": ("contracts/",), "INFRA": ("apps/", "frontend/"),
    "DATA": ("db/", "supabase/migrations/", "apps/time-service/src/main/resources/db/migration/"),
    "BACKEND": ("apps/", "backend/"), "FRONTEND": ("frontend/",)}
LEGACY_REAL_ROOTS = {"BACKEND": ("apps/time-service/src/main/java/", "backend/src/main/java/"),
    "FRONTEND": ("apps/web/", "frontend/"),
    "DATA": ("db/", "supabase/migrations/", "apps/time-service/src/main/resources/db/migration/"),
    "INFRA": ("apps/time-service/", "frontend/"), "CONTRATO": ("contracts/",)}

PATH_SETS = [
    [], ["frontend/package.json"], ["frontend/package-lock.json"],
    ["frontend/package.json", "frontend/package-lock.json", PB],
    ["apps/time-service/src/main/resources/application.properties"],
    [PB, "apps/time-service/src/main/resources/application.properties", "frontend/package.json"],
    ["frontend/next.config.js"],
]


def cmds(area, paths, **kw):
    if area == "INFRA":
        kw.setdefault("infra_dependencies", [])
    return [x["argv"] for x in g.acceptance(area, paths, **kw)
            if x["argv"][0] in ("mvn", "npm") or "infra_validate.py" in " ".join(x["argv"])
            or "--compare-live" in x["argv"]]


class Equivalence(unittest.TestCase):
    def test_lot_protection_equals_legacy_for_every_area_and_write_set(self):
        for area in sorted(pc.AREAS):
            for paths in PATH_SETS:
                with self.subTest(area=area, paths=paths):
                    self.assertEqual(sorted(g.lot_protection(area, paths)),
                                     sorted(legacy_protected(area, paths)))

    def test_acceptance_commands_equal_legacy(self):
        for area in ("BACKEND", "FRONTEND", "INFRA"):
            for paths in PATH_SETS:
                for contract in (False, True):
                    if area == "INFRA" and contract:
                        continue
                    with self.subTest(area=area, paths=paths, contract=contract):
                        self.assertEqual(cmds(area, paths, has_contract=contract),
                                         legacy_acceptance_cmds(area, paths, contract))

    def test_infra_context_files_equal_legacy(self):
        self.assertEqual(["pilot/orchestrator/dependency_allowlist_v1.json"]
                         + pc.lot_policy()["areas"]["INFRA"]["context_files"],
                         ["pilot/orchestrator/dependency_allowlist_v1.json", PB,
                          "apps/time-service/src/main/resources/application.properties"])

    def test_write_scope_and_real_roots_equal_legacy(self):
        self.assertEqual(w.AREA_ROOTS, LEGACY_AREA_ROOTS)
        self.assertEqual(list(w.AREA_ROOTS), list(LEGACY_AREA_ROOTS))
        self.assertEqual(b.REAL_ROOTS, LEGACY_REAL_ROOTS)

    def test_project_base_equals_legacy_mapping(self):
        cases = {("CONTRATO", "contracts/a.openapi.yaml"): "contracts",
                 ("BACKEND", "apps/time-service/src/main/java/lf/X.java"): "apps/time-service",
                 ("BACKEND", "backend/src/main/java/lf/X.java"): "backend",
                 ("FRONTEND", "apps/web/page.tsx"): "apps/web",
                 ("FRONTEND", "frontend/src/app/page.tsx"): "frontend",
                 ("DATA", "supabase/migrations/1.sql"): "supabase/migrations",
                 ("DATA", "db/1.sql"): "db",
                 ("DATA", "apps/time-service/src/main/resources/db/migration/V1__a.sql"): "apps/time-service",
                 ("INFRA", "frontend/package.json"): "frontend",
                 ("INFRA", PB): "apps/time-service"}
        for (area, path), base in cases.items():
            with self.subTest(path=path):
                self.assertEqual(b._project_base(area, path), base)

    def test_admission_meaningful_tops_equal_legacy(self):
        self.assertEqual(set(t._product_top_dirs()),
                         {"apps/", "frontend/", "backend/", "db/", "contracts/", "supabase/"})

    def test_migration_roots_equal_legacy(self):
        self.assertEqual(atomize._migrations_root(),
                         "apps/time-service/src/main/resources/db/migration")
        self.assertEqual(infra_validate._migrations_prefix(),
                         "apps/time-service/src/main/resources/db/migration/")


class LotPolicyValidation(unittest.TestCase):
    def test_rejections(self):
        base = json.loads((ROOT / "pilot/config/projects/sandbox.json").read_text("utf-8"))
        mutations = [
            lambda c: c.pop("lot_policy"),
            lambda c: c["lot_policy"]["areas"].pop("DATA"),
            lambda c: c["lot_policy"]["areas"]["INFRA"]["unprotect"].append("src/**"),  # hole not in base
            lambda c: c["lot_policy"]["areas"]["INFRA"]["unprotect_if_written"].append(PB),  # both lists
            lambda c: c["lot_policy"]["areas"]["DATA"]["protect"].append("../x/**"),
            lambda c: c["lot_policy"]["areas"]["INFRA"]["context_files"].append("frontend/**"),  # no globs
            lambda c: c["lot_policy"]["protected_base"].append(".github/**"),  # duplicate
        ]
        for index, mutate in enumerate(mutations):
            cfg = copy.deepcopy(base)
            mutate(cfg)
            with self.subTest(index=index), self.assertRaises(pc.ProjectConfigError):
                pc.validate(cfg, root=ROOT)


class OtherProjects(unittest.TestCase):
    def _with_config(self, mutate):
        cfg = json.loads((ROOT / "pilot/config/projects/sandbox.json").read_text("utf-8"))
        mutate(cfg)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "pilot/config/projects").mkdir(parents=True)
        (root / "pilot/config/projects/sandbox.json").write_text(json.dumps(cfg))
        (root / "pilot/config/active_project.json").write_text(json.dumps(
            {"schema_version": "LF_ACTIVE_PROJECT_V1", "project_id": "sandbox"}))
        p = patch.object(pc, "CONFIG_ROOT", root)
        p.start()
        self.addCleanup(p.stop)

    def test_backend_only_project_blocks_frontend_lots_but_plans_backend(self):
        def drop_frontend(c):
            del c["components"]["frontend"]
            c["areas"]["FRONTEND"]["project_roots"] = ["apps/web/"]
            c["areas"]["INFRA"]["project_roots"] = ["apps/time-service/"]
        self._with_config(drop_frontend)
        with self.assertRaises(pc.ProjectConfigError):
            g.acceptance("FRONTEND", ["apps/web/page.tsx"])
        self.assertEqual(cmds("BACKEND", [])[0], ["mvn", "-B", "-q", "-f", PB, "package"])
        infra = cmds("INFRA", ["frontend/package.json"])
        self.assertFalse(any(x[0] == "npm" for x in infra))

    def test_renamed_backend_build_file_flows_into_commands(self):
        def rename(c):
            c["components"]["backend"]["root"] = "services/core"
            c["components"]["backend"].update(
                build_file="services/core/pom.xml", source_roots=["services/core/src/main/java"],
                resource_roots=[], test_roots=["services/core/src/test"],
                migrations_root="services/core/db", config_files=[])
            c["areas"]["BACKEND"]["project_roots"] = ["services/core/src/main/java/"]
            c["areas"]["DATA"]["project_roots"] = ["services/core/db/"]
            c["areas"]["DATA"]["write_prefixes"] = ["services/"]
            c["areas"]["BACKEND"]["write_prefixes"] = ["services/"]
            c["areas"]["INFRA"]["project_roots"] = ["services/core/", "frontend/"]
            c["write_roots"].append("services/core")
        self._with_config(rename)
        self.assertEqual(cmds("BACKEND", [])[0],
                         ["mvn", "-B", "-q", "-f", "services/core/pom.xml", "package"])
        self.assertEqual(atomize._migrations_root(), "services/core/db")


if __name__ == "__main__":
    unittest.main()
