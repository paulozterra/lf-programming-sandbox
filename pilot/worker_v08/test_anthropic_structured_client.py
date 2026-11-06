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

    def test_thinking_then_text_valid_and_bills_full_usage(self):
        blocks=[{"type":"thinking","thinking":"PRIVATE_THOUGHT_NEVER_EXPORTED",
                 "signature":"PRIVATE_SIGNATURE_NEVER_EXPORTED"},
                {"type":"text","text":json.dumps(PROPOSAL)}]
        response=self.client(fake_response(blocks=blocks,usage={
            "input_tokens":11,"output_tokens":1234})).generate("s",{})
        self.assertEqual(json.loads(response.output_text),PROPOSAL)
        self.assertEqual(response.usage["output_tokens"],1234)
        self.assertEqual(response.usage["total_tokens"],1245)
        self.assertNotIn("PRIVATE_THOUGHT",response.output_text)
        self.assertNotIn("PRIVATE_SIGNATURE",response.output_text)

    def test_redacted_thinking_then_text_valid(self):
        blocks=[{"type":"redacted_thinking","data":"PRIVATE_REDACTED_PAYLOAD"},
                {"type":"text","text":json.dumps(PROPOSAL)}]
        response=self.client(fake_response(blocks=blocks)).generate("s",{})
        self.assertEqual(json.loads(response.output_text),PROPOSAL)
        self.assertNotIn("PRIVATE_REDACTED_PAYLOAD",response.output_text)

    def test_multiple_thinking_prefixes_then_text_valid(self):
        blocks=[{"type":"thinking","thinking":"secret 1","signature":"signature 1"},
                {"type":"redacted_thinking","data":"secret 2"},
                {"type":"text","text":json.dumps(PROPOSAL)}]
        self.assertEqual(json.loads(self.client(fake_response(blocks=blocks)).generate("s",{}).output_text),PROPOSAL)

    def test_text_then_thinking_is_model_error(self):
        blocks=[{"type":"text","text":json.dumps(PROPOSAL)},
                {"type":"thinking","thinking":"secret","signature":"signature"}]
        with self.assertRaises(ModelError):
            self.client(fake_response(blocks=blocks)).generate("s",{})

    def test_two_text_blocks_is_model_error(self):
        blocks=[{"type":"text","text":json.dumps(PROPOSAL)},
                {"type":"text","text":json.dumps(PROPOSAL)}]
        with self.assertRaises(ModelError):
            self.client(fake_response(blocks=blocks)).generate("s",{})

    def test_unknown_block_type_is_model_error(self):
        blocks=[{"type":"server_tool_use","name":"unsafe"},
                {"type":"text","text":json.dumps(PROPOSAL)}]
        with self.assertRaises(ModelError):
            self.client(fake_response(blocks=blocks)).generate("s",{})

    def test_thinking_without_text_is_model_error(self):
        blocks=[{"type":"thinking","thinking":"private","signature":"private"}]
        with self.assertRaises(ModelError):
            self.client(fake_response(blocks=blocks)).generate("s",{})

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

    def test_diagnostic_max_1500_and_stop_reason_not_hidden(self):
        from anthropic_diagnostic import structured_sonnet_call
        captured=[]
        def transport(body, key, timeout):
            captured.append(json.loads(body))
            return fake_response(stop="max_tokens", blocks=[
                {"type": "text", "text": "{", "citations": None}])
        result=structured_sonnet_call("fake",transport=transport)
        self.assertEqual(captured[0]["max_tokens"],1500)
        self.assertEqual(result["http_status"],200)
        self.assertFalse(result["SCHEMA_VALID"])
        self.assertEqual(result["stop_reason"],"max_tokens")
        self.assertEqual(result["content_block_keys"],[["citations","text","type"]])
        self.assertEqual(result["model_error_message"],
                         "Anthropic structured response shape or stop_reason invalid")
        self.assertNotIn("demo.txt",str(result))
        self.assertNotIn("text",json.dumps(result.get("error",{})))

    def test_diagnostic_reports_extra_content_key_without_relaxing_client(self):
        from anthropic_diagnostic import structured_sonnet_call
        def transport(body,key,timeout):
            return fake_response(blocks=[
                {"type":"text", "text":json.dumps(PROPOSAL), "citations":None}])
        result=structured_sonnet_call("fake",transport=transport)
        self.assertFalse(result["SCHEMA_VALID"])
        self.assertEqual(result["stop_reason"],"end_turn")
        self.assertEqual(result["content_block_keys"],[["citations","text","type"]])
        self.assertEqual(result["model_error_message"],
                         "Anthropic structured response must contain exactly one text block")

    def test_diagnostic_valid_schema_true_and_no_content(self):
        from anthropic_diagnostic import structured_sonnet_call
        result=structured_sonnet_call("fake",transport=lambda body,key,timeout:fake_response())
        self.assertTrue(result["SCHEMA_VALID"])
        self.assertEqual(result["stop_reason"],"end_turn")
        self.assertEqual(result["content_block_keys"],[["text","type"]])
        self.assertIsNone(result["model_error_message"])
        self.assertNotIn("summary",str(result))

    def test_diagnostic_errors_never_echo_untrusted_exception_text(self):
        from anthropic_diagnostic import structured_sonnet_call
        from programming_agent_runner.model_client import ModelError
        def transport(body,key,timeout):
            raise ModelError("SECRET_MODEL_OUTPUT_OR_KEY")
        result=structured_sonnet_call("fake",transport=transport)
        self.assertEqual(result["model_error_message"],"MODEL_ERROR_REDACTED")
        self.assertNotIn("SECRET_MODEL_OUTPUT_OR_KEY",str(result))

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
