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
need(r"^    timeout-minutes: 10$","JOB_TIMEOUT_INVALID")
need(r"^  group: lf-worker-v08-pilot-single-running-job$","CONCURRENCY_INVALID")
need(r"^  cancel-in-progress: false$","IN_FLIGHT_CANCELLATION_FORBIDDEN")
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
need(r"979a661f32627a6d5fb8585ca413835bed0242369887970798184b3a8d3ab821","HOLDOUT_PIN_MISSING")
need(r"^          ANTHROPIC_API_KEY: .*secrets.ANTHROPIC_API_KEY","ANTHROPIC_KEY_NOT_SECRET")
need(r"^      - name: Conservative pre-model budget gate","PREMODEL_BUDGET_GATE_MISSING")
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
print("PASS WORKFLOW_MANUAL_VENDOR_EXACT_BASE64_SHA_ACTIONS_VERIFIED_WORKER_MODEL_BUDGET")
