#!/usr/bin/env python3
"""Messages API structured-JSON ModelClient for Sonnet, without forced tool use.

Official API: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
Uses the vendored request serializer and schema, but NEVER edits vendor/.
"""
from __future__ import annotations

import json
from typing import Any

from programming_agent_runner.anthropic_messages import AnthropicMessagesClient
from programming_agent_runner.hashutil import canonical_json_bytes, strict_json_loads
from programming_agent_runner.model_client import ModelError, ModelRefusal, ModelResponse
from programming_agent_runner.worker_patch import PROPOSAL_JSON_SCHEMA


def _matches_schema(value: Any, schema: dict[str, Any]) -> bool:
    """Validate the imported schema's supported JSON Schema keywords offline.

    The Worker currently uses object/properties/required/additionalProperties,
    array/items, string, integer and enum. Reject unknown constraints, fail closed.
    """
    supported = {"type", "properties", "required", "additionalProperties", "items", "enum"}
    if not isinstance(schema, dict) or set(schema) - supported:
        return False
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return False
        props = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(props, dict) or not isinstance(required, list):
            return False
        if not all(isinstance(k, str) for k in required) or not set(required) <= set(value):
            return False
        if schema.get("additionalProperties") is False and set(value) - set(props):
            return False
        if any(k not in props or not _matches_schema(v, props[k]) for k, v in value.items()):
            return False
    elif kind == "array":
        if not isinstance(value, list) or not isinstance(schema.get("items"), dict):
            return False
        if not all(_matches_schema(v, schema["items"]) for v in value):
            return False
    elif kind == "integer":
        if type(value) is not int:
            return False
    elif kind == "string":
        if not isinstance(value, str):
            return False
    else:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    return True


def parse_structured_result(data: bytes, requested_model: str) -> ModelResponse:
    try:
        value = strict_json_loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ModelError("Anthropic structured response is not strict JSON") from exc
    if not isinstance(value, dict):
        raise ModelError("Anthropic structured response root invalid")
    if value.get("type") == "error" or "error" in value:
        raise ModelError("Anthropic structured response contains error")
    if value.get("stop_reason") == "refusal":
        raise ModelRefusal("Anthropic model refused structured proposal")
    blocks = value.get("content")
    if (value.get("type") != "message" or value.get("role") != "assistant"
        or value.get("stop_reason") != "end_turn"
        or not isinstance(blocks, list) or len(blocks) != 1):
        raise ModelError("Anthropic structured response shape or stop_reason invalid")
    block = blocks[0]
    if not isinstance(block, dict):
        raise ModelError("Anthropic structured response block invalid")
    if block.get("type") == "refusal":
        raise ModelRefusal("Anthropic structured content refused")
    if set(block) != {"type", "text"} or block["type"] != "text" or not isinstance(block["text"], str):
        raise ModelError("Anthropic structured response must contain exactly one text block")
    raw_text = block["text"]
    try:
        proposal = strict_json_loads(raw_text)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ModelError("Anthropic structured proposal is not strict JSON") from exc
    if not _matches_schema(proposal, PROPOSAL_JSON_SCHEMA):
        raise ModelError("Anthropic structured proposal violates imported Worker schema")
    response_id = value.get("id")
    resolved = value.get("model")
    if not isinstance(response_id, str) or not response_id or not isinstance(resolved, str) or not resolved:
        raise ModelError("Anthropic structured response identity missing")
    usage = value.get("usage")
    if (not isinstance(usage, dict)
        or any(type(usage.get(key)) is not int or usage[key] < 0
               for key in ("input_tokens", "output_tokens"))):
        raise ModelError("Anthropic structured response usage missing or invalid")
    actual_usage = {
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "total_tokens": usage["input_tokens"] + usage["output_tokens"],
    }
    # Return a canonical single JSON object understood by the ORIGINAL Worker.
    return ModelResponse(response_id, requested_model, resolved,
                         canonical_json_bytes(proposal).decode("utf-8"), actual_usage)


class AnthropicStructuredClient(AnthropicMessagesClient):
    """Drop-in ModelClient: identical system/user serialization, JSON output instead of tools."""

    def _request(self, system_instruction: str, user_payload: dict[str, Any]) -> bytes:
        request = strict_json_loads(super()._request(system_instruction, user_payload).decode("utf-8"))
        request.pop("tools")
        request.pop("tool_choice")
        request["output_config"] = {
            "format": {"type": "json_schema", "schema": PROPOSAL_JSON_SCHEMA}
        }
        return canonical_json_bytes(request)

    def generate(self, system_instruction: str, user_payload: dict[str, Any]) -> ModelResponse:
        data = self._transport(self._request(system_instruction, user_payload),
                               self.api_key, self.timeout_seconds)
        if not isinstance(data, bytes):
            raise ModelError("model transport did not return bytes")
        return parse_structured_result(data, self.model)
