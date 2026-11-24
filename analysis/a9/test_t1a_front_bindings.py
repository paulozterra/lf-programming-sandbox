"""T1-A: source-bound front partition and explicit fail-closed cases."""
import pytest
from analysis.a9.front_bindings import partition, FrontBindingGap
from analysis.host.run_a1_a9_fixture import make_rule_sources
from analysis.host.run_a1_a8_fixture import run_f3


def packet():
    source = run_f3()
    requirements = [{"source_requirement_id": r["requirement_id"],
                     "requirement_id": "REQ-" + r["requirement_id"],
                     "evidence_refs": r["evidence_refs"]}
                    for r in source["a6"]["requirements"]]
    sections = source["verified_screen_contract"]["value"]
    return source["a7"]["material_fronts"], requirements, sections, make_rule_sources()["effective"]


def test_login_two_areas_have_sourced_requirements():
    fronts, reqs, sections, rules = packet()
    active, excluded = partition(fronts, reqs, sections, rules,
                                 scope="SBX-AUTH-LOGIN", create_empty_inventory=True)
    assert [f["execution_area"] for f in active] == ["BACKEND", "FRONTEND"]
    assert len({f["front_id"] for f in active}) == 2
    assert active[0]["execution_area_source_ref"].endswith("#contract/errors/0")
    assert "#contract/visual/variants/" in active[1]["execution_area_source_ref"]
    for f in active:
        assert f["requirement_ids"] and f["source_ref"] in f["evidence_refs"]
    by_area = {f["execution_area"]: set(f["requirement_ids"]) for f in active}
    assert {"REQ-SBX-R-USER", "REQ-SBX-R-PASS", "REQ-SBX-R-ERR"} <= (
        by_area["BACKEND"] & by_area["FRONTEND"])
    assert any(x["reason"] == "NON_BLOCKING_GAP_EMPTY_INVENTORY_CREATE" for x in excluded)
    assert any(x["reason"] == "SOURCE_SECTION_HAS_NO_OBLIGATION" for x in excluded)


def test_a4_nonempty_inventory_fails_closed():
    fronts, reqs, sections, rules = packet()
    with pytest.raises(FrontBindingGap, match="A9_A4_DEPENDENCY_UNRESOLVED"):
        partition(fronts, reqs, sections, rules,
                  scope="SBX-AUTH-LOGIN", create_empty_inventory=False)


def test_required_field_without_requirement_fails_closed():
    fronts, reqs, sections, rules = packet()
    reqs = [r for r in reqs if r["evidence_refs"] != sections["fields"][0]["rule_refs"]]
    with pytest.raises(FrontBindingGap, match="A9_SECTION_RULE_WITHOUT_APPROVED_REQUIREMENT"):
        partition(fronts, reqs, sections, rules,
                  scope="SBX-AUTH-LOGIN", create_empty_inventory=True)


def test_empty_section_does_not_create_implementation():
    fronts, reqs, sections, rules = packet()
    active, excluded = partition(fronts, reqs, sections, rules,
                                 scope="SBX-AUTH-LOGIN", create_empty_inventory=True)
    excluded_ids = {f["front_id"] for f in excluded}
    assert all(f["front_id"] not in excluded_ids for f in active)
    assert not any(f["execution_area"] == "DATA" for f in active)


def synthetic_obligation_packet(config):
    ref = "fixture://synthetic/rule/one"
    req = {"source_requirement_id": "RULE-ONE", "requirement_id": "REQ-ONE",
           "evidence_refs": [ref], "scope_id": "SYNTHETIC",
           "outcome": "Persist and enforce a policy"}
    front = {"front_id": "F3-ONE", "candidate_ref": ref,
             "status": "REQUIRED", "evidence_refs": [ref],
             "simulation_mode": "SIMULATED_SANDBOX_ONLY"}
    sections = {"fields": [], "errors": [], "visual": {"variants": []},
                "rules": [{"source_ref": ref, "association_ref": ref + "/link"}]}
    rules = {"RULE-ONE": {"source_ref": ref, "categoria": "datos", "config": config}}
    return [front], [req], sections, rules


@pytest.mark.parametrize("areas", [[], ["DATA", "DATA"], ["UNKNOWN"], "DATA", [None]])
def test_invalid_declared_obligation_areas_block(areas):
    with pytest.raises(FrontBindingGap, match="A9_OBLIGATION_AREAS_INVALID"):
        partition(*synthetic_obligation_packet({"obligation_areas": areas}),
                  scope="SYNTHETIC", create_empty_inventory=True)


@pytest.mark.parametrize("config,expected", [
    ({}, ["DATA"]),
    ({"obligation_areas": ["DATA"]}, ["DATA"]),
    ({"obligation_areas": ["DATA", "BACKEND"]}, ["DATA", "BACKEND"]),
])
def test_synthetic_obligation_projection(config, expected):
    from analysis.a9.area_projection import project
    fronts, reqs, sections, rules = synthetic_obligation_packet(config)
    active, _ = partition(fronts, reqs, sections, rules,
                          scope="SYNTHETIC", create_empty_inventory=True)
    projected, active, scopes, _ = project("SYNTHETIC", reqs, active,
                                           readiness="READY_CANDIDATE")
    assert [f["execution_area"] for f in active] == expected
    assert len(scopes) == len(projected) == len(expected)
    assert projected[0]["requirement_id"] == "REQ-ONE"
    if len(expected) == 2:
        assert projected[1]["derived_from_requirement_id"] == "REQ-ONE"
        assert projected[1]["requirement_id"] == "REQ-ONE-BACKEND"
        assert projected[1]["evidence_refs"] == projected[0]["evidence_refs"]
