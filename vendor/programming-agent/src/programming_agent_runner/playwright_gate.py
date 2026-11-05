from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from .hashutil import sha256_json

PlaywrightStatus = Literal["PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"]
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BROWSER_ENGINES = {"chromium", "firefox", "webkit"}
_UI_TOKENS = ("frontend/", "web/", "ui/", ".tsx", ".jsx", ".vue", ".svelte")


class PlaywrightGateError(ValueError):
    """Raised when UI test applicability or execution identity is ambiguous."""


@dataclass(frozen=True)
class PlaywrightPlan:
    applicable: bool
    platform: str
    head_sha: str
    environment: str
    base_url: str | None
    playwright_version: str | None
    browser_engine: str | None
    browser_revision: str | None
    config_path: str | None
    config_sha256: str | None
    fixtures_sha256: str | None
    command: tuple[str, ...]
    changed_paths: tuple[str, ...]
    smoke_tests: tuple[str, ...]
    e2e_tests: tuple[str, ...]
    roles: tuple[str, ...]
    capture_on_failure: tuple[str, ...]
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def plan_sha256(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True)
class PlaywrightEvidence:
    status: PlaywrightStatus
    plan_sha256: str
    head_sha: str
    run_id: int | None
    job_id: int | None
    selected_tests: tuple[str, ...]
    executed: int
    passed: int
    failed: int
    artifacts: tuple[dict[str, Any], ...]
    reason: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ui_change_detected(paths: tuple[str, ...] | list[str]) -> bool:
    lowered = [path.lower() for path in paths]
    return any(any(token in path for token in _UI_TOKENS) for path in lowered)


