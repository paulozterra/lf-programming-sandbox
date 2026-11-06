#!/usr/bin/env python3
"""Static offline guard for manual-only, vendored exact Worker pilot.

No requests to GitHub, no model invocations, no CI execution.
"""
from __future__ import annotations
import re
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
WORKFLOW=REPO/".github/workflows/worker-pilot.yml"
RUNNER=REPO/"pilot/worker_v08/run_live_pilot.py"
CONFIG=REPO/"pilot/worker_v08/manifest.json"
yaml=WORKFLOW.read_text(encoding="utf-8")
runner=RUNNER.read_text(encoding="utf-8")

def need(pattern,reason):
    if re.search(pattern,yaml,re.M) is None:
        raise AssertionError(reason)

def deny(pattern,reason):
    if re.search(pattern,yaml,re.M) is not None:
        raise AssertionError(reason)

need(r"^on:\s*\n  workflow_dispatch:\s*$","WORKFLOW_MUST_BE_MANUAL_ONLY")
for event in ("push","pull_request","pull_request_target","schedule",
              "repository_dispatch","workflow_call","workflow_run"):
    deny(r"^\s*"+re.escape(event)+r":","AUTO_TRIGGER_FORBIDDEN:"+event)
need(r"^permissions:\s*\n  contents: read\s*$","GLOBAL_WRITE_PERMISSION_FORBIDDEN")
need(r"^    timeout-minutes: .*inputs.task == .*exercise-3.*30.*10","JOB_TIMEOUT_INVALID")
need(r"^  group: lf-worker-v08-pilot-single-running-job$","CONCURRENCY_INVALID")
need(r"^  cancel-in-progress: false$","IN_FLIGHT_CANCELLATION_FORBIDDEN")
for exercise in ("exercise-1","exercise-2","exercise-3","ex4a","ex4b"):
    need(r"^          - "+re.escape(exercise)+r"$","TASK_INPUT_MISSING:"+exercise)
need(r"^      PILOT_TASK: .*inputs.task","TASK_ENV_MISSING")
for required in ("anthropic","claude-haiku-5-5","claude-sonnet-5-5"):
    need(r"^          - "+re.escape(required)+r"$","PROVIDER_MODEL_NOT_PINNED")
for v in ("1", "2", "3"):
    pattern = r'^          - "' + re.escape(v) + '"' + chr(36)
    need(pattern, "MAX_ATTEMPTS_NOT_PINNED:" + v)
need(r"^      PYTHONDONTWRITEBYTECODE: \"1\"$","VENDOR_DIRTY_RISK")
need(r"^          python3 source/pilot/worker_v08/verify_vendor.py \\","VENDOR_INTEGRITY_GATE_MISSING")
need(r"^          python3 source/pilot/worker_v08/test_verify_vendor.py$","VENDOR_NEGATIVE_TEST_MISSING")
need(r"^          cp -a .*source/vendor/programming-agent","VENDOR_COPY_INSTALL_MISSING")
need(r"^            --no-cache-dir .*worker-install-src","VENDOR_INSTALL_PATH_INVALID")
need(r"^          PILOT_HOLDOUT_B64: .*secrets.PILOT_HOLDOUT_B64","HOLDOUT_MUST_BE_B64_SECRET")
need(r"base64.b64decode\(encoded,validate=True\)","HOLDOUT_BASE64_MUST_BE_STRICT")
need(r"^      - name: Block missing task-specific holdout SHA before model or secrets$","TASK_SHA_GATE_MISSING")
need(r"--github-output \"\$GITHUB_OUTPUT\"","TASK_SHA_NOT_EXPORTED")
need(r"PILOT_HOLDOUT_EXPECTED_SHA: .*steps.task_sha.outputs.sha256","TASK_SHA_NOT_BOUND_TO_HOLDOUT")
need(r"^      - name: Decode exercise-1 holdout from its OWN base64 secret", "EXERCISE1_STEP_MISSING")
need(r"^      - name: Decode exercise-2 holdout from its OWN base64 secret", "EXERCISE2_STEP_MISSING")
need(r"if: .*inputs.task == 'exercise-1'", "EXERCISE1_CONDITION_MISSING")
need(r"if: .*inputs.task == 'exercise-2'", "EXERCISE2_CONDITION_MISSING")
need(r"^          PILOT_HOLDOUT_B64: .*secrets.PILOT_HOLDOUT_EX2_B64", "EXERCISE2_SECRET_MISSING")
if "&& secrets." in yaml or "|| secrets." in yaml:
    raise AssertionError("HOLDOUT_SECRET_FALLBACK_FORBIDDEN")

