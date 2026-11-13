"""T7: registry precedence, stale SHA, mixed extension and native dry-run."""
from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from pilot.orchestrator.reuse_assessment import assess, index, ReuseBlocked

ROOT = Path(__file__).resolve().parents[2]


def source(root: Path, path: str, content: str):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content)
    return {"path": path, "sha256": hashlib.sha256(content.encode()).hexdigest()}


def ledger(*rows):
    return {"schema_version": "T7_IMPLEMENTED_REGISTRY_V1",
            "source_main_sha": "a" * 40, "entries": list(rows)}


def record(ref, *, codes=None, endpoints=None):
    return {
        "request": "sample", "lot": "SOL-001", "area": "BACKEND",
        "requirement_ids": ["REQ-EXAMPLE"], "rule_codes": codes or ["RULE-EXAMPLE"],
        "endpoints": endpoints or ["GET /api/demo"],
        "files": [ref], "merge_sha": "b" * 40, "status": "ATTESTED", "reasons": [],
    }


def test_registered_rule_reuse_and_new_rule_on_same_endpoint_extends(tmp_path):
    ref = source(tmp_path, "apps/time-service/src/main/java/demo/Demo.java",
                 '@GetMapping("/api/demo")\npublic class Demo {}\n')
    doc = ledger(record(ref))
    rows = [
        {"requirement_id": "REQ-EXAMPLE", "source_requirement_id": "RULE-EXAMPLE"},
        {"requirement_id": "REQ-NEW", "source_requirement_id": "RULE-NEW",
         "endpoint": "GET /api/demo"},
    ]
    result = assess(index(tmp_path), rows, registry=doc, root=tmp_path)
    assert [item["decision"] for item in result["obligations"]] == ["REUSE_AS_IS", "EXTEND"]
    assert result["obligations"][0]["reuse_context"] == [ref]
    assert result["obligations"][1]["write_paths"] == [ref["path"]]


def test_absent_from_registry_and_index_builds_new_with_negative_evidence(tmp_path):
    result = assess(index(tmp_path), [{"requirement_id": "REQ-NOTES-ONE",
                                       "source_requirement_id": "NOTES-RULE-ONE"}],
                    registry=ledger(), root=tmp_path)
    assert result["obligations"][0]["decision"] == "BUILD_NEW"
    assert result["obligations"][0]["evidence"]["kind"] == "sin coincidencias"


def test_registry_sha_drift_blocks_not_reuse(tmp_path):
    ref = source(tmp_path, "apps/time-service/src/main/java/demo/Demo.java",
                 '@GetMapping("/api/demo")\npublic class Demo {}\n')
    changed = {**ref, "sha256": "0" * 64}
    with pytest.raises(ReuseBlocked, match="REUTILIZACION_INDETERMINADA"):
        assess(index(tmp_path), [{"requirement_id": "REQ-EXAMPLE",
                                  "source_requirement_id": "RULE-EXAMPLE"}],
               registry=ledger(record(changed)), root=tmp_path)


def test_mixed_synthetic_chooses_existing_endpoint_from_index(tmp_path):
    for name, route in (("A", "/api/a"), ("B", "/api/b"), ("C", "/api/c")):
        source(tmp_path, f"apps/time-service/src/main/java/demo/{name}.java",
               f'@GetMapping("{route}")\npublic class {name} {{}}\n')
    candidates = [e for e in index(tmp_path)["entries"] if e["kind"] == "endpoint"]
    existing = random.Random(2039).choice(candidates)
    doc = ledger(record({"path": existing["path"], "sha256": existing["sha256"]},
                        codes=["RULE-RANDOM"], endpoints=[existing["key"]]))
    rows = [
        {"requirement_id": "REQ-REUSED", "source_requirement_id": "RULE-RANDOM"},
        {"requirement_id": "REQ-MORE", "source_requirement_id": "RULE-ADDED",
         "endpoint": existing["key"]},
    ]
    decision = assess(index(tmp_path), rows, registry=doc, root=tmp_path)
    assert [x["decision"] for x in decision["obligations"]] == ["REUSE_AS_IS", "EXTEND"]


def test_native_run_dry_mode_real_proposal_envelopes(tmp_path):
    rel = "apps/time-service/src/main/java/demo/Existing.java"
    ref = source(tmp_path, rel,
                 'public class Existing {\npublic String check(String x) { return x; }\n}\n')
    reuse = tmp_path / "reuse.json"
    reuse.write_text(json.dumps([ref]))
    program = ROOT / "pilot/worker_v08/native_run.py"
    def submit(name, added):
        patch = (
            "diff --git a/apps/time-service/src/main/java/demo/New.java "
            "b/apps/time-service/src/main/java/demo/New.java\n"
            + "\n".join("+" + line for line in added.splitlines()) + "\n")
        proposal = tmp_path / (name + ".json")
        proposal.write_text(json.dumps({
            "schema_version": 1, "summary": "offline test", "patch": patch,
            "changed_paths": ["apps/time-service/src/main/java/demo/New.java"]}))
        return subprocess.run([sys.executable, str(program), "dry-run-reuse",
                    "--control", str(ROOT), "--task", "sample",
                    "--source", str(tmp_path), "--proposal", str(proposal),
                    "--reuse-context", str(reuse)],
                   capture_output=True, text=True, timeout=30)
    allowed = submit("reuse", "public class New {\nprivate final Existing delegate;\n}")
    assert allowed.returncode == 0, allowed.stderr
    assert "PASS_UNAUTHENTICATED" in allowed.stdout
    denied = submit("duplicate",
        "public class Copy {\npublic String copied(String x) { return x; }\n}")
    assert denied.returncode != 0
    assert "DUPLICA_COMPONENTE_EXISTENTE" in denied.stderr


def test_real_second_screen_through_existing_a1_a9(tmp_path):
    from analysis.host.run_a1_a9_fixture import run_f4
    fixtures = ROOT / "analysis/fixtures/demo_notes_edit"
    source_doc = json.loads((fixtures / "source.json").read_text("utf-8"))
    target = source_doc["target_ref"]
    slug = "t7-second-screen"
    folder = tmp_path / "pilot/runs" / slug
    folder.mkdir(parents=True)
    request = f"Crear pantalla {target} con las reglas vigentes\n"
    (folder / "request.md").write_text(request, encoding="utf-8")
    result = run_f4(tmp_path, slug=slug, fixtures=fixtures)
    assert result["package"]["schema_version"] == "ANALYSIS_IMPLEMENTATION_PACKAGE_V1"
    assert result["state"]["stage"] == "INTAKE_ACCEPTED"
    assert result["package"]["request_context"]["intent"] == request.strip()