def _strings(value: Any, field: str, maximum: int = 256) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise PlaywrightGateError(f"{field} must be an array with at most {maximum} strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or len(item.encode("utf-8")) > 4096:
            raise PlaywrightGateError(f"{field} contains invalid string")
        result.append(item)
    if len(set(result)) != len(result):
        raise PlaywrightGateError(f"{field} contains duplicates")
    return tuple(result)


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PlaywrightGateError(f"{field} must be lowercase SHA-256")
    return value


def playwright_plan_from_dict(value: Any) -> PlaywrightPlan:
    if not isinstance(value, dict):
        raise PlaywrightGateError("Playwright plan must be an object")
    applicable = value.get("applicable")
    if type(applicable) is not bool:
        raise PlaywrightGateError("applicable must be boolean")
    head = value.get("head_sha")
    if not isinstance(head, str) or _SHA40.fullmatch(head) is None:
        raise PlaywrightGateError("head_sha must be lowercase 40-hex")
    platform = value.get("platform")
    if platform not in {"web", "pwa", "native_mobile", "none"}:
        raise PlaywrightGateError("platform must be web, pwa, native_mobile or none")
    changed_paths = _strings(value.get("changed_paths", []), "changed_paths")
    if applicable and platform not in {"web", "pwa"}:
        raise PlaywrightGateError("Playwright applicable=true requires web or pwa platform")
    if not applicable:
        if ui_change_detected(changed_paths) and platform in {"web", "pwa"}:
            raise PlaywrightGateError("web UI change cannot declare Playwright NOT_APPLICABLE")
        return PlaywrightPlan(
            False, platform, head, str(value.get("environment") or "none"), None, None, None, None, None, None, None,
            (), changed_paths, (), (), (), (), str(value.get("reason") or "NO_WEB_UI_CHANGE"),
        )
    base_url = value.get("base_url")
    if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
        raise PlaywrightGateError("applicable plan requires explicit http(s) base_url")
    browser = value.get("browser_engine")
    if browser not in _BROWSER_ENGINES:
        raise PlaywrightGateError("browser_engine must be chromium, firefox or webkit")
    playwright_version = value.get("playwright_version")
    browser_revision = value.get("browser_revision")
    config_path = value.get("config_path")
    for item, field in (
        (playwright_version, "playwright_version"),
        (browser_revision, "browser_revision"),
        (config_path, "config_path"),
    ):
        if not isinstance(item, str) or not item:
            raise PlaywrightGateError(f"{field} is required")
    command = _strings(value.get("command", []), "command", maximum=32)
    if not command or command[0] not in {"npx", "npm", "pnpm", "yarn", "bunx"}:
        raise PlaywrightGateError("command must be explicit argv using a package runner")
    if "playwright" not in " ".join(command).lower() or "test" not in command:
        raise PlaywrightGateError("command must invoke playwright test")
    smoke = _strings(value.get("smoke_tests", []), "smoke_tests")
    e2e = _strings(value.get("e2e_tests", []), "e2e_tests")
    if not smoke and not e2e:
        raise PlaywrightGateError("applicable plan requires smoke_tests or e2e_tests")
    capture = _strings(value.get("capture_on_failure", ["screenshot", "trace", "video"]), "capture_on_failure")
    if not {"screenshot", "trace", "video"}.issubset(capture):
        raise PlaywrightGateError("capture_on_failure must include screenshot, trace and video")
    return PlaywrightPlan(
        True,
        platform,
        head,
        str(value.get("environment") or "test"),
        base_url,
        playwright_version,
        browser,
        browser_revision,
        config_path,
        _digest(value.get("config_sha256"), "config_sha256"),
        _digest(value.get("fixtures_sha256"), "fixtures_sha256"),
        command,
        changed_paths,
        smoke,
        e2e,
        _strings(value.get("roles", []), "roles"),
        capture,
        None,
    )


def select_tests(plan: PlaywrightPlan, risk: str) -> tuple[str, ...]:
    if not plan.applicable:
        return ()
    if risk.lower() in {"high", "critical"} or len(plan.changed_paths) > 10:
        return tuple(dict.fromkeys((*plan.smoke_tests, *plan.e2e_tests)))
    return plan.smoke_tests or plan.e2e_tests


def _artifacts(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise PlaywrightGateError("artifacts must be an array")
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or item.get("kind") not in {"screenshot", "trace", "video", "json", "junit", "html"}:
            raise PlaywrightGateError("artifact kind invalid")
        if not isinstance(item.get("path"), str) or not item["path"]:
            raise PlaywrightGateError("artifact path invalid")
        _digest(item.get("sha256"), "artifact.sha256")
        result.append(dict(item))
    return tuple(result)


def seal_playwright_evidence(plan: PlaywrightPlan, execution: Any, *, risk: str = "medium") -> PlaywrightEvidence:
    if not plan.applicable:
        reason = plan.reason or "NO_WEB_UI_CHANGE"
        payload: dict[str, Any] = {
            "status": "NOT_APPLICABLE",
            "plan_sha256": plan.plan_sha256,
            "head_sha": plan.head_sha,
            "run_id": None,
            "job_id": None,
            "selected_tests": [],
            "executed": 0,
            "passed": 0,
            "failed": 0,
            "artifacts": [],
            "reason": reason,
        }
        return PlaywrightEvidence(
            "NOT_APPLICABLE", plan.plan_sha256, plan.head_sha, None, None, (), 0, 0, 0, (), reason,
            sha256_json(payload),
        )
    if not isinstance(execution, dict):
        raise PlaywrightGateError("applicable Playwright plan requires execution object")
    expected_tests = select_tests(plan, risk)
    problems: list[str] = []
    if execution.get("head_sha") != plan.head_sha:
        problems.append("HEAD_MISMATCH")
    if execution.get("base_url") != plan.base_url or execution.get("environment") != plan.environment:
        problems.append("ENVIRONMENT_MISMATCH")
    for field in ("playwright_version", "browser_engine", "browser_revision", "config_sha256", "fixtures_sha256"):
        if execution.get(field) != getattr(plan, field):
            problems.append(f"{field.upper()}_MISMATCH")
    selected_raw = execution.get("selected_tests")
    selected: list[str]
    if (
        not isinstance(selected_raw, list)
        or not all(isinstance(item, str) for item in selected_raw)
        or tuple(selected_raw) != expected_tests
    ):
        problems.append("SELECTED_TESTS_MISMATCH")
        selected = []
    else:
        selected = list(selected_raw)
    counts: list[int] = []
    for field in ("executed", "passed", "failed"):
        value = execution.get(field)
        if type(value) is not int or value < 0:
            problems.append(f"{field.upper()}_INVALID")
            value = 0
        counts.append(value)
    executed, passed, failed = counts
    if executed != passed + failed or executed != len(selected):
        problems.append("TEST_COUNTS_INCOHERENT")
    artifacts = _artifacts(execution.get("artifacts", []))
    if failed:
        kinds = {item["kind"] for item in artifacts}
        missing = set(plan.capture_on_failure) - kinds
        if missing:
            problems.append(f"FAILURE_ARTIFACTS_MISSING:{','.join(sorted(missing))}")
    claimed_raw = execution.get("status")
    claimed: PlaywrightStatus
    if claimed_raw == "PASS":
        claimed = "PASS"
    elif claimed_raw == "FAIL":
        claimed = "FAIL"
    elif claimed_raw == "BLOCKED":
        claimed = "BLOCKED"
    else:
        problems.append("STATUS_INVALID")
        claimed = "BLOCKED"
    if claimed == "PASS" and (failed != 0 or executed == 0):
        problems.append("PASS_WITHOUT_CLEAN_EXECUTION")
    status: PlaywrightStatus
    if problems:
        status = "BLOCKED"
    elif claimed == "FAIL" or failed:
        status = "FAIL"
    else:
        status = claimed
    reason = "PLAYWRIGHT_EXECUTION_VERIFIED" if not problems else ";".join(sorted(problems))
    payload = {
        "status": status,
        "plan_sha256": plan.plan_sha256,
        "head_sha": plan.head_sha,
        "run_id": execution.get("run_id"),
        "job_id": execution.get("job_id"),
        "selected_tests": selected,
        "executed": executed,
        "passed": passed,
        "failed": failed,
        "artifacts": list(artifacts),
        "reason": reason,
    }
    return PlaywrightEvidence(
        status,
        plan.plan_sha256,
        plan.head_sha,
        execution.get("run_id") if type(execution.get("run_id")) is int else None,
        execution.get("job_id") if type(execution.get("job_id")) is int else None,
        tuple(selected),
        executed,
        passed,
        failed,
        artifacts,
        reason,
        sha256_json(payload),
    )


def playwright_quality_passes(evidence: PlaywrightEvidence) -> bool:
    return evidence.status in {"PASS", "NOT_APPLICABLE"}