need(r"^          ANTHROPIC_API_KEY: .*secrets.ANTHROPIC_API_KEY","ANTHROPIC_KEY_NOT_SECRET")
need(r"^      - name: Conservative pre-model budget gate","PREMODEL_BUDGET_GATE_MISSING")
if yaml.index("Block missing task-specific holdout SHA") > yaml.index("ANTHROPIC_API_KEY:"):
    raise AssertionError("TASK_SHA_GATE_TOO_LATE")
need(r"^      - name: Mandatory actual-usage model-specific USD cost gate","COST_GATE_MISSING")
need(r"steps.worker.outcome == 'success' && steps.cost.outcome == 'success'","PATCH_PASS_GATE_MISSING")
need(r"^            .*public/cost.json$","COST_ARTIFACT_MISSING")
need(r"^            .*public/visible-worker-receipt.json$","VISIBLE_RECEIPT_ARTIFACT_MISSING")
need(r"^            .*public/verified-worker-receipt.json$","VERIFIED_RECEIPT_ARTIFACT_MISSING")
for name,sha in (("actions/checkout","11d5960a326750d5838078e36cf38b85af677262"),
                 ("actions/setup-python","a26af69be951a213d495a4c3e4e4022e16d87065"),
                 ("actions/upload-artifact","ea165f8d65b6e75b540449e92b4886f43607fa02")):
    if not re.search(r"uses: "+re.escape(name)+r"@"+sha+r"\b",yaml):
        raise AssertionError("ACTION_NOT_PINNED:"+name)
for bad in ("actions/checkout@v4","actions/setup-python@v5","actions/upload-artifact@v4",
            "repository: cristhianlujan/programming-agent",
            "repository: cristhianlujan/claude-persona-lf-patch",
            "PILOT_HOLDOUT_JSON", "set -x","gh pr create","secrets.GITHUB_TOKEN",
            "quality/programming_quality/baseline_v1.json"):
    if bad in yaml:
        raise AssertionError("FORBIDDEN_WORKFLOW_CONTENT:"+bad)
if ("run_verified_worker" not in runner or
    'QUALITY_CLI_NOT_USED = True' not in runner or
    "programming_quality_worker_hardened" in runner or
    "worker_cli.main" in runner or
    'PILOT_COST_OVER_USD_0_10' not in runner or
    'selected_policy()' not in runner or
    'budget_gate import require' not in runner or
    'MAX_COST_BY_MODEL' not in runner or
    '"max_output_tokens": 8000' not in runner):
    raise AssertionError("VERIFIED_WORKER_OR_LIMIT_INVARIANT_MISSING")
need(r"^      - name: Set up Java 21 ONLY for exercise-3", "EX3_JAVA_STEP_MISSING")
need(r"uses: actions/setup-java@dded0888837ed1f317902acf8a20df0ad188d165", "EX3_JAVA_NOT_PINNED")
need(r"^      - name: Decode exercise-3 holdout from its OWN base64 secret", "EX3_HOLDOUT_STEP_MISSING")
need(r"^          PILOT_HOLDOUT_B64: .*secrets.PILOT_HOLDOUT_EX3_B64", "EX3_HOLDOUT_SECRET_MISSING")
need(r"^      - name: Link JDK 21 and Maven into the vendored Worker's fixed PATH", "EX3_JDK_MAVEN_LINK_STEP_MISSING")
need(r"^      - name: Verify isolated Worker command environment uses Java 21 and Maven", "EX3_ISOLATED_JAVA_VERIFY_STEP_MISSING")
need(r"for tool in java javac jar; do", "EX3_JDK_TOOLS_INCOMPLETE")
if 'ln -sfn "$JAVA_HOME/bin/$tool" "/usr/local/bin/$tool"' not in yaml:
    raise AssertionError("EX3_JDK_BINARY_NOT_LINKED")
need(r"ln -sfn .* /usr/local/bin/mvn", "EX3_MAVEN_NOT_LINKED")
need(r"maven_source=.*readlink -f", "EX3_MAVEN_LINK_MUST_RESOLVE")
need(r'isolated_path="/usr/local/bin:/usr/bin:/bin"', "EX3_WORKER_PATH_NOT_EXACT")
for command in ('java -version', 'mvn -v'):
    if ('env -i PATH="$isolated_path" HOME="$isolated_home" '+command) not in yaml:
        raise AssertionError("EX3_ISOLATED_COMMAND_NOT_TESTED:"+command)
need(r"grep -Eq 'version .*21", "EX3_JAVA21_NOT_ENFORCED")
need(r"grep -Eq 'Java version: 21", "EX3_MAVEN_JAVA21_NOT_ENFORCED")
need(r'test -z ".*JAVA_HOME', "EX3_JAVA_HOME_MUST_BE_UNSET")
if yaml.count("if: ${{ inputs.task == 'exercise-3' }}") < 4:
    raise AssertionError("EX3_STEPS_MUST_BE_ISOLATED")
