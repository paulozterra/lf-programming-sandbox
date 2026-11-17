"""T37: the proof tool only accepts a single BLOCKED failure of a route tool."""
import pytest

import route_tool_defect as r

REC = {"task_spec": {"acceptance_commands": [
    {"name": "contract-source-coverage",
     "argv": ["lf-python", "pilot/orchestrator/contract_validate.py", "--x"]},
    {"name": "build", "argv": ["mvn", "package"]}]}}


def _fb(*rows):
    return {"kind": "VISIBLE_ACCEPTANCE_ONLY", "commands": list(rows)}


def test_code_parsing():
    assert r.code_of("BLOCKED:CONTRACT_FIELD_COVERAGE_MISSING:email,password\\n") == \
        "CONTRACT_FIELD_COVERAGE_MISSING"
    assert r.code_of("Traceback (most recent call last)") is None


def test_route_tool_failure_is_accepted():
    cmd, code = r.failing_tool(_fb({"name": "contract-source-coverage", "status": "FAIL",
                                    "reason": "EXIT_NONZERO",
                                    "stderr_excerpt": "BLOCKED:CONTRACT_YAML_INVALID\\n"}), REC)
    assert code == "CONTRACT_YAML_INVALID" and cmd["argv"][1].endswith("contract_validate.py")


@pytest.mark.parametrize("fb", [
    _fb({"name": "build", "status": "FAIL", "reason": "EXIT_NONZERO", "stderr_excerpt": "x"}),
    _fb({"name": "contract-source-coverage", "status": "FAIL", "reason": "EXIT_NONZERO",
         "stderr_excerpt": "BLOCKED:A\\n"},
        {"name": "build", "status": "FAIL", "reason": "EXIT_NONZERO", "stderr_excerpt": "x"}),
    _fb({"name": "contract-source-coverage", "status": "FAIL", "reason": "TIMEOUT",
         "stderr_excerpt": "BLOCKED:A\\n"}),
    {"kind": "HIDDEN", "commands": []},
])
def test_non_route_failures_are_rejected(fb):
    with pytest.raises(r.ToolDefectBlocked):
        r.failing_tool(fb, REC)
