from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Protocol

from playground.llm_usage import JsonCompletion, usage_from_openai_completion

_FENCE = re.compile(r"```(?:json)?\s*(?P<body>\{.*\})\s*```", re.DOTALL)
DEFAULT_REQUEST_TIMEOUT_SECONDS = 180.0


def coerce_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _FENCE.search(text)
    if match:
        return json.loads(match.group("body"))
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        return json.loads(text[start:end + 1])
    raise ValueError("could not parse JSON from model output: {!r}".format(text[:200]))


def openai_model_supports_custom_temperature(model: str) -> bool:
    """Whether Chat Completions / Messages accepts a non-default ``temperature``.

    GPT-5 family models currently only allow the API default (1); sending
    ``0.1`` / ``0.7`` returns HTTP 400. Claude Opus 4.7+ (and Bedrock Opus)
    similarly reject an explicit non-default temperature.
    """
    lowered = (model or "").strip().lower()
    bare = lowered.rsplit("/", 1)[-1] if "/" in lowered else lowered
    if bare.startswith("gpt-5"):
        return False
    opus = re.search(r"opus-4-(\d+)", lowered)
    if opus is not None and int(opus.group(1)) >= 7:
        return False
    if "bedrock" in lowered and "opus" in lowered:
        return False
    return True


class ChatClient(Protocol):
    def complete_json(self, system: str, user: str) -> Dict[str, Any]: ...


class OpenAIChatClient:
    """OpenAI v1 client (`from openai import OpenAI`) using JSON response mode."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        client: Optional[Any] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        provider: str = "openai",
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.provider = provider
        if client is None:
            from openai import OpenAI  # lazy: tests inject a fake

            client_kwargs: Dict[str, Any] = {}
            if api_key is not None:
                client_kwargs["api_key"] = api_key
            if base_url is not None:
                client_kwargs["base_url"] = base_url
            client = OpenAI(**client_kwargs)
        self._client = client

    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        return self.complete_json_with_usage(system, user).data

    def complete_json_with_usage(self, system: str, user: str) -> JsonCompletion:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "timeout": self.timeout_seconds,
        }
        if openai_model_supports_custom_temperature(self.model):
            kwargs["temperature"] = self.temperature
        completion = self._client.chat.completions.create(**kwargs)
        data = coerce_json(completion.choices[0].message.content)
        usage = usage_from_openai_completion(
            completion, model=self.model, provider=self.provider
        )
        return JsonCompletion(data=data, usage=usage)
