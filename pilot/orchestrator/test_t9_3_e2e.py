"""T9.3: synthetic approved handoff -> trusted T7 -> real PG selector LOTS_PLANNED."""
import json
import os
import subprocess
import sys
import re
from pathlib import Path

import pytest

from pilot.orchestrator.test_t72_dependencies import _scenario
from pilot.workflow_python_commands import commands
from pilot import train_handoff


FORMAT_CANARY_PATHS = (
    "apps/time-service/src/main/java/lf/sandbox/time/formatcanary/FormatCanaryController.java",
    "apps/time-service/src/main/java/lf/sandbox/time/formatcanary/FormatCanaryService.java",
)


def _prepare_format_canary_create_base(root):
    """Isolate CREATE in the disposable checkout, including its reuse ledger."""
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

    assert git("branch", "--show-current") == "main"
    assert not git("status", "--porcelain")
    git("rm", "--ignore-unmatch", "--", *FORMAT_CANARY_PATHS)
    # Once the real canary integrates, its attested registry entry must not
    # turn this independent CREATE scenario into REUSE_AS_IS (or stale proof).
    # Only the disposable copy and this exact target's entries are changed.
    registry = root / "pilot/registry/implemented.json"
    ledger = json.loads(registry.read_text(encoding="utf-8"))
    assert ledger["schema_version"] == "T7_IMPLEMENTED_REGISTRY_V1"
    original = ledger["entries"]
    ledger["entries"] = [
        row for row in original
        if "FORMAT-CANARY-VALIDATION" not in row["rule_codes"]
        and "REQ-FORMAT-CANARY-VALIDATION" not in row["requirement_ids"]
        and not any(item["path"] in FORMAT_CANARY_PATHS for item in row["files"])
    ]
    if ledger["entries"] != original:
        registry.write_text(json.dumps(ledger, sort_keys=True, separators=(",", ":")) + "\n",
                            encoding="utf-8")
        git("add", "--", "pilot/registry/implemented.json")
    changed = git("diff", "--cached", "--name-only").splitlines()
    assert set(changed) <= {*FORMAT_CANARY_PATHS, "pilot/registry/implemented.json"}
    if changed:
        git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-m", "test: isolate format canary CREATE base")
    base = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", base)
    assert not git("status", "--porcelain")
    assert not git("ls-tree", "-r", "--name-only", base, "--", *FORMAT_CANARY_PATHS)
    assert all(not (root / path).exists() for path in FORMAT_CANARY_PATHS)
    return base


@pytest.mark.parametrize("existing", [(), (FORMAT_CANARY_PATHS[1],), FORMAT_CANARY_PATHS])
def test_format_canary_create_base_isolates_existing_components(tmp_path, existing):
    # An isolated Git repository proves the preparation works before and
    # after integration, independent of the disposable SQL selector.
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    git("init", "-b", "main")
    sentinel = tmp_path / "unrelated.txt"
    sentinel.write_text("preserve\n", encoding="utf-8")
    for rel in existing:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("synthetic previously integrated component\n", encoding="utf-8")
    unrelated = {"rule_codes": ["OTHER"], "requirement_ids": ["REQ-OTHER"],
                 "files": [{"path": "unrelated.txt"}]}
    entry = {"rule_codes": ["FORMAT-CANARY-VALIDATION"],
             "requirement_ids": ["REQ-FORMAT-CANARY-VALIDATION"],
             "files": [{"path": rel} for rel in existing]}
    registry = tmp_path / "pilot/registry/implemented.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"schema_version": "T7_IMPLEMENTED_REGISTRY_V1",
                                    "entries": [unrelated, entry] if existing else [unrelated]}),
                        encoding="utf-8")
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-m", "test: initial synthetic source")
    before = git("rev-parse", "HEAD")
    base = _prepare_format_canary_create_base(tmp_path)
    assert (base != before) == bool(existing)
    assert base == git("rev-parse", "refs/remotes/origin/main")
    assert sentinel.read_text(encoding="utf-8") == "preserve\n"
    assert json.loads(registry.read_text(encoding="utf-8"))["entries"] == [unrelated]
    assert all(not (tmp_path / path).exists() for path in FORMAT_CANARY_PATHS)
    assert _prepare_format_canary_create_base(tmp_path) == base


@pytest.mark.skipif(
    os.environ.get("SELECTOR_EXP_DISPOSABLE_DB") != "YES"
    or os.environ.get("ATOMIZE_T1_SELECTOR") != "YES"
    or not os.environ.get("SELECTOR_EXP_TEST_DSN"),
    reason="Requires shared disposable selector setup")
