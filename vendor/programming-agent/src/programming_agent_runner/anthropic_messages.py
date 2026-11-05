from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from .hashutil import canonical_json_bytes, strict_json_loads
from .model_client import ModelError, ModelRefusal, ModelResponse
from .worker_patch import PROPOSAL_JSON_SCHEMA

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
PATCH_TOOL_NAME = "programming_agent_patch"
MAX_API_RESPONSE_BYTES = 4_000_000

Transport = Callable[[bytes, str, float], bytes]


def _bounded_http_body(response: Any) -> bytes:
    data = response.read(MAX_API_RESPONSE_BYTES + 1)
    if len(data) > MAX_API_RESPONSE_BYTES:
        raise ModelError("Anthropic response exceeds the local response-size limit")
    return data


def _default_transport(body: bytes, api_key: str, timeout: float) -> bytes:
    request = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=body,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
            "user-agent": "programming-agent-worker/0.7.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _bounded_http_body(response)
    except urllib.error.HTTPError as exc:
        _bounded_http_body(exc)
        raise ModelError(f"Anthropic HTTP error {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ModelError(f"Anthropic transport failure: {type(exc).__name__}") from exc


def _usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for field in ("input_tokens", "output_tokens"):
        item = value.get(field)
        if type(item) is int and item >= 0:
            result[field] = item
    if "input_tokens" in result and "output_tokens" in result:
        result["total_tokens"] = result["input_tokens"] + result["output_tokens"]
    return result


def parse_messages_api_result(data: bytes, requested_model: str) -> ModelResponse:
    try:
        value = strict_json_loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ModelError(f"Anthropic response is not strict JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ModelError("Anthropic response root is not an object")
    if value.get("type") == "error" or value.get("error") is not None:
        raise ModelError("Anthropic response contains an error")
    response_id = value.get("id")
    resolved_model = value.get("model")
    if not isinstance(response_id, str) or not response_id:
        raise ModelError("Anthropic response id is missing")
    if not isinstance(resolved_model, str) or not resolved_model:
        raise ModelError("Anthropic resolved model is missing")
    if value.get("type") != "message" or value.get("role") != "assistant":
        raise ModelError("Anthropic response is not an assistant message")
    stop_reason = value.get("stop_reason")
    if stop_reason == "refusal":
        raise ModelRefusal("Anthropic model refused the worker proposal")
    if stop_reason != "tool_use":
        raise ModelError(f"Anthropic response did not complete with tool_use: stop_reason={stop_reason!r}")
    content = value.get("content")
    if not isinstance(content, list):
        raise ModelError("Anthropic response content is missing")
    tool_blocks: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            raise ModelError("Anthropic response content block is malformed")
        if block.get("type") != "tool_use":
            raise ModelError(f"unexpected Anthropic content type: {block.get('type')!r}")
        tool_blocks.append(block)
    if len(tool_blocks) != 1:
        raise ModelError(f"expected exactly one Anthropic tool_use, observed {len(tool_blocks)}")
    tool = tool_blocks[0]
    if tool.get("name") != PATCH_TOOL_NAME:
        raise ModelError("Anthropic response invoked the wrong tool")
    tool_id = tool.get("id")
    proposal = tool.get("input")
    if not isinstance(tool_id, str) or not tool_id:
        raise ModelError("Anthropic tool_use id is missing")
    if not isinstance(proposal, dict):
        raise ModelError("Anthropic tool_use input is not an object")
    output_text = canonical_json_bytes(proposal).decode("utf-8")
    return ModelResponse(response_id, requested_model, resolved_model, output_text, _usage(value.get("usage")))


class AnthropicMessagesClient:
    provider = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
        max_output_tokens: int = 20_000,
        transport: Transport | None = None,
    ) -> None:
        if not api_key or any(character in api_key for character in "\r\n"):
            raise ValueError("api_key is missing or invalid")
        if not model or len(model.encode("utf-8")) > 200 or any(ord(character) < 32 for character in model):
            raise ValueError("model identifier is missing or invalid")
        if not 1 <= max_output_tokens <= 100_000:
            raise ValueError("max_output_tokens is outside the local safety bound")
        if not 1 <= timeout_seconds <= 900:
            raise ValueError("timeout_seconds is outside the local safety bound")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self._transport = transport or _default_transport

    def _request(self, system_instruction: str, user_payload: dict[str, Any]) -> bytes:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "system": system_instruction,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        user_payload,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        allow_nan=False,
                    ),
                }
            ],
            "tools": [
                {
                    "name": PATCH_TOOL_NAME,
                    "description": (
                        "Return exactly one programming Worker patch proposal. The input must satisfy the supplied "
                        "schema; it is data only and is still validated by the local Worker before any patch is "
                        "applied."
                    ),
                    "input_schema": PROPOSAL_JSON_SCHEMA,
                }
            ],
            "tool_choice": {
                "type": "tool",
                "name": PATCH_TOOL_NAME,
                "disable_parallel_tool_use": True,
            },
        }
        return canonical_json_bytes(request)

    def generate(self, system_instruction: str, user_payload: dict[str, Any]) -> ModelResponse:
        body = self._request(system_instruction, user_payload)
        data = self._transport(body, self.api_key, self.timeout_seconds)
        if not isinstance(data, bytes):
            raise ModelError("model transport did not return bytes")
        return parse_messages_api_result(data, self.model)
