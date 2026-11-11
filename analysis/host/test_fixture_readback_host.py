"""F1 fixture-only readback and positive/negative deterministic execution."""
from __future__ import annotations
import copy
import hashlib
import json
import shutil
from pathlib import Path
import pytest

from analysis.host.fixture_readback_host import (
    DEFAULT_FIXTURES, FixtureBlocked, FixtureHost, TARGET,
)
from analysis.host.run_a1_a5_fixture import REQUEST, encoded, execute


def pinned_copy(tmp_path):
    dst = tmp_path / "sbx_auth_login"
    shutil.copytree(DEFAULT_FIXTURES, dst)
    return dst


def change_and_repin(root, name, update):
    path = root / name
    doc = json.loads(path.read_text(encoding="utf-8"))
    update(doc)
    raw = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(raw)
    pin = root / "SOURCE_PIN.json"
    manifest = json.loads(pin.read_text(encoding="utf-8"))
    next(x for x in manifest["files"] if x["file"] == name)["sha256"] = hashlib.sha256(raw).hexdigest()
    pin.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_chain_runs_real_a1_to_a5_with_six_effective_rules(tmp_path):
    out = execute(output_dir=tmp_path)
    stages = out["stages"]
    assert list(stages) == ["A1", "A2", "A3", "A4", "A5"]
    assert all(stage["status"] != "BLOCKED" for stage in stages.values())
    a3 = stages["A3"]
    valid = a3["policy_scope_clear_rule_candidates"]
    assert {x["rule_code"] for x in valid} == {
        "SBX-R-USER", "SBX-R-PASS", "SBX-R-LOCK", "SBX-R-HASH",
        "SBX-R-LOG", "SBX-R-ERR",
    }
    assert all(x["source_ref"].startswith("supabase://lf_ops.reglas/") for x in valid)
    assert all(x["runtime_implementation_approved"] is False for x in valid)
    assert len(out["fixture_provenance"]) == 13
    assert all(x.startswith("fixture://sbx_auth_login/") and len(x.rsplit("@",1)[1]) == 64
               for x in out["fixture_provenance"].values())
    profiles = stages["A5"]["rule_profiles"]["rules"]
    approved = [row for row in profiles if row["implementation_scope"] == "APPROVED_SCOPE"]
    assert len(approved) == 6
    assert {row["rule_code"] for row in approved} == {row["rule_code"] for row in valid}
    assert all(row["rule_source_ref"].startswith("supabase://lf_ops.reglas/") for row in approved)
    assert stages["A5"]["rule_profiles"]["applicability_source_attested"] is False
    assert stages["A5"]["source_attested"] is False
    assert stages["A5"]["a6_allowed"] is False
    assert all((tmp_path / (s.lower()+".json")).is_file() for s in stages)


def test_pending_rule_not_promoted():
    a3 = execute()["stages"]["A3"]
    item = next(x for x in a3["excluded_rule_items"] if x["rule_code"] == "SBX-R-PENDING")
    assert item["exclusion_reason"] == "DECISION_PENDING"
    assert "SBX-R-PENDING" not in {x["rule_code"] for x in a3["policy_scope_clear_rule_candidates"]}


def test_candidate_with_alerts_excluded():
    a3 = execute()["stages"]["A3"]
    item = next(x for x in a3["excluded_rule_items"] if x["rule_code"] == "SBX-R-CAND")
    assert item["exclusion_reason"] == "RULE_NOT_VIGENTE"
    assert "PENDING_RULES_EXCLUDED_AS_USER_REQUESTED" in a3["scope_alerts"]


def test_derived_global_is_effective():
    a3 = execute()["stages"]["A3"]
    assert a3["counts"]["inherited_derived_global_vigente"] == 1
    item = next(x for x in a3["policy_scope_clear_rule_candidates"] if x["rule_code"] == "SBX-R-LOG")
    assert item["binding_source"] == "DERIVED_GLOBAL"


def test_missing_contract_policy_resolves_from_backup():
    a3 = execute()["stages"]["A3"]
    policy = a3["policy_resolution"]
    assert policy["supplemental_policy_source_refs"] == ["supabase://lf_ops.politicas_seguridad/71"]
    assert any(x["read_origin"] == "DIRECT_CANONICAL_POLICY_LOOKUP"
               for x in policy["approved_policy_objects"])
    dep = next(x for x in policy["rule_policy_dependencies"] if x["rule_code"] == "SBX-R-ERR")
    assert dep["eligible_for_implementation"] is True
    assert dep["status"] == "APPROVED_POLICY_AND_BINDING"


def test_empty_inventory_does_not_assert_zero_impact():
    a4 = execute()["stages"]["A4"]
    assert a4["status"] in ("PLANNED_BUILD_IMPACT_UNATTESTED", "IMPACT_UNKNOWN")
    assert a4["target_change_action"] == "CREATE"
    assert a4["no_impact_claimed"] is False
    assert a4["unresolved_material_impacts"]


@pytest.mark.parametrize("name", ["screen_contract.json", "effective_rules.json", "inventory.json"])
def test_missing_required_file_fails_closed(tmp_path, name):
    root = pinned_copy(tmp_path)
    (root / name).unlink()
    with pytest.raises(FixtureBlocked) as exc:
        FixtureHost(root).run(REQUEST)
    assert exc.value.code == "SBX_FIXTURE_MISSING:" + name


def test_changed_fixture_sha_fails_closed(tmp_path):
    root = pinned_copy(tmp_path)
    path = root / "effective_rules.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(FixtureBlocked) as exc:
        FixtureHost(root).run(REQUEST)
    assert exc.value.code == "SBX_FIXTURE_SHA256_MISMATCH:effective_rules.json"


def test_current_rule_without_valor_config_fails_closed(tmp_path):
    root = pinned_copy(tmp_path)
    def drop(row):
        row["valor_config"][0].pop("valor_config")
    change_and_repin(root, "direct_rules.json", drop)
    with pytest.raises(FixtureBlocked) as exc:
        FixtureHost(root).run(REQUEST)
    assert exc.value.code == "SBX_VIGENTE_VALOR_CONFIG_MISSING:SBX-R-USER"


def test_two_runs_byte_identical(tmp_path):
    x, y = tmp_path / "first", tmp_path / "second"
    a = execute(output_dir=x)
    b = execute(output_dir=y)
    assert encoded(a) == encoded(b)
    assert {p.name:p.read_bytes() for p in x.iterdir()} == {
        p.name:p.read_bytes() for p in y.iterdir()
    }


def test_forged_natural_language_request_not_interpreted():
    with pytest.raises(FixtureBlocked) as exc:
        FixtureHost().run("Crear otra pantalla no declarada")
    assert exc.value.code == "SBX_SEMANTIC_REQUEST_NOT_PRESTRUCTURED"
