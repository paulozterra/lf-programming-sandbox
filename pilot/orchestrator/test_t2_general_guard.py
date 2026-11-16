"""T2 generality guard outside Analysis. Legacy tests are not production code."""
from pathlib import Path
import re

from pilot.orchestrator.native_write_scope import PRODUCT_ROOTS

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


def production_route_sources(root: Path) -> list[Path]:
    """Scan only control-plane implementation, never T24 product outputs."""
    files = [
        p for relative in ("pilot", "analysis/host")
        for p in (root / relative).rglob("*.py")
        if p.is_file() and not p.name.startswith("test_")
        and "tests" not in p.parts
    ]
    files.extend((root / ".github/workflows").glob("*.yml"))
    files.extend((root / ".github/workflows").glob("*.yaml"))
    # Keep the T24 single authority for exclusions, rather than an invented
    # list of individual product directories.
    return sorted(p for p in files
                  if not p.relative_to(root).as_posix().startswith(tuple(PRODUCT_ROOTS)))


def concrete_case_violations(root: Path) -> list[str]:
    errors = []
    for file in production_route_sources(root):
        data = file.read_text(encoding="utf-8")
        for pattern in (EXACT_FIXTURE, CONCRETE_RULE):
            match = pattern.search(data)
            if match:
                errors.append(str(file.relative_to(root)) + ":" + match.group())
    return errors


def test_no_concrete_fixture_code_in_pilot_and_workflows():
    assert not concrete_case_violations(ROOT), (
        "T2_CONCRETE_CASE_IN_PRODUCTION:" + ",".join(concrete_case_violations(ROOT)))


def test_product_openapi_case_codes_are_not_an_implementation_fixture(tmp_path):
    contract = tmp_path / "contracts/sample.openapi.yaml"
    contract.parent.mkdir(parents=True)
    contract.write_text("operationId: SBX-REM-LIST\n"
                        "x-requirement: REQ-SBX-PRIORITY\n", "utf-8")
    assert concrete_case_violations(tmp_path) == []


def test_literal_case_in_pilot_implementation_still_fails(tmp_path):
    control = tmp_path / "pilot/orchestrator/example.py"
    control.parent.mkdir(parents=True)
    control.write_text("SCREEN_CODE = 'SBX-REM-LIST'\n", "utf-8")
    assert concrete_case_violations(tmp_path) == [
        "pilot/orchestrator/example.py:SBX-REM-LIST"]



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
