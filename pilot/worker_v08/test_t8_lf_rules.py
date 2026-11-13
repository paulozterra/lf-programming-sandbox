"""T8 deterministic rules and adversarial checks, no API/model/oracle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pilot.worker_v08.lf_rule_context import material
from pilot.worker_v08.lf_rule_gate import evaluate, coverage, catalog, RuleGateBlocked

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("area",("BACKEND","FRONTEND","DATA","CONTRATO","INFRA"))
def test_all_domains_and_rules_derive_from_authoritative_skill_catalog(area):
    content,receipt=material(area)
    assert content
    assert receipt["rule_ids"]
    assert receipt["assembled_sha256"]==hashlib.sha256(content).hexdigest()
    assert set(receipt["rule_ids"]).issubset(catalog())
    if receipt["selected_stack"]:
        manifest=json.loads((ROOT/"standards/skills"/receipt["selected_stack"]/"skill.json").read_text())
        assert receipt["selected_domains"]==manifest["domains"]
    assert len(receipt["rule_ids"])==len(set(receipt["rule_ids"]))


@pytest.mark.parametrize("path,added,expected",[
    ("frontend/src/app/example.tsx", "const response = await fetch('/api/example')", "STD-FE-04"),
    ("backend/src/main/java/lf/example/Example.java", 'logger.info("password " + password);', "STD-GEN-04"),
    ("frontend/src/app/config.ts", 'const apiKey = "1234567890secret";', "STD-GEN-03"),
    ("apps/time-service/src/main/resources/db/migration/INVALID.sql","CREATE TABLE sample (id int);","STD-DB-09"),
])
def test_new_lines_fail_by_rule_code(path,added,expected):
    patch=f"diff --git a/{path} b/{path}\n+{added}\n"
    result=evaluate(patch,[expected])
    assert result["status"]=="FAIL"
    assert any(r["rule_id"]==expected for r in result["violations"])
    assert coverage(result)[0]["coverage"]=="NO_VERIFICADO"
    assert coverage(result)[0]["reason"]=="DETECCION_PARCIAL_NO_PRUEBA_CUMPLIMIENTO"


def test_legacy_unchanged_lines_are_not_rejected():
    patch=("diff --git a/frontend/src/app/example.tsx b/frontend/src/app/example.tsx\n"
           " const old = fetch('/legacy');\n+const value = generatedClient();\n")
    result=evaluate(patch,["STD-FE-04"])
    assert result["status"]=="PASS"


def test_unverifiable_rules_stay_unverified_not_hidden_by_claim():
    actual=catalog()
    unknown=[r for r in actual if r not in
             ("STD-GEN-03","STD-GEN-04","STD-GEN-05","STD-FE-04","STD-BE-04","STD-DB-09")]
    assert unknown
    report=evaluate("diff --git a/frontend/src/a.ts b/frontend/src/a.ts\n+const ok = true\n",unknown[:2])
    assert all(item["coverage"]=="NO_VERIFICADO" for item in coverage(report))
    assert all(item["reason"]=="SIN_VERIFICADOR_COMPLETO" for item in coverage(report))
    with pytest.raises(RuleGateBlocked,match="LF_HIDDEN_COVERAGE_NOT_ATTESTED"):
        coverage(report,hidden_coverage=[unknown[0]])


def test_invalid_domain_rule_or_patch_blocks_not_defaults():
    with pytest.raises(RuleGateBlocked,match="LF_RULES_UNRESOLVED"):
        evaluate("",["UNREGISTERED-RULE"])
    with pytest.raises(RuleGateBlocked,match="LF_PATCH_PATH_INVALID"):
        evaluate("+fetch('/test')",["STD-FE-04"])


def test_waiver_must_have_explicit_reference():
    path="frontend/src/app/example.tsx"
    bad=f"diff --git a/{path} b/{path}\n+// eslint-disable-next-line\n"
    forged=f"diff --git a/{path} b/{path}\n+// eslint-disable-next-line no-console -- WAIVER-9999\n"
    permitted="standards/tests/fixtures/suppressions/good.ts"
    good=(f"diff --git a/{permitted} b/{permitted}\n"
          "+// eslint-disable-next-line no-console -- WAIVER-0001 diagnóstico\n")
    assert evaluate(bad,["STD-GEN-05"])["status"]=="FAIL"
    assert evaluate(forged,["STD-GEN-05"])["status"]=="FAIL"
    assert evaluate(good,["STD-GEN-05"])["status"]=="PASS"


def test_catalogue_cases_resolved_without_case_literals():
    catalogue=ROOT/"analysis/fixtures"
    names=sorted(p.parent for p in catalogue.glob("*/SOURCE_PIN.json"))
    assert len(names)>=2
    from analysis.host.request_catalog import resolve
    schema_versions = set()
    for source in names:
        manifest = json.loads((source/"SOURCE_PIN.json").read_text("utf-8"))
        schema_versions.add(manifest["schema_version"])
        code = manifest["fixture_id"]
        selected_code, selected_path = resolve(ROOT, ("Cambiar pantalla " + code).encode())
        assert selected_code == code and selected_path == source
        for area in ("BACKEND", "FRONTEND", "DATA"):
            assert material(area)[1]["rule_ids"]
    # Covers both the original and the second-screen fixture format, without
    # pinning a screen's proper name, route, module or business requirement.
    assert {"SBX_FIXTURE_PIN_V1","SOURCE_SCREEN_PIN_V1"}.issubset(schema_versions)
    # A synthetic route has no special code path or per-screen allowance.
    assert evaluate("diff --git a/frontend/src/app/new/page.tsx b/frontend/src/app/new/page.tsx\n"
                    "+export default function Page() { return null; }\n",
                    ["STD-FE-04"])["status"]=="PASS"


@pytest.mark.parametrize("area,source,addition,should_pass",[
    ("FRONTEND","frontend/src/app/widget.tsx",
     "const answer = await fetch('/api/data');",False),
    ("FRONTEND","frontend/src/app/widget.tsx",
     "const answer = await apiClient.get();",True),
    ("BACKEND","apps/time-service/src/main/java/lf/sandbox/time/Widget.java",
     'logger.debug("password=" + password);',False),
    ("BACKEND","apps/time-service/src/main/java/lf/sandbox/time/Widget.java",
     'private String password = "hardcoded-value";',False),
])
def test_native_run_dry_lf_rule_proposal_no_model(tmp_path,area,source,addition,should_pass):
    import subprocess,sys
    receipt=material(area)[1]
    receipt_path=tmp_path/"receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    patch=f"diff --git a/{source} b/{source}\n+{addition}\n"
    proposal=tmp_path/"proposal.json"
    proposal.write_text(json.dumps({"schema_version":1,"summary":"offline",
                                    "patch":patch,"changed_paths":[source]}))
    cmd=[sys.executable,str(ROOT/"pilot/worker_v08/native_run.py"),
         "dry-run-lf-rules","--control",str(ROOT),"--task","synthetic",
         "--proposal",str(proposal),"--rule-receipt",str(receipt_path)]
    result=subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert (result.returncode==0)==should_pass,(result.stdout,result.stderr)
    assert ("NATIVE_LF_RULE_DRY_RUN_BLOCKED" in result.stderr)==(not should_pass)


def test_format_is_machine_verified_only_with_pinned_successful_visible_command():
    from pilot.worker_v08.lf_rule_gate import verified_visible_commands
    table=[{"rule_id":"STD-BE-05","coverage":"NO_VERIFICADO",
            "reason":"SIN_VERIFICADOR_COMPLETO"}]
    command={"name":"std-be-05-spotless-check",
             "argv":["mvn","-f","apps/time-service/pom.xml","spotless:check"]}
    visible={"attempts":[{"acceptance":[{
        **command,"status":"PASS","returncode":0}]}]}
    updated=verified_visible_commands(table,visible,[command])
    assert updated[0]["coverage"]=="MACHINE"
    assert updated[0]["evidence"]=="PINNED_VISIBLE_ACCEPTANCE_COMMAND"
    assert verified_visible_commands(table,visible,[{"name":command["name"],
             "argv":["false"]}])==table
    failed={"attempts":[{"acceptance":[{**command,"status":"FAIL"}]}]}
    assert verified_visible_commands(table,failed,[command])==table


def test_offline_api_and_native_browser_toolchain_pin_parity():
    import re
    api=(ROOT/".github/workflows/worker-pilot.yml").read_text("utf-8")
    native=(ROOT/".github/workflows/worker-native.yml").read_text("utf-8")
    for exact in ("playwright==1.56.0", "--with-deps --only-shell chromium",
                  "/tmp/lf-playwright-browsers", "/tmp/lf-playwright-runtime"):
        assert exact in api and exact in native
    assert "source/pilot/worker_v08/test_t8_lf_rules.py" in api
    assert re.search(r"node-version:\s*[\"']?22",api)
    assert re.search(r"java-version:\s*[\"']?21",api)


@pytest.mark.parametrize("area", ("BACKEND", "FRONTEND", "DATA"))
def test_manifest_domains_change_context_exactly_without_manual_lists(tmp_path, area):
    import shutil
    from pilot.worker_v08.lf_rule_context import RuleContextBlocked, select_stack
    initial, original = material(area)
    stack = original["selected_stack"]
    assert original["selected_domains"] == json.loads(
        (ROOT/"standards/skills"/stack/"skill.json").read_text())["domains"]
    standards = tmp_path/"standards"
    skill_dir = standards/"skills"/stack
    skill_dir.mkdir(parents=True)
    shutil.copy2(ROOT/"standards/catalog.json", standards/"catalog.json")
    (standards/"glossary").mkdir()
    shutil.copy2(ROOT/"standards/glossary/base.json", standards/"glossary/base.json")
    shutil.copy2(ROOT/"standards/skills"/stack/"SKILL.md", skill_dir/"SKILL.md")
    manifest=json.loads((ROOT/"standards/skills"/stack/"skill.json").read_text())
    # Remove a secondary, catalog-backed domain, so the resolver still
    # has its selected stack but must regenerate different rule content.
    candidates=[d for d in manifest["domains"] if d!="STD-GEN"]
    assert len(candidates)<len(manifest["domains"])
    manifest["domains"]=candidates
    (skill_dir/"skill.json").write_text(json.dumps(manifest))
    modified, receipt = material(area, standards_root=standards)
    assert receipt["selected_domains"]==candidates
    assert receipt["rule_ids"] != original["rule_ids"]
    assert modified != initial
    with pytest.raises(RuleContextBlocked,match="DOMINIOS_NO_RESUELTOS"):
        material(area, skill_codes=["unmatched_stack"], standards_root=standards)
