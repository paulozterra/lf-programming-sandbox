"""T54 phase 1: project config is complete, safe and fail-closed."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from config.project_config import ProjectConfigError, load, validate

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "pilot/config/projects/sandbox.json").read_text("utf-8"))


class ProjectConfigTests(unittest.TestCase):
    def test_real_sandbox_config(self):
        self.assertEqual(load("sandbox")["schema_version"], "LF_PROJECT_CONFIG_V1")
        self.assertEqual(load("sandbox")["storage"]["requests_root"], "pilot/runs")

    def test_valid_synthetic_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = copy.deepcopy(FIXTURE)
            cfg["project_id"] = "other"
            path = root / "pilot/config/projects/other.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(cfg), encoding="utf-8")
            self.assertEqual(load("other", root=root), cfg)

    def test_missing_project_no_default(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                load("unknown", root=Path(temp))

    def test_invalid_project_identifiers(self):
        for name in ("../sandbox", "/sandbox", "Sandbox", "", "x/y", "x\\y"):
            with self.subTest(name=name), self.assertRaisesRegex(
                    ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                load(name)

    def test_missing_keys_at_every_level(self):
        cases = [
            (lambda c: c.pop("write_roots")),
            (lambda c: c["storage"].pop("requests_root")),
            (lambda c: c["storage"].pop("task_template_pattern")),
            (lambda c: c["components"].pop("frontend")),
            (lambda c: c["components"]["backend"].pop("test_roots")),
            (lambda c: c["components"]["frontend"].pop("manifest")),
        ]
        for mutate in cases:
            cfg = copy.deepcopy(FIXTURE)
            mutate(cfg)
            with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                validate(cfg, root=ROOT)

    def test_absolute_traversal_windows_and_empty_paths(self):
        for bad in ("/tmp/data", "../escape", "pilot/../runs", "pilot//runs",
                    "C:/secret", "pilot\\runs", ".", "", "pilot/./runs"):
            cfg = copy.deepcopy(FIXTURE)
            cfg["storage"]["requests_root"] = bad
            with self.subTest(bad=bad), self.assertRaisesRegex(
                    ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                validate(cfg, root=ROOT)

    def test_rejects_symlink_ancestors_and_config_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pilot").mkdir()
            (root / "target").mkdir()
            (root / "pilot/runs").symlink_to(root / "target", target_is_directory=True)
            with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                validate(FIXTURE, root=root)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / "pilot/config/projects"
            directory.mkdir(parents=True)
            target = root / "actual.json"
            target.write_text(json.dumps(FIXTURE), encoding="utf-8")
            (directory / "sandbox.json").symlink_to(target)
            with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                load("sandbox", root=root)

    def test_write_roots_must_be_explicit(self):
        for roots in ([], ["pilot/runs"], ["apps/time-service", "frontend"]):
            cfg = copy.deepcopy(FIXTURE)
            cfg["write_roots"] = roots
            with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                validate(cfg, root=ROOT)

    def test_template_pattern_is_exact_and_scoped(self):
        for bad in ("pilot/runs/{request}/templates/{task}.json",
                    "other/{request}/templates/{task}.task.json",
                    "pilot/runs/../{request}/templates/{task}.task.json",
                    "pilot/runs/{request}/templates/{task}.task.json/extra"):
            cfg = copy.deepcopy(FIXTURE)
            cfg["storage"]["task_template_pattern"] = bad
            with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                validate(cfg, root=ROOT)

    def test_component_files_cannot_escape_component_root(self):
        cfg = copy.deepcopy(FIXTURE)
        cfg["components"]["backend"]["build_file"] = "frontend/package.json"
        with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
            validate(cfg, root=ROOT)

    def test_invalid_json_and_unknown_keys(self):
        cfg = copy.deepcopy(FIXTURE)
        cfg["unknown"] = "unexpected"
        with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
            validate(cfg, root=ROOT)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "pilot/config/projects/sandbox.json"
            path.parent.mkdir(parents=True)
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                load("sandbox", root=root)


if __name__ == "__main__":
    unittest.main()
