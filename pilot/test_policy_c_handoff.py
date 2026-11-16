#!/usr/bin/env python3
"""T17.2: static proof every Policy C branch can trigger a post-CI handoff."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from pilot.auto_integrate import BRANCH_RULES, BOT_BRANCH_PREFIXES, accepted_branch_kind
from pilot.policy_c_handoff import should_notify

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github/workflows/ci.yml"
POLICY = ROOT / ".github/workflows/auto-integrate.yml"


def events(document: dict) -> dict:
    value = document.get("on", document.get(True, {}))
    return value if isinstance(value, dict) else {}


def check_coverage(ci: dict, policy: dict, rules=BRANCH_RULES) -> list[str]:
    jobs = ci.get("jobs") if isinstance(ci, dict) else None
    jobs = jobs if isinstance(jobs, dict) else {}
    classifier = jobs.get("standards-catalog", {})
    notifier = jobs.get("notify-policy-c", {})
    steps = classifier.get("steps", [])
    steps = steps if isinstance(steps, list) else []
    source = (classifier.get("outputs") or {}).get("policy_c_notify")
    step = next((s for s in steps if isinstance(s, dict)
                 and s.get("id") == "policy_c_branch"), {})
    if_expr = notifier.get("if") or ""
    if not isinstance(if_expr, str):
        if_expr = ""
    dependencies = notifier.get("needs", [])
    if isinstance(dependencies, str):
        dependencies = [dependencies]
    ci_events, policy_events = events(ci), events(policy)
    handoff_workflow = policy.get("jobs", {}).get("evaluate", {}).get("steps", [])
    trusted_dispatch = any(
        isinstance(s, dict) and
        "pilot/auto_integrate.py" in str(s.get("run", ""))
        for s in handoff_workflow)
    wired = (
        source == "${{ steps.policy_c_branch.outputs.accepted }}"
        and "standards-catalog" in dependencies
        and "needs.standards-catalog.outputs.policy_c_notify == 'true'" in if_expr
        and "github.event_name == 'workflow_dispatch'" in if_expr
        and "always()" in if_expr
        and "policy_c_handoff.py" in str(step.get("run", ""))
        and "$GITHUB_OUTPUT" in str(step.get("run", ""))
        and step.get("env", {}).get("POLICY_C_BRANCH") == "${{ github.ref_name }}"
        and "workflow_dispatch" in ci_events
        and "workflow_dispatch" in policy_events
        and trusted_dispatch
        and "gh workflow run auto-integrate.yml" in str(notifier.get("steps", []))
    )
    errors = []
    for kind, prefix, pattern in rules:
        # Construct examples from the policy's actual prefix and common
        # valid suffixes. No second allowlist or copied list of prefixes.
        examples = ([prefix + "req186contrato1-" + "a" * 12,
                     prefix + "pack-req186contrato1-" + "b" * 12,
                     prefix + "route-python-req186contrato1-" + "c" * 12]
                    if kind == "registration" else
                    [prefix + suffix for suffix in ("a", "a" * 12, "req-1", "1")])
        examples = [b for b in examples if re.fullmatch(pattern, b)]
        if (not wired or not examples or
                not all(accepted_branch_kind(branch) == kind
                        and should_notify(branch) for branch in examples)):
            errors.append("POLICY_C_SIN_DISPARO:" + prefix)
    if tuple(item[1] for item in rules) != BOT_BRANCH_PREFIXES:
        errors.extend("POLICY_C_SIN_DISPARO:" + prefix for _, prefix, _ in rules)
    return sorted(set(errors))


def test_real_workflows_cover_all_policy_c_branches() -> None:
    assert not check_coverage(
        yaml.safe_load(CI.read_text(encoding="utf-8")),
        yaml.safe_load(POLICY.read_text(encoding="utf-8")))


def test_missing_handoff_is_detected_per_policy_prefix() -> None:
    ci = yaml.safe_load(CI.read_text(encoding="utf-8"))
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    ci["jobs"]["notify-policy-c"]["if"] = "false"
    assert check_coverage(ci, policy) == sorted(
        "POLICY_C_SIN_DISPARO:" + prefix for prefix in BOT_BRANCH_PREFIXES)


def test_missing_classification_is_detected() -> None:
    ci = yaml.safe_load(CI.read_text(encoding="utf-8"))
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    ci["jobs"]["standards-catalog"]["steps"] = [
        step for step in ci["jobs"]["standards-catalog"]["steps"]
        if step.get("id") != "policy_c_branch"]
    assert len(check_coverage(ci, policy)) == len(BOT_BRANCH_PREFIXES)


def test_registration_and_all_accepted_branches_share_policy_rule() -> None:
    branch = "lf/native-registration/req186contrato1-2f384485df66"
    assert accepted_branch_kind(branch) == "registration"
    assert should_notify(branch)
    assert not should_notify("feat/t17-2-policy-c-notify-coverage")


def main() -> int:
    from sys import stderr
    ci = yaml.safe_load(CI.read_text(encoding="utf-8"))
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    errors = check_coverage(ci, policy)
    for error in errors:
        print(error, file=stderr)
    if errors:
        return 1
    print("POLICY_C_DISPARO_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
