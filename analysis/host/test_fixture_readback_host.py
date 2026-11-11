"""F1 offline real A1-A5 execution, five traps, fail-closed inputs and determinism."""
import importlib.util
import json
import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "analysis/host/fixture_readback_host.py"
spec = importlib.util.spec_from_file_location("sbx_f1_host_tests", P)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def folder(tmp_path):
    target = tmp_path / "data"
    shutil.copytree(host.FIXTURES, target)
    return target


def test_positive_full_chain():
    out = host.run()
    assert out.get("status") != "BLOCKED", out.get("blocking_codes")
    assert set(out["stages"]) == {"A1", "A2", "A3", "A4", "A5"}
    a3, a4, a5 = (out["stages"][k] for k in ("A3", "A4", "A5"))
    assert a5["status"] != "BLOCKED"
    allowed = a3["policy_scope_clear_rule_candidates"]
    codes = {r["rule_code"] for r in allowed}
    assert codes == {"SBX-RULE-CREDENTIALS", "SBX-RULE-LOCKOUT", "SBX-RULE-BCRYPT",
                     "SBX-RULE-ERROR-GENERIC", "SBX-RULE-SESSION", "SBX-RULE-NO-PASSWORD-LOGS"}
    assert all(r["source_ref"].startswith("supabase://lf_ops.reglas/") for r in allowed)
    assert a3["counts"]["inherited_derived_global_vigente"] == 1
    assert a3["counts"]["policy_objects_resolved"] == 1
    assert any(p["read_origin"] == "DIRECT_CANONICAL_POLICY_LOOKUP"
               for p in a3["policy_resolution"]["approved_policy_objects"])
    assert a4["target_change_action"] == "CREATE"
    assert a4["status"] == "PLANNED_BUILD_IMPACT_UNATTESTED"
    assert not a4["no_impact_claimed"] and a4["unresolved_material_impacts"]
    assert out["source_attested"] is False and out["authority_verified"] is False
    assert all(x.startswith("fixture://sbx_auth_login/") and "@" in x
               for x in out["source_provenance"].values())


def test_pending_and_candidate_alert_excluded():
    out = host.run()
    assert out.get("status") != "BLOCKED", out.get("blocking_codes")
    a3 = out["stages"]["A3"]
    excluded = {x["rule_code"]: x for x in a3["excluded_rule_items"]}
    assert excluded["SBX-RULE-PENDING"]["exclusion_reason"] == "DECISION_PENDING"
    assert excluded["SBX-RULE-ALERT"]["exclusion_reason"] == "RULE_NOT_VIGENTE"
    assert a3["counts"]["inherited_derived_global_vigente"] == 1
    assert not a3["policy_deferred_rule_items"]


def test_missing_screen_contract(tmp_path):
    d = folder(tmp_path)
    (d / "screen_contract.json").unlink()
    assert host.run(folder=d)["blocking_codes"] == ["SBX_FIXTURE_MISSING:screen_contract.json"]


def test_missing_effective_rules(tmp_path):
    d = folder(tmp_path)
    (d / "effective_rules.json").unlink()
    assert host.run(folder=d)["blocking_codes"] == ["SBX_FIXTURE_MISSING:effective_rules.json"]


def test_tampered_sha(tmp_path):
    d = folder(tmp_path)
    p = d / "policies.json"
    p.write_bytes(p.read_bytes() + b" ")
    assert host.run(folder=d)["blocking_codes"] == ["SBX_FIXTURE_SHA256_MISMATCH:policies.json"]


def test_vigente_without_valor_config(tmp_path, monkeypatch):
    d = folder(tmp_path)
    p = d / "effective_rules.json"
    value = json.loads(p.read_text(encoding="utf8"))
    value["payload"]["rules"][0]["config"] = {}
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf8")
    # Re-pin in a trusted TEST-ONLY manifest, then exercise semantic checks.
    pins = json.loads(host.HASHES.read_text(encoding="utf8"))
    pins["effective_rules.json"] = hashlib.sha256(p.read_bytes()).hexdigest()
    trust = tmp_path / "trusted_pin_override.json"
    trust.write_text(json.dumps(pins), encoding="utf8")
    monkeypatch.setattr(host, "HASHES", trust)
    assert host.run(folder=d)["blocking_codes"] == [
        "SBX_VIGENTE_RULE_VALUE_CONFIG_MISSING:SBX-RULE-CREDENTIALS"]


def test_missing_inventory_is_not_empty(tmp_path):
    d = folder(tmp_path)
    (d / "inventory.json").unlink()
    assert host.run(folder=d)["blocking_codes"] == ["SBX_FIXTURE_MISSING:inventory.json"]


def test_determinism_bytes():
    first, second = host.run(), host.run()
    assert first.get("status") != "BLOCKED", first.get("blocking_codes")
    assert json.dumps(first, ensure_ascii=False, sort_keys=True).encode() == (
        json.dumps(second, ensure_ascii=False, sort_keys=True).encode())
