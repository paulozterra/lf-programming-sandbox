"""F1 offline fixture contract tests, separate from unmodified A1-A5 suites."""
import copy
import json
import shutil
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/host"))
from fixture_readback_host import FIXTURES, FILES, HASHES, TARGET, run, load, FixtureBlocked


def _clone(tmp_path):
    folder = tmp_path / "sbx_auth_login"
    shutil.copytree(FIXTURES, folder)
    return folder


def test_complete_a1_a5_fixture():
    result = run()
    assert result.get("status") != "BLOCKED", result
    stages = result["stages"]
    assert list(stages) == ["A1", "A2", "A3", "A4", "A5"]
    assert stages["A5"]["status"] != "BLOCKED"
    a3 = stages["A3"]
    assert len(a3["policy_scope_clear_rule_candidates"]) == 6
    actual = {r["rule_code"] for r in a3["policy_scope_clear_rule_candidates"]}
    assert actual == {"SBX-RULE-CREDENTIALS", "SBX-RULE-LOCKOUT",
                      "SBX-RULE-BCRYPT", "SBX-RULE-ERROR-GENERIC",
                      "SBX-RULE-SESSION", "SBX-RULE-NO-PASSWORD-LOGS"}
    assert all(r["source_ref"].startswith("supabase://") for r in a3["policy_scope_clear_rule_candidates"])
    assert len(result["source_provenance"]) == len(FILES)
    assert all(r.startswith("fixture://sbx_auth_login/") and len(r.rsplit("@", 1)[-1]) == 64
               for r in result["source_provenance"].values())
    assert all(stages[k]["source_attested"] is False for k in ("A3", "A4", "A5"))


def test_pending_and_alerts_excluded():
    a3 = run()["stages"]["A3"]
    exclusions = {x["rule_code"]: x["exclusion_reason"] for x in a3["excluded_rule_items"]}
    assert exclusions["SBX-RULE-PENDING"] == "DECISION_PENDING"
    assert exclusions["SBX-RULE-ALERT"] == "RULE_NOT_VIGENTE"


def test_global_inheritance_present():
    a3 = run()["stages"]["A3"]
    assert a3["counts"]["inherited_derived_global_vigente"] == 1
    assert "SBX-RULE-NO-PASSWORD-LOGS" in {r["rule_code"] for r in a3["policy_scope_clear_rule_candidates"]}


def test_policy_fallback_resolved():
    a3 = run()["stages"]["A3"]
    assert a3["policy_resolution"]["supplemental_policy_source_refs"] == [
        "supabase://lf_ops.politicas_seguridad/900081"]
    assert not a3["policy_resolution"]["rule_codes_policy_dependency_pending"]


def test_empty_inventory_never_no_impact():
    a4 = run()["stages"]["A4"]
    assert a4["target_change_action"] == "CREATE"
    assert a4["no_impact_claimed"] is False
    assert a4["unresolved_material_impacts"]
    assert a4["status"] in ("PLANNED_BUILD_IMPACT_UNATTESTED", "IMPACT_UNKNOWN")


@pytest.mark.parametrize("missing,code", [
    ("screen_contract.json", "SBX_FIXTURE_MISSING:screen_contract.json"),
    ("effective_rules.json", "SBX_FIXTURE_MISSING:effective_rules.json"),
    ("inventory.json", "SBX_FIXTURE_MISSING:inventory.json"),
])
def test_missing_file_blocks(tmp_path, missing, code):
    folder = _clone(tmp_path)
    (folder / missing).unlink()
    assert run(folder=folder)["blocking_codes"] == [code]


def test_tampered_fixture_blocks(tmp_path):
    folder = _clone(tmp_path)
    with (folder / "screen_contract.json").open("ab") as fd:
        fd.write(b" ")
    assert run(folder=folder)["blocking_codes"] == ["SBX_FIXTURE_SHA256_MISMATCH:screen_contract.json"]


def test_vigente_rule_missing_config_blocks(tmp_path, monkeypatch):
    import hashlib
    import fixture_readback_host as host
    folder = _clone(tmp_path)
    row = json.loads((folder / "effective_rules.json").read_text())
    row["payload"]["rules"][0].pop("config")
    target = folder / "effective_rules.json"
    target.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    # Explicit test-only re-pin: validates the semantic gate after integrity.
    pins = json.loads(HASHES.read_text(encoding="utf-8"))
    pins["effective_rules.json"] = hashlib.sha256(target.read_bytes()).hexdigest()
    trusted_pin = tmp_path / "trusted_pin_override.json"
    trusted_pin.write_text(json.dumps(pins), encoding="utf-8")
    monkeypatch.setattr(host, "HASHES", trusted_pin)
    assert run(folder=folder)["blocking_codes"] == [
        "SBX_VIGENTE_RULE_VALUE_CONFIG_MISSING:SBX-RULE-CREDENTIALS"]


def test_two_runs_byte_exact():
    encode = lambda x: (json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    assert encode(run()) == encode(run())


def test_pin_inventory_complete():
    pins = {name: item["sha256"] for name, item in json.loads(HASHES.read_text())["files"].items()}
    assert len(pins) == len(FILES) == 13
    assert set(pins) == set(FILES)
    for name in FILES:
        payload, ref = load(name)
        assert ref.endswith("@" + pins[name])