def test_synthetic_trusted_handoff_to_t7_lots_planned(tmp_path):
    # A separate synthetic 13-file screen and local Git repository:
    # never reads, changes or replays the actual request #167.
    package, _, _, _, _ = _scenario(
        tmp_path, adds_rule=True, attested=True, backend_only=True)
    assert package["package_readiness_candidate"] == "READY_CANDIDATE"
    slug = "t72-after"
    folder = tmp_path / "pilot/runs" / slug
    assert (folder / "request.md").exists()
    # T10 report renders provenance from the request's actual metadata, not
    # inferred author/issue/date. The temporary fixture supplies it explicitly.
    (folder / "request_meta.json").write_text(json.dumps({
        "author": "synthetic-bot", "issue": 987654,
        "date": "2026-11-14T00:00:00Z"
    }), encoding="utf-8")

    # Same published registry contract as T7, empty for this isolated synthetic
    # repository. Never import any historical real request or user registry.
    registry = tmp_path / "pilot/registry/implemented.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({
        "schema_version": "T7_IMPLEMENTED_REGISTRY_V1", "entries": []
    }), encoding="utf-8")

    # Route decision uses the same versioned map that Train uses.
    mapping = json.loads(train_handoff.MAP.read_text(encoding="utf-8"))
    assert train_handoff.route("lf/request/req-987654", mapping)[0]["workflow"] == "t7-request.yml"

    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                                   text=True).strip()
    # Extract the executable form from the REAL T7 YAML, not a parallel
    # function call. Substituting only temporary fixture values preserves the
    # exact interpreter/module/argument contract.
    repo = Path(__file__).resolve().parents[2]
    workflow = repo / ".github/workflows/t7-request.yml"
    scripts = commands(workflow)
    assert ("wrapper", "pilot/orchestrator/t7_entry.py") in scripts
    source = workflow.read_text(encoding="utf-8")
    assert "python3 -m pilot.workflow_entrypoint pilot/orchestrator/t7_entry.py --root ." in source
    # Exact workflow executable + script. Only fixture arguments are replaced.
    argv = [sys.executable, "-m", "pilot.workflow_entrypoint",
            "pilot/orchestrator/t7_entry.py",
            "--root", str(tmp_path), "--request-id", slug,
            "--base-head-sha", base]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    completed = subprocess.run(argv, cwd=repo, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=120)
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout.strip().splitlines()[-1])
    assert output["status"] == "LOTS_PLANNED", output
    assert (folder / "ANALYSIS_REPORT.md").is_file()
    state = json.loads((folder / "state.json").read_text(encoding="utf-8"))
    lots = json.loads((folder / "lots.json").read_text(encoding="utf-8"))
    assert state["stage"] == "LOTS_PLANNED"
    assert len(lots["lots"]) >= 1 and output["lots"] == len(lots["lots"])
    assert all(lot["write_paths"] for lot in lots["lots"])
    assert (folder / "chain_plan.json").is_file() or (
        tmp_path / "pilot/orchestrator/chain_plans" / (slug + ".json")).is_file()


@pytest.mark.skipif(
    os.environ.get("SELECTOR_EXP_DISPOSABLE_DB") != "YES"
    or os.environ.get("ATOMIZE_T1_SELECTOR") != "YES"
    or not os.environ.get("SELECTOR_EXP_TEST_DSN"),
    reason="Requires shared disposable selector setup")
