"""Reject secrets-context references from ANY workflow with a push event."""
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"

def _has_push_event(source: str) -> bool:
    lines=source.splitlines()
    for i,line in enumerate(lines):
        if line.startswith("on:"):
            rhs=line[3:].strip()
            if re.search(r"(^|[,\\[ ])push([,\\] ]|$)",rhs):
                return True
            if rhs:
                return False
            for nxt in lines[i+1:]:
                if nxt and not nxt.startswith((" ","\\t","#")):
                    break
                if re.match(r"^  push\\s*:",nxt):
                    return True
    return False

def assert_push_workflow_no_secrets(path: Path) -> None:
    source=path.read_text(encoding="utf-8")
    if _has_push_event(source) and re.search(r"secrets\\s*(?:\\.|\\[)",source):
        raise AssertionError("PUSH_WORKFLOW_SECRETS_FORBIDDEN:"+path.name)

def test_all_repository_workflows():
    paths=list(WORKFLOWS.glob("*.yml"))+list(WORKFLOWS.glob("*.yaml"))
    assert paths
    for path in paths:
        assert_push_workflow_no_secrets(path)

@pytest.mark.parametrize("header",["on:\\n  push:\\n","on: push\\n","on: [push, workflow_dispatch]\\n"])
def test_push_secret_rejected(tmp_path,header):
    path=tmp_path/"unsafe.yml"
    path.write_text(header.replace("\\n","\n")+"jobs:\n  a:\n    steps:\n      - run: echo ${{ secrets.LEAK }}\n")
    with pytest.raises(AssertionError,match="PUSH_WORKFLOW_SECRETS_FORBIDDEN"):
        assert_push_workflow_no_secrets(path)

def test_workflow_run_secret_allowed(tmp_path):
    path=tmp_path/"trusted.yml"
    path.write_text("on:\n  workflow_run:\n    workflows: [LF Native proposal trigger]\n"
                    "jobs:\n  a:\n    steps:\n      - run: echo ${{ secrets.SECRET }}\n")
    assert_push_workflow_no_secrets(path)

def test_push_without_secrets_allowed(tmp_path):
    path=tmp_path/"trigger.yml"
    path.write_text("on:\n  push:\n    branches: ['lf/native-proposal/**']\n")
    assert_push_workflow_no_secrets(path)
