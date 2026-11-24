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
            ["git", "-C", str(ROOT), "rev-parse", "refs/remotes/origin/main"], text=True).strip(),
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
    git(root, "symbolic-ref", "HEAD", "refs/heads/main")
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
    if "root" in overrides and (params["root"] / ".git").exists():
        scoped = copy.deepcopy(task)
        payload = scoped.get("task_spec", scoped)
        payload["base_head_sha"] = git(params["root"], "rev-parse", "HEAD")
        task = scoped
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
        self.assertEqual(a["task_spec"]["acceptance_commands"][-1], mod.format_command())
        api, _ = run(task_spec())
        self.assertEqual(api["context_path_patterns"], a["task_spec"]["context_path_patterns"])
        self.assertEqual(api["protected_path_patterns"], a["task_spec"]["protected_path_patterns"])

    def test_all_generated_context_paths_protected_and_read_only(self):
        task, artifacts = run(task_spec())
        expected = {".lf/worker-context/ex8/profile.md",
                    ".lf/worker-context/ex8/skills.md",
                    ".lf/worker-context/ex8/protocolo.md",
                    ".lf/worker-context/ex8/receipt.json"}
        self.assertEqual(set(artifacts), expected)
        self.assertIn(b"Modo continuo", artifacts[".lf/worker-context/ex8/protocolo.md"])
        self.assertTrue(expected.issubset(task["context_path_patterns"]))
        self.assertTrue(expected.issubset(task["protected_path_patterns"]))
        self.assertFalse(expected.intersection(task["write_path_patterns"]))
        receipt = json.loads(artifacts[".lf/worker-context/ex8/receipt.json"])
        self.assertEqual(receipt["source_pin_sha256"], hashlib.sha256((PINS / "SOURCE_PIN.json").read_bytes()).hexdigest())
        self.assertEqual([x["code"] for x in receipt["skills"]], ["SPRINGBOOT_EXP", "KAFKA_EXP"])
        self.assertEqual([x["priority"] for x in receipt["skills"]], [1, 2])
        self.assertIn("STD-BE-05", artifacts[".lf/worker-context/ex8/skills.md"].decode())
        self.assertFalse(receipt["production_authority"])

    def test_cp16_contract_and_infra_have_source_derived_rule_receipts(self):
        contract_policy = json.loads(
            (ROOT / "pilot/orchestrator/atomize_rules_v1.json").read_text())["contract_lot"]
        contract_path = contract_policy["write_path"].format(module="generated")
        allowlist = json.loads(
            (ROOT / "pilot/orchestrator/dependency_allowlist_v1.json").read_text())
        manifest_path = allowlist["targets"]["maven"]["manifest"]
        for area, path in (("CONTRATO", contract_path), ("INFRA", manifest_path)):
            scoped = task_spec()
            scoped["write_path_patterns"] = [path]
            result, artifacts = run(scoped, area=area, lot_paths=[path],
                                    task_name="cp16" + area.lower())
            prefix = ".lf/worker-context/cp16" + area.lower() + "/"
            rule = json.loads(artifacts[prefix + "lf_rules.receipt.json"])
            self.assertTrue(rule["rule_ids"])
            # The authoritative assembly hash is immutable; only the
            # Worker-facing copy may redact vendor-detected example literals.
            meta = json.loads(artifacts[prefix + "receipt.json"])[
                "lf_rules_worker_safety"]
            self.assertEqual(rule["assembled_sha256"], meta["source_sha256"])
            self.assertEqual(meta["worker_sha256"],
                hashlib.sha256(artifacts[prefix + "lf_rules.md"]).hexdigest())
            self.assertTrue(meta["vendor_secret_scanner_passed"])
            from programming_agent_runner.worker_secrets import secret_text_reason
            self.assertIsNone(secret_text_reason(
                artifacts[prefix + "lf_rules.md"].decode("utf-8")))
            self.assertEqual(result["protected_path_patterns"].count(
                prefix + "lf_rules.md"), 1)
            self.assertNotIn(prefix + "lf_rules.md", result["write_path_patterns"])
        self.assertEqual(
            json.loads(artifacts[".lf/worker-context/cp16infra/lf_rules.receipt.json"])
            ["selected_stack"], "spring-boot")

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
            import shutil
            config_source = ROOT / "pilot/config"
            config_target = root / "pilot/config"
            (config_target / "projects").mkdir(parents=True, exist_ok=True)
            shutil.copy2(config_source / "active_project.json", config_target / "active_project.json")
            shutil.copy2(config_source / "projects/sandbox.json", config_target / "projects/sandbox.json")
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
            self.assertEqual(len(artifacts), 6)
            prefix = ".lf/worker-context/cp14fresh/"
            self.assertIn(prefix + "lf_rules.md", artifacts)
            self.assertIn(prefix + "lf_rules.receipt.json", artifacts)
            lf_receipt = json.loads(artifacts[prefix + "lf_rules.receipt.json"])
            self.assertTrue(lf_receipt["rule_ids"])
            rule_safety = json.loads(artifacts[prefix + "receipt.json"])[
                "lf_rules_worker_safety"]
            self.assertEqual(lf_receipt["assembled_sha256"],
                             rule_safety["source_sha256"])
            self.assertEqual(hashlib.sha256(
                artifacts[prefix + "lf_rules.md"]).hexdigest(),
                rule_safety["worker_sha256"])
            from programming_agent_runner.worker_secrets import secret_text_reason
            self.assertIsNone(secret_text_reason(
                artifacts[prefix + "lf_rules.md"].decode("utf-8")))
            self.assertIn(prefix + "lf_rules.md", enriched["context_path_patterns"])
            self.assertIn(prefix + "lf_rules.md", enriched["protected_path_patterns"])
            self.assertNotIn(prefix + "lf_rules.md", enriched["write_path_patterns"])

    def test_native_fail_closed_paths_sha_historic_and_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            import shutil
            target = root / "pilot/config"
            (target / "projects").mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "pilot/config/active_project.json", target / "active_project.json")
            shutil.copy2(ROOT / "pilot/config/projects/sandbox.json", target / "projects/sandbox.json")
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

    def test_context_artifacts_pass_real_staged_git_diff_check(self):
        # The registration bytes must be mergeable by sandbox_train_merge.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init_git_fixture(root)
            _task, artifacts = run(task_spec(), root=root, persist=True)
            profile = artifacts[".lf/worker-context/ex8/profile.md"]
            self.assertTrue(profile.endswith(b"\n"))
            self.assertFalse(profile.endswith(b"\n\n"))
            receipt = json.loads(artifacts[".lf/worker-context/ex8/receipt.json"])
            self.assertEqual(receipt["profile"]["sha256"], hashlib.sha256(profile).hexdigest())
            self.assertEqual(receipt["context_sha256"]["profile.md"],
                             hashlib.sha256(profile).hexdigest())
            mod.assert_generated_context_clean(artifacts)
            git(root, "add", "--", *artifacts)
            result = subprocess.run(["git", "diff", "--cached", "--check"],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_synthetic_registered_profile_receipt_consistent(self):
        # Exercise the real assembler and offline capture, independent of
        # any live request or retained registration.
        from export_task_pack import export
        from programming_agent_runner.hashutil import source_snapshot_sha256

        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            root = sandbox / "repo"
            root.mkdir()
            init_git_fixture(root)
            task = task_spec()
            task.update(task_id="LF-WORKER-NATIVE-SYNTHETIC-CONTEXT",
                        max_attempts=1, max_patch_bytes=60000,
                        max_changed_files=1, allow_deletions=False,
                        acceptance_commands=[{
                            "name": "visible",
                            "argv": ["python3", "-c", "print('ok')"],
                            "timeout_seconds": 15, "max_output_bytes": 1024,
                        }])
            enriched, artifacts = run(task, root=root, persist=True,
                                      task_name="syntheticcontext")
            git(root, "add", "--", *artifacts)
            git(root, "commit", "-qm", "Register synthetic context")
            enriched["base_head_sha"] = git(root, "rev-parse", "HEAD")
            enriched["source_snapshot_sha256"] = source_snapshot_sha256(root)
            spec_path = sandbox / "task.json"
            pack_path = sandbox / "task-pack.json"
            spec_path.write_bytes(mod.canonical(enriched))
            pack_sha = export(root, spec_path, pack_path)
            self.assertEqual(pack_sha, sha256_bytes(pack_path))
            folder = root / ".lf/worker-context/syntheticcontext"
            receipt = json.loads((folder / "receipt.json").read_bytes())
            pack = json.loads(pack_path.read_bytes())
            entries = pack["user_payload"]["workspace"]["files"]
            prefix = folder.relative_to(root).as_posix() + "/"
            context = [entry for entry in entries if entry["path"].startswith(prefix)]
            by_path = {entry["path"]: entry for entry in context}
            self.assertEqual(len(context), len(by_path))
            self.assertEqual(set(by_path), set(receipt["context_paths"]))
            self.assertEqual(set(by_path), set(artifacts))
            self.assertEqual(set(receipt["context_sha256"]) | {"receipt.json"},
                             {Path(path).name for path in by_path})
            for path, entry in by_path.items():
                with self.subTest(path=path):
                    raw = (root / path).read_bytes()
                    observed = hashlib.sha256(raw).hexdigest()
                    self.assertEqual(raw, artifacts[path])
                    self.assertFalse(entry["binary"])
                    self.assertEqual(entry["sha256"], observed)
                    self.assertEqual(entry["content"].encode("utf-8"), raw)
                    if Path(path).name != "receipt.json":
                        self.assertEqual(receipt["context_sha256"][Path(path).name],
                                         observed)
            self.assertEqual(receipt["profile"]["sha256"],
                             receipt["context_sha256"]["profile.md"])

    def test_assembled_markdown_normalization_and_all_artifact_fail_closed(self):
        pin, sources = mod.read_pins()
        modified = dict(sources)
        name = "prog_backend_exp/checklists/priority_checklist.md"
        modified[name] += b"   \n\n"
        profile, skills, _ids, _catalog = mod.build_material(modified, "lf_java", "BACKEND")
        for data in (profile, skills):
            self.assertTrue(data.endswith(b"\n"))
            self.assertFalse(data.endswith(b"\n\n"))
            self.assertFalse(any(line.endswith((b" ", b"\t", b"\r"))
                                 for line in data.splitlines()))
        with self.assertRaisesRegex(mod.ContextBlocked, "CONTEXT_OUTPUT_WHITESPACE"):
            mod.assert_generated_context_clean({"other.md": b"unsafe \n"})
        with self.assertRaisesRegex(mod.ContextBlocked, "CONTEXT_OUTPUT_WHITESPACE"):
            mod.assert_generated_context_clean({"other.md": b"end\n\n"})

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
