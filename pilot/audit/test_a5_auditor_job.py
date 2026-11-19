"""A5: the deterministic gates around the event-driven auditor."""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import auditor_job as aj  # noqa: E402

INPUT = {"schema_version": "LF_DEEP_AUDIT_INPUT_V2", "evidence_destination": "pilot/runs/req-9/audit"}


def issue(**over):
    base = {"state": "open", "user": {"login": "github-actions[bot]"}, "labels": [{"name": "audit-request"}],
            "title": "[AUDIT][lf] req-9",
            "body": "<!-- audit-request:req-9 -->\ntexto\n```json\n" + json.dumps(INPUT) + "\n```"}
    base.update(over)
    return base


def test_route_issue_is_accepted():
    assert aj.parse_issue(issue()) == ("req-9", "lf", INPUT)


@pytest.mark.parametrize("over,code", [
    ({"user": {"login": "someone"}}, "AUDITOR_ISSUE_NOT_FROM_ROUTE"),
    ({"state": "closed"}, "AUDITOR_ISSUE_NOT_OPEN"),
    ({"labels": []}, "AUDITOR_ISSUE_NOT_LABELLED"),
    ({"title": "req-9"}, "AUDITOR_ISSUE_MALFORMED"),
    ({"body": "<!-- audit-request:req-9 --><!-- audit-request:req-8 -->```json\n{}\n```"}, "AUDITOR_ISSUE_MALFORMED"),
    ({"body": "<!-- audit-request:req-9 -->\n```json\n" + json.dumps(dict(INPUT, evidence_destination="pilot/x"))
      + "\n```"}, "AUDITOR_INPUT_MISMATCH"),
    ({"body": "<!-- audit-request:../x -->\n```json\n{}\n```"}, "AUDITOR_ISSUE_MALFORMED"),
])
def test_untrusted_or_malformed_issues_are_rejected(over, code):
    with pytest.raises(aj.JobError, match=code):
        aj.parse_issue(issue(**over))


def test_model_writes_outside_its_folder_are_caught():
    assert aj.changed_outside("req-9", ["pilot/runs/req-9/audit/draft.json",
                                        "pilot/runs/req-9/audit/evidence/x.json"]) == []
    assert aj.changed_outside("req-9", ["pilot/runs/req-9/audit/a", ".github/workflows/x.yml",
                                        "pilot/runs/req-99/audit/a"]) == [".github/workflows/x.yml",
                                                                          "pilot/runs/req-99/audit/a"]


def test_prompt_template_keeps_the_model_without_github():
    text = (HERE / "auditor_prompt.md").read_text()
    assert "{request}" in text and "{skill_dir}" in text and "No tienes acceso a GitHub" in text


def test_workflow_strips_github_credentials_from_the_model_step():
    wf = (HERE.parents[1] / ".github/workflows/audit-auditor.yml").read_text()
    step = wf.split("- name: Audit with Claude", 1)[1].split("- name:", 1)[0]
    assert "unset GH_TOKEN GITHUB_TOKEN" in step and "github.token" not in step
    assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in step
    assert "persist-credentials: false" in wf and "github-actions[bot]" in wf
