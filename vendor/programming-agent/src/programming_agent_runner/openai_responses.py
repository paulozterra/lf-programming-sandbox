from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from .hashutil import canonical_json_bytes, strict_json_loads
from .model_client import ModelError, ModelRefusal, ModelResponse
from .worker_patch import PROPOSAL_JSON_SCHEMA

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
MAX_API_RESPONSE_BYTES = 4_000_000

Transport = Callable[[bytes, str, float], bytes]


def _bounded_http_body(response: Any) -> bytes:
    data = response.read(MAX_API_RESPONSE_BYTES + 1)
    if len(data) > MAX_API_RESPONSE_BYTES:
        raise ModelError("OpenAI response exceeds the local response-size limit")
    return data


def _default_transport(body: bytes, api_key: str, timeout: float) -> bytes:
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "programming-agent-worker/0.7.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _bounded_http_body(response)
    except urllib.error.HTTPError as exc:
        _bounded_http_body(exc)
        raise ModelError(f"OpenAI HTTP error {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ModelError(f"OpenAI transport failure: {type(exc).__name__}") from exc


def _usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        item = value.get(field)
        if type(item) is int and item >= 0:
            result[field] = item
    return result


def parse_responses_api_result(data: bytes, requested_model: str) -> ModelResponse:
    try:
        value = strict_json_loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ModelError(f"OpenAI response is not strict JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ModelError("OpenAI response root is not an object")
    if value.get("error") is not None:
        raise ModelError("OpenAI response contains a top-level error")
    status = value.get("status")
    if status != "completed":
        reason = value.get("incomplete_details")
        raise ModelError(f"OpenAI response is not completed: status={status!r}, details={reason!r}")
    response_id = value.get("id")
    resolved_model = value.get("model")
    output = value.get("output")
    if not isinstance(response_id, str) or not response_id:
        raise ModelError("OpenAI response id is missing")
    if not isinstance(resolved_model, str) or not resolved_model:
        raise ModelError("OpenAI resolved model is missing")
    if not isinstance(output, list):
        raise ModelError("OpenAI response output is missing")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            raise ModelError("OpenAI response output item is malformed")
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            raise ModelError("OpenAI message content is malformed")
        for part in content:
            if not isinstance(part, dict):
                raise ModelError("OpenAI message content part is malformed")
            part_type = part.get("type")
            if part_type == "refusal":
                raise ModelRefusal("OpenAI model refused the worker proposal")
            if part_type != "output_text":
                raise ModelError(f"unexpected OpenAI message content type: {part_type!r}")
            text = part.get("text")
            if not isinstance(text, str):
                raise ModelError("OpenAI output_text has no text")
            texts.append(text)
    if len(texts) != 1:
        raise ModelError(f"expected exactly one OpenAI output_text, observed {len(texts)}")
    return ModelResponse(response_id, requested_model, resolved_model, texts[0], _usage(value.get("usage")))


class OpenAIResponsesClient:
    provider = "openai"

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
            "store": False,
            "max_output_tokens": self.max_output_tokens,
            "input": [
                {"role": "system", "content": system_instruction},
                {
                    "role": "user",
                    "content": json.dumps(
                        user_payload,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        allow_nan=False,
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "programming_agent_patch",
                    "strict": True,
                    "schema": PROPOSAL_JSON_SCHEMA,
                }
            },
        }
        return canonical_json_bytes(request)

    def generate(self, system_instruction: str, user_payload: dict[str, Any]) -> ModelResponse:
        body = self._request(system_instruction, user_payload)
        data = self._transport(body, self.api_key, self.timeout_seconds)
        if not isinstance(data, bytes):
            raise ModelError("model transport did not return bytes")
        return parse_responses_api_result(data, self.model)