def test_format_canary_original_route_single_backend(tmp_path):
    """Actual T7 on an isolated full source checkout and the pinned real SQL selector."""
    import hashlib
    import shutil
    repo = Path(__file__).resolve().parents[2]
    root = tmp_path / "repo"
    subprocess.run(["git", "clone", "--local", "--no-hardlinks", "--no-checkout",
                    str(repo), str(root)], check=True, capture_output=True)
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                   text=True).strip()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    git("checkout", "--detach", base)
    # Only this disposable repository: local main simulates an authorized
    # source commit; no remote write or actual issue is made.
    git("switch", "-C", "main", base)
    base = _prepare_format_canary_create_base(root)
    slug = "req-9999579"
    folder = root / "pilot/runs" / slug
    folder.mkdir(parents=True)
    phrase = "Implementa DEMO-FORMAT-CANARY"
    (folder / "request.md").write_text(phrase, encoding="utf-8")
    (folder / "request_meta.json").write_text(json.dumps({
        "author": "synthetic-fixture-test", "issue": 9999579,
        "date": "2026-11-26T00:00:00Z"}), encoding="utf-8")
    from analysis.host.request_catalog import resolve
    code, fixture = resolve(root, phrase.encode())
    assert code == "DEMO-FORMAT-CANARY"
    pin = json.loads((fixture / "SOURCE_PIN.json").read_text())
    assert pin["simulation_only"] is True
    assert hashlib.sha256((fixture / "source.json").read_bytes()).hexdigest() == pin["sha256"]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    argv = [sys.executable, "-m", "pilot.workflow_entrypoint",
            "pilot/orchestrator/t7_entry.py", "--root", str(root),
            "--request-id", slug, "--base-head-sha", base]
    completed = subprocess.run(argv, cwd=repo, env=env, text=True,
                               capture_output=True, timeout=120)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    output = json.loads(completed.stdout.strip().splitlines()[-1])
    assert output["status"] == "LOTS_PLANNED" and output["lots"] == output["tasks"] == 1
    def read(name):
        return json.loads((folder / name).read_text(encoding="utf-8"))
    package = read("analysis.json")
    rid = "REQ-FORMAT-CANARY-VALIDATION"
    assert package["simulation_mode"] == "SIMULATED_SANDBOX_ONLY"
    assert [r["requirement_id"] for r in package["requirements"]] == [rid]
    assert [f["execution_area"] for f in package["material_fronts"]] == ["BACKEND"]
    reuse = read("reuse_assessment.json")["obligations"]
    assert [(r["requirement_id"], r["decision"]) for r in reuse] == [(rid, "BUILD_NEW")]
    atoms = read("atomized_inputs.json")["atoms"]
    assert len(atoms) == 1 and atoms[0]["area"] == "BACKEND" and not atoms[0]["depends_on"]
    lots = read("lots.json")
    assert len(lots["lots"]) == 1 and lots["worker_invoked"] is False
    lot = lots["lots"][0]
    assert lot["area"] == "BACKEND" and lot["depends_on"] == []
    assert lot["requirement_ids"] == [rid]
    assert lot["profile_code"] == "PERFIL-PROG-BACKEND-SPRING-EXP"
    paths = list(FORMAT_CANARY_PATHS)
    assert sorted(lot["write_paths"]) == paths
    assert all(not (root / path).exists() for path in paths)
    chain_path = root / "pilot/orchestrator/chain_plans" / (slug + ".json")
    plan = json.loads(chain_path.read_text())
    assert len(plan["bindings"]) == 1 and plan["bindings"][0]["lot_id"] == lot["id"]
    binding = plan["bindings"][0]
    template = json.loads((root / binding["template_path"]).read_text())
    # Verify the ordinary context-registration inputs and command derivation,
    # without producing a fake holdout, native registration, or task-pack.
    sys.path.insert(0, str(repo / "pilot/worker_v08"))
    from register_task_context import read_pins, build_material, select_area, format_command
    from pilot.orchestrator.native_lot_binding import map_profile, real_write_paths
    assert real_write_paths(root, lot["area"], lot["write_paths"]) == paths
    assert map_profile(lot["profile_code"], lot["area"])
    selected = select_area(paths, lot["area"])
    assert selected == "BACKEND"
    _, files = read_pins()
    _, _, skills, _ = build_material(files, "lf_java", selected)
    assert "SPRINGBOOT_EXP" in [s["code"] for s in skills]
    command = format_command()
    assert command == {
        "name": "std-be-05-spotless-check",
        "argv": ["mvn", "-B", "-q", "-f", "apps/time-service/pom.xml", "spotless:check"],
        "timeout_seconds": 600, "max_output_bytes": 16000}
    # Persist only generated planning evidence in the existing CI artifact
    # directory. The synthetic test runs never touch the real repository.
    if os.environ.get("T1_ARTIFACT_DIR"):
        dest = Path(os.environ["T1_ARTIFACT_DIR"]) / "format-canary"
        shutil.copytree(folder, dest)
        shutil.copyfile(chain_path, dest / "chain_plan.json")
        (dest / "format-command-derived.json").write_text(json.dumps(
            {"area": selected, "profile": lot["profile_code"],
             "skill_codes": [s["code"] for s in skills], "command": command,
             "registration_created": False}, indent=2) + "\n", encoding="utf-8")
