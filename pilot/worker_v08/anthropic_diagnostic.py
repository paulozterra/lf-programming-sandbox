#!/usr/bin/env python3
"""Manual Anthropic diagnostic: exact vendored Worker request shape, safe metadata only.

ONE call per model; never export API keys, response content, or holdout.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))
from programming_agent_runner.anthropic_messages import (
    AnthropicMessagesClient, ANTHROPIC_MESSAGES_URL, ANTHROPIC_VERSION,
)
from programming_agent_runner.worker_secrets import secret_text_reason

MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")
MAX_ERROR_BODY = 65536

def safe_field(value):
    if not isinstance(value, str):
        return None
    text = value[:500]
    # Fail closed: an unsafe field is replaced, never partly leaked.
    if secret_text_reason(text) or any(ord(c) < 32 and c not in "\t\n" for c in text):
        return "[REDACTED_PROBABLE_SECRET]"
    return text

def public_error(status, raw):
    result = {"http_status": status, "error": {"type": None, "message": None}}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        return result
    if isinstance(value, dict) and isinstance(value.get("error"), dict):
        err = value["error"]
        result["error"] = {"type": safe_field(err.get("type")),
                           "message": safe_field(err.get("message"))}
    return result

def one_call(model, api_key, opener=urllib.request.urlopen):
    # _request is the original, pinned, vendored Worker serializer:
    # same anthropic-version, tools schema and forced tool_choice.
    client = AnthropicMessagesClient(api_key=api_key, model=model,
                                    max_output_tokens=50, timeout_seconds=30)
    body = client._request("Return a minimal valid patch proposal.", {"diagnostic": "ping"})
    request = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL, data=body, method="POST",
        headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION,
                 "content-type": "application/json",
                 "user-agent": "programming-agent-worker/0.7.1"})
    try:
        with opener(request, timeout=30) as response:
            # NEVER read/export successful model output, even if tool use occurs.
            return {"model": model, "http_status": response.status,
                    "error": {"type": None, "message": None}}
    except urllib.error.HTTPError as exc:
        # Bound the provider error body; export only the allowlisted fields.
        value = public_error(exc.code, exc.read(MAX_ERROR_BODY + 1)[:MAX_ERROR_BODY])
        return {"model": model, **value}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"model": model, "http_status": None,
                "error": {"type": "TRANSPORT_ERROR", "message": None}}

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY_MISSING")
    dest = Path(os.environ["RUNNER_TEMP"]) / "anthropic-diagnostic"
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    results = [one_call(model, api_key) for model in MODELS]
    path = dest / "status.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump({"schema_version": "LF_ANTHROPIC_DIAGNOSTIC_V1",
                   "worker_request_structure": "VENDORED_EXACT_MAX_TOKENS_50",
                   "anthropic_version": ANTHROPIC_VERSION,
                   "results": results}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    path.chmod(0o600)
    for item in results:
        print(item["model"] + ": HTTP " + str(item["http_status"]) + 
              " type=" + str(item["error"]["type"]))
    if any(item["http_status"] != 200 for item in results):
        raise SystemExit("ANTHROPIC_DIAGNOSTIC_NON_200")

if __name__ == "__main__":
    main()
