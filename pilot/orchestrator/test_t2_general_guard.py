"""T2 generality guard outside Analysis. Legacy tests are not production code."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
EXACT_FIXTURE = re.compile(r"(?<![A-Za-z0-9])(?:SBX|DEMO)-[A-Za-z0-9_-]+")
CONCRETE_RULE = re.compile(r"REQ-(?:SBX|DEMO)-[A-Za-z0-9_-]+")
NEW_PRODUCTION = (
    "pilot/orchestrator/atomize.py",
    "pilot/orchestrator/contract_generate.py",
    "pilot/orchestrator/contract_validate.py",
    "pilot/orchestrator/generate_chain.py",
    "pilot/orchestrator/plan_lots.py",
    "analysis/host/fixture_readback_host.py",
    "analysis/host/run_a1_a9_fixture.py",
    "analysis/host/request_catalog.py",
    "pilot/orchestrator/reuse_assessment.py",
    "pilot/worker_v08/reuse_guard.py",
)
CASE_ROUTE = re.compile(r"(?i)(?:/|\\b)(?:login|notes)(?:/|\\.|-|\\b)")


def test_no_concrete_fixture_code_in_pilot_and_workflows():
    roots = (ROOT/"pilot/orchestrator", ROOT/"pilot/worker_v08", ROOT/"analysis/host")
    files = [
        p for start in roots for p in start.rglob("*.py")
        if not p.name.startswith("test_") and "tests" not in p.parts
    ]
    files += list((ROOT/".github/workflows").glob("*.yml"))
    files += list((ROOT/"contracts").glob("*.openapi.yaml"))
    errors=[]
    for file in sorted(files):
        data=file.read_text(encoding="utf-8")
        for pattern in (EXACT_FIXTURE, CONCRETE_RULE):
            if pattern.search(data):
                errors.append(str(file.relative_to(ROOT))+":"+pattern.search(data).group())
    assert not errors, "T2_CONCRETE_CASE_IN_PRODUCTION:"+",".join(errors)


def test_new_t2_pipeline_contains_no_case_specific_paths():
    errors=[]
    for path in NEW_PRODUCTION:
        text=(ROOT/path).read_text(encoding="utf-8")
        if CASE_ROUTE.search(text):
            errors.append(path)
    assert not errors, "T2_CASE_PATH_IN_NEW_PRODUCTION:"+",".join(errors)


def test_guard_recognizes_both_fixture_prefixes():
    assert EXACT_FIXTURE.search("SBX-ANY-RULE")
    assert EXACT_FIXTURE.search("DEMO-ANY-SCREEN")
    assert CASE_ROUTE.search("/login/") and CASE_ROUTE.search("/notes/")
