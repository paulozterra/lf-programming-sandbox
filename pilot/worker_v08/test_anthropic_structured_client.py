#!/usr/bin/env python3
"""Fake transport tests for the separate Sonnet structured ModelClient; no paid calls."""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "vendor/programming-agent/src"))
from programming_agent_runner.anthropic_messages import AnthropicMessagesClient, ANTHROPIC_VERSION
from programming_agent_runner.worker_patch import PROPOSAL_JSON_SCHEMA
from programming_agent_runner.model_client import ModelError, ModelRefusal
from programming_agent_runner.worker import WORKER_SYSTEM_INSTRUCTION
from anthropic_structured_client import AnthropicStructuredClient

PROPOSAL={"schema_version": 1, "summary": "test", "patch": "diff --git a/x b/x\n", "changed_paths": ["x"]}
def fake_response(text=None, *, stop="end_turn", blocks=None, usage=None):
    return json.dumps({
        "id": "msg_test", "type": "message", "role": "assistant",
        "model": "claude-sonnet-5-5", "stop_reason": stop,
        "content": blocks if blocks is not None else [{"type":"text","text":json.dumps(PROPOSAL) if text is None else text}],
        "usage": {"input_tokens": 13, "output_tokens": 9} if usage is None else usage,
    }).encode()

class StructuredClientTests(unittest.TestCase):
    def client(self, response, captured=None):
        def transport(body,key,timeout):
            if captured is not None:
                captured.append(json.loads(body))
            return response
        return AnthropicStructuredClient(api_key="fake",model="claude-sonnet-5-5",
                                         max_output_tokens=50,transport=transport)

    def test_valid_json_returns_model_response_and_real_usage(self):
        captured=[]
        model=self.client(fake_response(),captured).generate(WORKER_SYSTEM_INSTRUCTION,{"ok":True})
        self.assertEqual(model.usage,{"input_tokens":13,"output_tokens":9,"total_tokens":22})
        self.assertEqual(json.loads(model.output_text),PROPOSAL)
        payload=captured[0]
        self.assertNotIn("tools",payload)
        self.assertNotIn("tool_choice",payload)
        self.assertEqual(payload["output_config"]["format"],
                         {"type":"json_schema","schema":PROPOSAL_JSON_SCHEMA})
        self.assertEqual(payload["system"],WORKER_SYSTEM_INSTRUCTION)
        self.assertEqual(payload["model"],"claude-sonnet-5-5")
        self.assertEqual(payload["max_tokens"],50)
        self.assertEqual(json.loads(payload["messages"][0]["content"]),{"ok":True})
        original=AnthropicMessagesClient(api_key="fake",model="claude-sonnet-5-5",
                                        max_output_tokens=50)
        reference=json.loads(original._request(WORKER_SYSTEM_INSTRUCTION,{"ok":True}))
        self.assertEqual({k:v for k,v in payload.items() if k!="output_config"},
                         {k:v for k,v in reference.items() if k not in ("tools","tool_choice")})

    def test_extra_text_is_model_error(self):
        with self.assertRaises(ModelError):
            self.client(fake_response(text=json.dumps(PROPOSAL)+" extra")).generate("s",{})

    def test_invalid_json_is_model_error(self):
        with self.assertRaises(ModelError):
            self.client(fake_response(text='{"summary":')).generate("s",{})

    def test_schema_violation_is_model_error(self):
        with self.assertRaises(ModelError):
            self.client(fake_response(text=json.dumps({**PROPOSAL,"unexpected":True}))).generate("s",{})

    def test_refusal_is_model_refusal(self):
        with self.assertRaises(ModelRefusal):
            self.client(fake_response(stop="refusal")).generate("s",{})

    def test_refusal_block_is_model_refusal(self):
        with self.assertRaises(ModelRefusal):
            self.client(fake_response(blocks=[{"type":"refusal","refusal":"no"}])).generate("s",{})

    def test_missing_usage_is_model_error(self):
        with self.assertRaises(ModelError):
            self.client(fake_response(usage={})).generate("s",{})

    def test_multiple_content_blocks_are_model_error(self):
        with self.assertRaises(ModelError):
            self.client(fake_response(blocks=[{"type":"text","text":json.dumps(PROPOSAL)},
                                              {"type":"text","text":"more"}])).generate("s",{})

    def test_non_end_turn_is_model_error(self):
        with self.assertRaises(ModelError):
            self.client(fake_response(stop="max_tokens")).generate("s",{})

    def test_diagnostic_records_only_schema_boolean(self):
        from anthropic_diagnostic import structured_sonnet_call
        result=structured_sonnet_call("fake",transport=lambda body,key,timeout:fake_response())
        self.assertEqual(result["http_status"],200)
        self.assertTrue(result["SCHEMA_VALID"])
        self.assertNotIn("patch",str(result))
        result=structured_sonnet_call("fake",transport=lambda body,key,timeout:fake_response(usage={}))
        self.assertEqual(result["http_status"],200)
        self.assertFalse(result["SCHEMA_VALID"])

if __name__=="__main__":
    unittest.main(verbosity=2)
