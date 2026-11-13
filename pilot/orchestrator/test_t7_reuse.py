"""T7 offline catalogue and reuse guards; no fixture or hidden exam modifications."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

from analysis.host.request_catalog import resolve, CatalogueBlocked
from pilot.orchestrator.reuse_assessment import index, assess, ReuseBlocked
from pilot.worker_v08.reuse_guard import check, DuplicateComponent


def catalogue(tmp_path):
    base = tmp_path / "analysis/fixtures"
    for dirname, code in (("screen_one", "SCREEN-ONE"), ("screen_two", "SCREEN-TWO")):
        target = base / dirname
        target.mkdir(parents=True)
        (target / "SOURCE_PIN.json").write_text(json.dumps({"fixture_id": code}))


def test_catalogue_exact_screen_resolution(tmp_path):
    catalogue(tmp_path)
    assert resolve(tmp_path, b"Implement SCREEN-ONE")[0] == "SCREEN-ONE"
    with pytest.raises(CatalogueBlocked, match="PEDIDO_AMBIGUO"):
        resolve(tmp_path, b"Implement SCREEN-ONE and SCREEN-TWO")
    with pytest.raises(CatalogueBlocked, match="PEDIDO_AMBIGUO"):
        resolve(tmp_path, b"Build a screen without code")
    with pytest.raises(CatalogueBlocked, match="PANTALLA_NO_EN_CATALOGO"):
        resolve(tmp_path, b"Build SCREEN-ABSENT")


def source(tmp_path, rel, value):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    return {"path": rel, "sha256": hashlib.sha256(value.encode()).hexdigest()}


def test_index_exact_evidence_and_indeterminate_without_explicit_rule(tmp_path):
    source(tmp_path, "apps/time-service/src/main/java/demo/Service.java",
           'public class Worker {\n'
           '@PostMapping("/api/example")\n'
           'public String process(String input) { return "ok"; }\n'
           '// REQ-EXAMPLE\n}\n')
    catalogue = index(tmp_path)
    keys = {(x["kind"], x["key"]) for x in catalogue["entries"]}
    assert ("endpoint", "POST /api/example") in keys
    assert ("public_signature", "type:Worker") in keys
    assert ("implemented_rule", "REQ-EXAMPLE") in keys
    report = assess(catalogue, [{"requirement_id": "REQ-EXAMPLE",
                                 "source_requirement_id": "RULE-EXAMPLE"}])
    assert report["obligations"][0]["decision"] == "REUSE_AS_IS"
    with pytest.raises(ReuseBlocked, match="REUTILIZACION_INDETERMINADA"):
        assess(catalogue, [{"requirement_id": "REQ-UNKNOWN",
                            "source_requirement_id": "RULE-UNKNOWN"}])


def test_duplicate_endpoint_rejected(tmp_path):
    source(tmp_path, "apps/time-service/src/main/java/demo/Old.java",
           '@PostMapping("/api/example")\npublic class Old {}\n')
    patch = ('diff --git a/apps/time-service/src/main/java/demo/New.java '
             'b/apps/time-service/src/main/java/demo/New.java\n'
             '+@PostMapping("/api/example")\n')
    with pytest.raises(DuplicateComponent, match="DUPLICA_COMPONENTE_EXISTENTE:endpoint"):
        check(tmp_path, patch, [])


def test_copy_service_with_renamed_class_same_public_signature_rejected(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public class Existing {\n'
                   'public String check(String input) { return input; }\n}\n')
    patch = ('diff --git a/apps/time-service/src/main/java/demo/New.java '
             'b/apps/time-service/src/main/java/demo/New.java\n'
             '+public class New {\n'
             '+public String changed(String input) { return input; }\n')
    with pytest.raises(DuplicateComponent, match="DUPLICA_COMPONENTE_EXISTENTE:signature"):
        check(tmp_path, patch, [entry])


def test_modify_reuse_context_rejected(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   "public class Existing {}")
    path = entry["path"]
    patch = f"diff --git a/{path} b/{path}\n+// modification\n"
    with pytest.raises(DuplicateComponent, match="DUPLICA_COMPONENTE_EXISTENTE:reuse_context"):
        check(tmp_path, patch, [entry])


def test_use_existing_service_without_modifying_or_copying_passes(tmp_path):
    entry = source(tmp_path, "apps/time-service/src/main/java/demo/Existing.java",
                   'public class Existing {\n'
                   'public String check(String input) { return input; }\n}\n')
    patch = ('diff --git a/apps/time-service/src/main/java/demo/New.java '
             'b/apps/time-service/src/main/java/demo/New.java\n'
             '+public class New {\n'
             '+private final Existing existing;\n')
    check(tmp_path, patch, [entry])