if not (yaml.index("Set up Java 21 ONLY") <
        yaml.index("Link JDK 21 and Maven") <
        yaml.index("Verify isolated Worker command environment") <
        yaml.index("Execute REAL vendored run_verified_worker")):
    raise AssertionError("EX3_JDK_VERIFICATION_TOO_LATE")
need(r"^      - name: Build isolated executable time-service JAR only on verified PASS", "EX3_JAR_GATE_MISSING")
need(r"^      - name: Upload exercise-3 executable JAR ONLY on verified PASS", "EX3_JAR_UPLOAD_MISSING")
need(r"name: time-service.jar", "EX3_JAR_ARTIFACT_MISSING")
need(r'--task "[^"]*PILOT_TASK"', "EX3_BUDGET_TASK_NOT_PASSED")
if yaml.index("Block missing task-specific holdout SHA") > yaml.index("Set up Java 21 ONLY"):
    raise AssertionError("EX3_HOLDOUT_SHA_GATE_TOO_LATE")

for task in ("ex4a","ex4b"):
    need(r"^          - "+task+r"$", "EX4_TASK_NOT_SELECTABLE:"+task)
    need(r"^      - name: Decode "+task+r" holdout from its OWN base64 secret", "EX4_PRIVATE_HOLDOUT_MISSING:"+task)
    need(r"^          PILOT_HOLDOUT_B64: .*secrets.PILOT_HOLDOUT_"+task.upper()+r"_B64", "EX4_SECRET_MISSING:"+task)
    need(r"if: .*inputs.task == '"+task+r"'", "EX4_SECRET_SCOPE_MISSING:"+task)
need(r"^      - name: Lot A/B SHA, context-size and first-parent handoff gate BEFORE secrets/model",
     "EX4_PREMODEL_LOT_GATE_MISSING")
need(r"lot_preflight.py --task", "EX4_PREMODEL_LOT_GATE_NOT_INVOKED")
need(r"EX4_ISOLATED_JAVA21_AND_MAVEN_PASS", "EX4_ISOLATED_JAVA_TEST_MISSING")
need(r"^      - name: Set up Java 21 ONLY for ex4a/ex4b", "EX4_SETUP_JAVA_MISSING")
need(r"^      - name: Link JDK 21 and Maven into the vendored Worker's fixed PATH \(ex4a/ex4b only\)",
     "EX4_FIXED_PATH_MISSING")
if not (yaml.index("Lot A/B SHA, context-size") < yaml.index("Decode ex4a holdout") and
        yaml.index("Lot A/B SHA, context-size") < yaml.index("Decode ex4b holdout") and
        yaml.index("Lot A/B SHA, context-size") < yaml.index("ANTHROPIC_API_KEY:")):
    raise AssertionError("EX4_LOT_PREFLIGHT_MUST_PRECEDE_SECRETS")
if "|| secrets." in yaml or "&& secrets." in yaml:
    raise AssertionError("EX4_HOLDOUT_FALLBACK_FORBIDDEN")

# PR #34 lineage needs full first-parent history, not checkout default depth=1.
if "fetch-depth: " + "$" + "{{ inputs.task == 'ex4b' && '0' || '1' }}" not in yaml:
    raise AssertionError("EX4B_COMPLETE_MERGE_HISTORY_NOT_FETCHED")
if yaml.index("fetch-depth:") > yaml.index("Lot A/B SHA, context-size"):
    raise AssertionError("EX4B_HISTORY_FETCH_TOO_LATE")

# Exercise 5: context is derived before any secret or model call; no oracle fallback.
need(r"^          - ex5c$", "EX5C_TASK_NOT_SELECTABLE")
need(r"^      - name: Derive ex5c context before secrets/model", "EX5_DERIVE_STEP_MISSING")
need(r"derive_context.py", "EX5_DERIVER_NOT_INVOKED")
need(r"--output .*derived-context.json", "EX5_DERIVE_REPORT_MISSING")
need(r"^      - name: Decode ex5c holdout from its OWN base64 secret", "EX5_PRIVATE_HOLDOUT_MISSING")
need(r"secrets.PILOT_HOLDOUT_EX5C_B64", "EX5_SECRET_NOT_ISOLATED")
need(r"^            .*public/derived-context.json", "EX5_REPORT_NOT_UPLOADED")
if not (yaml.index("Derive ex5c context") <
        yaml.index("Decode ex5c holdout") <
        yaml.index("Execute REAL vendored run_verified_worker")):
    raise AssertionError("EX5_DERIVE_NOT_PREMODEL")
if "|| secrets." in yaml or "&& secrets." in yaml:
    raise AssertionError("EX5_SECRET_FALLBACK_FORBIDDEN")

print("PASS WORKFLOW_MANUAL_VENDOR_EXACT_BASE64_SHA_ACTIONS_VERIFIED_WORKER_MODEL_BUDGET")
