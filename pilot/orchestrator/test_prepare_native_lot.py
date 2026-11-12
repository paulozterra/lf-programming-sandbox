"""Offline lifecycle-order proof: no GitHub push, model, oracle or merge."""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_native_lot


def test_single_command_register_commit_seal_commit_export(tmp_path):
    events = []
    reg = {"context_paths": [".lf/worker-context/demo/profile.md"],
           "native_task": "pilot/worker_v08/native_tasks/demo.json"}
    def fake_git(root, *args):
        if args == ("branch", "--show-current"):
            return "feat/test"
        if args == ("status", "--porcelain"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return "f" * 40
        return ""
    def fake_choose(root, request, lot, proofs):
        events.append("choose")
        return (Path("run"), {"id": lot, "area": "BACKEND"},
                {"area": "BACKEND"}, ["apps/time-service/src/main/java/X.java"])
    def fake_register(*args):
        events.append("register")
        return reg
    def fake_commit(*args):
        events.append("commit")
        return ("a" if events.count("commit") == 1 else "b") * 40
    def fake_seal(*args):
        events.append("seal")
        return {"native_task": reg["native_task"]}
    def fake_export(*args):
        events.append("export")
        return {"base_head_sha": "a" * 40,
                "status": "PROPOSAL_REQUEST_ONLY"}
    with (patch.object(prepare_native_lot, "ROOT", tmp_path),
          patch.object(prepare_native_lot, "git", side_effect=fake_git),
          patch.object(prepare_native_lot, "choose", side_effect=fake_choose),
          patch.object(prepare_native_lot, "register_lot", side_effect=fake_register),
          patch.object(prepare_native_lot, "_commit_exact", side_effect=fake_commit),
          patch.object(prepare_native_lot, "seal_lot", side_effect=fake_seal),
          patch.object(prepare_native_lot, "export_lot", side_effect=fake_export)):
        result = prepare_native_lot.run(
            tmp_path, "request", "L1", "demo", {}, {}, [])
    assert events == ["choose", "register", "commit", "seal", "commit", "export"]
    assert result["registration_commit_sha"] == "a" * 40
    assert result["seal_commit_sha"] == "b" * 40
    assert result["result"] == "CP35_PREPARED_NO_MODEL_NO_PUSH"
