#!/usr/bin/env python3
"""Static review assertions only. NEVER invokes workflow or Anthropic API."""
from pathlib import Path
import re

text=(Path(__file__).resolve().parents[2]/".github/workflows/worker-pilot.yml").read_text(encoding="utf-8")
def required(pattern,reason):
    if re.search(pattern,text,re.M) is None:raise AssertionError(reason)
def forbidden(pattern,reason):
    if re.search(pattern,text,re.M) is not None:raise AssertionError(reason)

required(r"(?m)^on:\s*\n  workflow_dispatch:\s*$","manual-only trigger missing")
for name in ("push","pull_request","pull_request_target","schedule","repository_dispatch","workflow_call","workflow_run"):
    forbidden(r"^\s*"+name+r":", "automatic trigger forbidden:"+name)
required(r"^\s*permissions:\s*\n\s*contents: read\s*$","read-only permissions missing")
for name in ("contents","pull-requests","actions","checks","issues","packages"):
    forbidden(r"^\s*"+re.escape(name)+r":\s*write\s*$","write privilege forbidden:"+name)
required(r"^\s*timeout-minutes:\s*10\s*$","timeout must be 10")
required(r"^\s*group:\s*lf-worker-v08-pilot-single-running-job\s*$","singleton concurrency missing")
required(r"^\s*cancel-in-progress:\s*false\s*$","must never cancel in-flight paid run")
required(r"^\s*- anthropic\s*$","provider choice not pinned")
required(r"^\s*- claude-haiku-5-5\s*$","model choice not pinned")
required(r"^\s*- \"1\"\s*$","attempt choice not pinned")
required(r"^\s*ref: 298307e2f9cac72abfde2b181f3554b0e28bad24\s*$","original Worker not pinned")
required(r"^\s*ref: 5c981dfc77f8ffee1aa3cd66ab08a3b4d0051e2e\s*$","original cost adapter not pinned")
required(r"^\s*PILOT_HOLDOUT_JSON:.*secrets.PILOT_HOLDOUT_JSON","holdout secret not used")
required(r"^\s*ANTHROPIC_API_KEY:.*secrets.ANTHROPIC_API_KEY","API key secret not used")
required(r"979a661f32627a6d5fb8585ca413835bed0242369887970798184b3a8d3ab821","holdout hash not pinned")
required(r"--max-output-tokens", "token cap must be asserted by runner command generator") if "--max-output-tokens" in text else required(r"8000 output tokens","8k output token bound not documented")
required(r"^      - name: Mandatory real-usage cost gate", "cost gate step missing")
required(r"^      - name: Upload patch only after PASS and cost", "PASS-only patch upload missing")
for bad in ("echo \"$ANTHROPIC_API_KEY\"","echo \"$PILOT_HOLDOUT_JSON\"","set -x","secrets.GITHUB_TOKEN","gh pr create"):
    if bad in text:raise AssertionError("unsafe workflow expression:"+bad)
print("PASS WORKFLOW_STATIC_MANUAL_ONLY_NO_KEY_NO_MODEL")
