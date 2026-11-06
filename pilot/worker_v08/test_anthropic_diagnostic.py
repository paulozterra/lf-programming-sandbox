#!/usr/bin/env python3
"""Offline checks for diagnostic disclosure and exact vendored request shape."""
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from receipt_diagnostics import safe_reason
from anthropic_diagnostic import one_call, public_error, safe_field
from programming_agent_runner.anthropic_messages import ANTHROPIC_VERSION, PATCH_TOOL_NAME

class FakeHTTPFailure:
    def __init__(self, code, body):
        self.code = code
        self._body = io.BytesIO(body)
    def read(self, n=-1):
        return self._body.read(n)

class DiagnosticTests(unittest.TestCase):
    def test_worker_original_error_http_code_is_visible(self):
        self.assertEqual(safe_reason("Anthropic HTTP error 400", "MODEL_ERROR"),
                         "MODEL_ERROR: HTTP 400")
        self.assertEqual(safe_reason("Anthropic HTTP error 404", "MODEL_ERROR"),
                         "MODEL_ERROR: HTTP 404")
        self.assertEqual(safe_reason("Model returned opaque output", "MODEL_ERROR"),
                         "MODEL_ERROR (detalle privado redactado)")

    def test_error_only_allowed_fields_truncated_and_scanned(self):
        data=json.dumps({"type":"error","error":{"type":"invalid_request_error",
                         "message":"x"*550,"private":"DO_NOT_LEAK"},
                         "content":"MODEL_OUTPUT_DO_NOT_LEAK"}).encode()
        value=public_error(400,data)
        self.assertEqual(value["http_status"],400)
        self.assertEqual(value["error"]["type"],"invalid_request_error")
        self.assertEqual(len(value["error"]["message"]),500)
        self.assertNotIn("private",str(value))
        self.assertNotIn("content",str(value))
        self.assertEqual(safe_field("sk-proj-"+"A"*30),"[REDACTED_PROBABLE_SECRET]")

    def test_actual_worker_serializer_for_two_models_no_reply_export(self):
        seen=[]
        def opener(request,timeout):
            payload=json.loads(request.data)
            seen.append((payload,dict(request.header_items())))
            if payload["model"]=="claude-haiku-5-5":
                raise urllib.error.HTTPError(request.full_url,400,"invalid",{},
                      io.BytesIO(json.dumps({"error":{"type":"invalid_request_error",
                            "message":"forced tool choice rejected"},
                            "content":"MODEL_OUTPUT_DO_NOT_LEAK"}).encode()))
            class Success:
                status=200
                def __enter__(self): return self
                def __exit__(self,*args): return False
                def read(self,*args): raise AssertionError("response body must not be read")
            return Success()
        haiku=one_call("claude-haiku-5-5","test-key",opener=opener)
        sonnet=one_call("claude-sonnet-5-5","test-key",opener=opener)
        self.assertEqual((haiku["http_status"],sonnet["http_status"]),(400,200))
        self.assertEqual(haiku["error"]["message"],"forced tool choice rejected")
        self.assertNotIn("MODEL_OUTPUT_DO_NOT_LEAK",str(haiku)+str(sonnet))
        for payload, headers in seen:
            self.assertEqual(payload["max_tokens"],50)
            self.assertEqual(payload["tool_choice"],
                {"type":"tool","name":PATCH_TOOL_NAME,"disable_parallel_tool_use":True})
            self.assertEqual(len(payload["tools"]),1)
            self.assertEqual(payload["tools"][0]["name"],PATCH_TOOL_NAME)
            self.assertEqual(headers["Anthropic-version"],ANTHROPIC_VERSION)
            self.assertNotIn("thinking",payload)

if __name__=="__main__":
    unittest.main(verbosity=2)
