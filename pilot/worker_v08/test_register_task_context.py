"""Offline Phase 2B tests; no hidden oracle, model, Supabase or remote access."""
from __future__ import annotations
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

import register_task_context as mod

ROOT = Path(__file__).resolve().parents[2]
PINS = ROOT / "pilot/lf_profiles_pinned"
WRITE = "apps/time-service/src/main/java/lf/sandbox/time/reminder/ReminderRepository.java"


def task_spec():
    return {
        "schema_version": 1,
        "task_id": "LF-WORKER-NATIVE-EX8",
        "base_head_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "main"], text=True).strip(),
        "objective": "Sandbox-only exercise; no actual Worker dispatch",
        "context_path_patterns": ["apps/time-service/REMINDERS_SPEC.md"],
        "write_path_patterns": [WRITE],
        "protected_path_patterns": ["apps/time-service/src/test/**"],
        "acceptance_commands": [{
            "name": "visible-api",
            "argv": ["mvn", "-B", "-q", "-f", "apps/time-service/pom.xml", "test"],
            "timeout_seconds": 600,
            "max_output_bytes": 16000,
        }],
        "max_context_bytes": 160000,
    }



def sha256_bytes(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def init_git_fixture(root):
    git(root, "init", "-q")
    git(root, "config", "user.name", "CP1.4 Offline")
    git(root, "config", "user.email", "cp14@example.invalid")
    spec = root / "apps/time-service/REMINDERS_SPEC.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("Fixture only: CP1.4\\n", encoding="utf-8")
    java = root / WRITE
    java.parent.mkdir(parents=True, exist_ok=True)
    java.write_text("package lf.sandbox.time.reminder;\\nclass ReminderRepository {}\\n",
                    encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "offline fixture")
    return git(root, "rev-parse", "HEAD")


def run(task, **overrides):
    params = dict(project="lf_java", area="BACKEND", lot_paths=[WRITE],
                  task_name="ex8", budget=160000, root=ROOT, pinned=PINS, persist=False)
    params.update(overrides)
    return mod.register(task, **params)


class PinnedSource(unittest.TestCase):
    def test_entire_source_pin_sha_and_git_blob(self):
        pin, files = mod.read_pins()
        self.assertEqual(len(files), 54)
        self.assertEqual(set(pin["files"]), set(files))
        self.assertEqual(pin["source_commit_sha"], mod.LF_SHA)
        self.assertEqual(pin["status"], "CANDIDATE_SANDBOX_ONLY")
        self.assertTrue(all(hashlib.sha256(v).hexdigest() == pin["files"][k]["sha256"]
                            for k, v in files.items()))

    def test_bytes_reproducible_native_and_api(self):
        native = {"task_spec": task_spec(), "holdout_sha256": "public-digest-only"}
        a, sources_a = run(native)
        b, sources_b = run(native)
        self.assertEqual(mod.canonical(a), mod.canonical(b))
        self.assertEqual(sources_a, sources_b)
        self.assertEqual(a["holdout_sha256"], native["holdout_sha256"])
        self.assertEqual(a["task_spec"]["acceptance_commands"][-1], mod.FORMAT_COMMAND)
        api, _ = run(task_spec())
        self.assertEqual(api["context_path_patterns"], a["task_spec"]["context_path_patterns"])
        self.assertEqual(api["protected_path_patterns"], a["task_spec"]["protected_path_patterns"])

    def test_all_generated_context_paths_protected_and_read_only(self):
        task, artifacts = run(task_spec())
        expected = {".lf/worker-context/ex8/profile.md",
                    ".lf/worker-context/ex8/skills.md",
                    ".lf/worker-context/ex8/receipt.json"}
        self.assertEqual(set(artifacts), expected)
        self.assertTrue(expected.issubset(task["context_path_patterns"]))
        self.assertTrue(expected.issubset(task["protected_path_patterns"]))
        self.assertFalse(expected.intersection(task["write_path_patterns"]))
        receipt = json.loads(artifacts[".lf/worker-context/ex8/receipt.json"])
        self.assertEqual(receipt["source_pin_sha256"], hashlib.sha256((PINS / "SOURCE_PIN.json").read_bytes()).hexdigest())
        self.assertEqual([x["code"] for x in receipt["skills"]], ["SPRINGBOOT_EXP", "KAFKA_EXP"])
        self.assertEqual([x["priority"] for x in receipt["skills"]], [1, 2])
        self.assertIn("STD-BE-05", artifacts[".lf/worker-context/ex8/skills.md"].decode())
        self.assertFalse(receipt["production_authority"])

    def test_modified_pinned_source_rejected_before_register(self):
        with tempfile.TemporaryDirectory() as path:
            temporary = Path(path)
            pin = json.loads((PINS / "SOURCE_PIN.json").read_text())
            for rel in pin["files"]:
                target = temporary / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((PINS / rel).read_bytes())
            (temporary / "SOURCE_PIN.json").write_bytes(mod.canonical(pin))
            modified = temporary / "prog_backend_exp/SKILL.md"
            modified.write_bytes(modified.read_bytes() + b"tamper")
            with self.assertRaisesRegex(mod.ContextBlocked, "SOURCE_PIN_MISMATCH"):
                run(task_spec(), pinned=temporary)

    def test_multi_area_is_blocked(self):
        with self.assertRaisesRegex(mod.ContextBlocked, "LOT_MULTI_AREA"):
            run(task_spec(), lot_paths=[WRITE, "frontend/src/app/page.tsx"])
        for area, scope, expected_profile, expected_skill in (
            ("BACKEND", WRITE, "PERFIL-PROG-BACKEND-EXP", "SPRINGBOOT_EXP"),
            ("FRONTEND", "frontend/src/app/page.tsx", "PERFIL-PROG-FRONTEND-EXP", "NEXTJS"),
            ("DATA", "db/migration/V1__baseline.sql", "PERFIL-PROG-DATA-EXP", "FLYWAY_EXP"),
        ):
            scoped = task_spec()
            scoped["write_path_patterns"] = [scope]
            _, artifacts = run(scoped, area=area, lot_paths=[scope],
                               task_name="cp12_" + area.lower())
            prefix = ".lf/worker-context/cp12_" + area.lower()
            receipt = json.loads(artifacts[prefix + "/receipt.json"])
            self.assertEqual(receipt["profile"]["code"], expected_profile)
            self.assertIn(expected_skill, [row["code"] for row in receipt["skills"]])
            rendered = artifacts[prefix + "/skills.md"].decode("utf-8")
            if area == "BACKEND":
                self.assertEqual(rendered.count("- STD-BE-05 ["), 1)
            if area == "FRONTEND":
                catalog = json.loads((PINS / "stack_skills_exp" /
                                      "pg00_normative_catalog_snapshot.json").read_text("utf-8"))
                rule = next(x for x in catalog["rules"] if x["id"] == "STD-FE-04")
                exact = "- " + rule["id"] + " [" + rule["status"] + "]: " + rule["rule"]
                self.assertIn(exact, rendered)
                self.assertNotIn("decisión de Paulo", rendered)
                self.assertNotIn("(a) o (b)", rendered)
                self.assertNotIn("ANGULAR_EXP@", rendered)
                for n in ("01", "02", "03", "05", "06", "07"):
                    self.assertIn("STD-FE-" + n, rendered)
            if area == "DATA":
                self.assertIn("FLYWAY_EXP", rendered)


    def test_nextjs_pin_and_pinned_lf_profiles_have_valid_sha(self):
        from hashlib import sha256
        pin, files = mod.read_pins()
        self.assertEqual(len(files), 54)
        for role in ("prog_frontend_exp", "prog_data_exp"):
            for name in ("SKILL.md", "contracts/main_contract.md",
                         "contracts/missing_input_policy.md",
                         "contracts/runtime_binding.json",
                         "checklists/preflight_checklist.md",
                         "checklists/priority_checklist.md"):
                path = role + "/" + name
                self.assertEqual(sha256(files[path]).hexdigest(),
                                 pin["files"][path]["sha256"])
        cfg = json.loads((ROOT / "pilot/nextjs_source_pin.json").read_text())
        for key, outpath in (("skill_sha256", "skill_path"),
                             ("manifest_sha256", "manifest_path")):
            self.assertEqual(sha256((ROOT / cfg[outpath]).read_bytes()).hexdigest(),
                             cfg[key])

    def test_historical_ex6_ex7_ex8_bytes_unchanged_by_registration(self):
        historic = [ROOT / "pilot/worker_v08/native_tasks" / (x + ".json")
                    for x in ("ex6", "ex7", "ex8")]
        before = {str(x): sha256_bytes(x) for x in historic}
        for area, paths in (("BACKEND", [WRITE]),
                            ("FRONTEND", ["frontend/src/app/page.tsx"]),
                            ("DATA", ["db/migration/V1__baseline.sql"])):
            scoped = task_spec()
            scoped["write_path_patterns"] = paths
            run(scoped, area=area, lot_paths=paths,
                task_name="cp12_immutable_" + area.lower())
        self.assertEqual(before, {str(x): sha256_bytes(x) for x in historic})

    def test_native_end_to_end_git_registration_and_loader(self):
        from native_run import load_registration
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            head = init_git_fixture(root)
            source = json.loads((ROOT / "pilot/worker_v08/native_tasks/ex8.json").read_text())
            task = copy.deepcopy(source["task_spec"])
            task.update(task_id="LF-WORKER-NATIVE-CP14-NEW",
                        base_head_sha=head,
                        max_attempts=1,
                        write_path_patterns=[WRITE],
                        context_path_patterns=["apps/time-service/REMINDERS_SPEC.md"],
                        protected_path_patterns=["apps/time-service/src/test/**"])
            enriched, artifacts = run(task, task_name="cp14fresh", root=root, persist=True)
            native_out = root / "pilot/worker_v08/native_tasks/cp14fresh.json"
            digest = "a" * 64  # Synthetic SHA only; never a hidden exam.
            raw = mod.write_native_registration(
                root, "cp14fresh", native_out, enriched, digest)
            self.assertEqual(raw, mod.canonical({"task_spec": enriched,
                                                  "holdout_sha256": digest}))
            self.assertEqual(native_out.read_bytes(), raw)
            loaded, sha = load_registration(root, "cp14fresh")
            self.assertEqual(loaded, enriched)
            self.assertEqual(sha, digest)
            self.assertEqual(mod.write_native_registration(
                root, "cp14fresh", native_out, enriched, digest), raw)
            self.assertEqual(native_out.read_bytes(), raw)
            self.assertEqual(len(artifacts), 3)

    def test_native_fail_closed_paths_sha_historic_and_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            safe = root / "pilot/worker_v08/native_tasks/newtask.json"
            spec = {"max_attempts": 1, "base_head_sha": "a" * 40}
            with self.assertRaisesRegex(mod.ContextBlocked, "NATIVE_TASK_PATH_INVALID"):
                mod.write_native_registration(
                    root, "newtask", root / "elsewhere/newtask.json", spec, "b" * 64)
            for invalid in ("bad", "g" * 64, "a" * 63, "a" * 65):
                with self.assertRaisesRegex(mod.ContextBlocked, "NATIVE_HOLDOUT_SHA_INVALID"):
                    mod.write_native_registration(root, "newtask", safe, spec, invalid)
            for historic in ("ex6", "ex7", "ex8"):
                with self.assertRaisesRegex(mod.ContextBlocked, "HISTORICAL_TASK_IMMUTABLE"):
                    mod.write_native_registration(
                        root, historic,
                        root / "pilot/worker_v08/native_tasks" / (historic + ".json"),
                        spec, "b" * 64)
            for invalid_spec in ({"max_attempts": 2, "base_head_sha": "a" * 40},
                                 {"max_attempts": 1, "base_head_sha": "b" * 39}):
                with self.assertRaises(mod.ContextBlocked):
                    mod.write_native_registration(
                        root, "newtask", safe, invalid_spec, "b" * 64)
            original = mod.write_native_registration(
                root, "newtask", safe, spec, "b" * 64)
            with self.assertRaisesRegex(mod.ContextBlocked, "NATIVE_TASK_EXISTS"):
                mod.write_native_registration(
                    root, "newtask", safe, spec, "c" * 64)
            self.assertEqual(safe.read_bytes(), original)

    def test_missing_git_blocks_new_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(mod.ContextBlocked, "LOT_PREFLIGHT_NO_GIT"):
                run(task_spec(), root=root, task_name="cp14nogit")

    def test_historical_native_bytes_are_untouched(self):
        originals = {name: (ROOT / "pilot/worker_v08/native_tasks" /
                            (name + ".json")).read_bytes()
                     for name in ("ex6", "ex7", "ex8")}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_git_fixture(root)
            template = task_spec()
            template["task_id"] = "LF-WORKER-NATIVE-CP14-HISTORY"
            run(template, root=root, task_name="cp14check", persist=False)
        self.assertEqual(originals,
                         {name: (ROOT / "pilot/worker_v08/native_tasks" /
                                 (name + ".json")).read_bytes()
                          for name in originals})

    def test_budget_exceeded_before_outputs(self):
        with self.assertRaisesRegex(mod.ContextBlocked, "CONTEXT_BUDGET_EXCEEDED"):
            run(task_spec(), budget=1000, persist=False)

    def test_existing_ex6_ex7_records_not_modified(self):
        files = [ROOT / "pilot/worker_v08/native_tasks/ex6.json",
                 ROOT / "pilot/worker_v08/native_tasks/ex7.json"]
        original = [p.read_bytes() for p in files]
        for task, name in zip(original, ("ex6", "ex7")):
            with self.assertRaisesRegex(mod.ContextBlocked, "HISTORICAL_TASK_IMMUTABLE"):
                run(json.loads(task), task_name=name)
        self.assertEqual(original, [p.read_bytes() for p in files])

    def test_write_scope_overlap_blocked(self):
        t = task_spec()
        t["write_path_patterns"] = [WRITE, ".lf/worker-context/ex8/profile.md"]
        with self.assertRaisesRegex(mod.ContextBlocked, "CONTEXT_WRITE_SCOPE_OVERLAP"):
            run(t)

    def test_store_and_replay_same_bytes_in_isolated_repo(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            init_git_fixture(root)
            enriched, artifacts = run(task_spec(), root=root, persist=True)
            for rel, raw in artifacts.items():
                self.assertEqual((root / rel).read_bytes(), raw)
            again, same = run(task_spec(), root=root, persist=True)
            self.assertEqual(enriched, again)
            self.assertEqual(artifacts, same)
            path = root / ".lf/worker-context/ex8/profile.md"
            path.write_bytes(b"tampered")
            with self.assertRaisesRegex(mod.ContextBlocked, "CONTEXT_OUTPUT_CONFLICT"):
                run(task_spec(), root=root, persist=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
