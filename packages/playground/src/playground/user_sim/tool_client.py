"""LLM clients with tool-calling support for the user simulator."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Protocol, Sequence

from playground.chatbot_capabilities import ChatbotCapability
from playground.openai_client import openai_model_supports_custom_temperature
from playground.user_sim.tools import (
    ToolCall,
    anthropic_tool_definitions,
    normalize_sim_message,
    tool_definitions,
)
from matraix.persona_agent_context import CHATBOT_MAX_OUTPUT_TOKENS


class ToolStepClient(Protocol):
    def complete_with_tools(self, messages: List[Dict[str, Any]]) -> List[ToolCall]: ...


class FakeToolStepClient:
    """Test double returning a scripted sequence of tool calls."""

    def __init__(self, steps: List[List[ToolCall]]) -> None:
        self._steps = list(steps)
        self.calls: List[List[Dict[str, Any]]] = []

    def complete_with_tools(self, messages: List[Dict[str, Any]]) -> List[ToolCall]:
        self.calls.append(list(messages))
        if not self._steps:
            return [ToolCall("end_conversation", {"reason": "give_up"})]
        return self._steps.pop(0)


class OpenAIToolStepClient:
    def __init__(
        self,
        model: str,
        *,
        client: Optional[Any] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        capabilities: Sequence[ChatbotCapability] | None = None,
        provider: str = "openai",
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.provider = provider
        self.usage_parts: list = []
        self._tools = tool_definitions(capabilities)
        if client is None:
            from openai import OpenAI

            client_kwargs: Dict[str, Any] = {}
            if api_key is not None:
                client_kwargs["api_key"] = api_key
            if base_url is not None:
                client_kwargs["base_url"] = base_url
            client = OpenAI(**client_kwargs)
        self._client = client

    def complete_with_tools(self, messages: List[Dict[str, Any]]) -> List[ToolCall]:
        from playground.llm_usage import usage_from_openai_completion

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": self._tools,
            "tool_choice": "auto",
        }
        if openai_model_supports_custom_temperature(self.model):
            kwargs["temperature"] = self.temperature
        completion = self._client.chat.completions.create(**kwargs)
        self.usage_parts.append(
            usage_from_openai_completion(
                completion, model=self.model, provider=self.provider
            )
        )
        message = completion.choices[0].message
        calls: List[ToolCall] = []
        for tool_call in message.tool_calls or []:
            fn = tool_call.function
            calls.append(ToolCall(fn.name, _coerce_args(fn.arguments)))
        if not calls:
            text = normalize_sim_message(str(message.content or ""))
            if text:
                calls.append(ToolCall("send_message", {"message": text}))
        return calls

    def accumulated_usage(self):
        from playground.llm_usage import merge_usage

        return merge_usage(*self.usage_parts)


class AnthropicToolStepClient:
    def __init__(
        self,
        model: str,
        *,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        timeout_seconds: float = 180.0,
        capabilities: Sequence[ChatbotCapability] | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.usage_parts: list = []
        self._tools = anthropic_tool_definitions(capabilities)
        self.api_key = (
            api_key
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("CLAUDE_API_KEY")
            or ""
        ).strip()
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY or CLAUDE_API_KEY is required for persona model {}".format(
                    model
                )
            )

    def complete_with_tools(self, messages: List[Dict[str, Any]]) -> List[ToolCall]:
        from playground.llm_usage import usage_from_anthropic_payload

        system_parts: List[str] = []
        convo: List[Dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = str(message.get("content") or "")
            if role == "system":
                system_parts.append(content)
            elif role in {"user", "assistant"}:
                convo.append({"role": role, "content": content})
        body = {
            "model": self.model,
            "max_tokens": CHATBOT_MAX_OUTPUT_TOKENS,
            "system": "\n\n".join(system_parts),
            "messages": convo,
            "tools": self._tools,
        }
        if openai_model_supports_custom_temperature(self.model):
            body["temperature"] = self.temperature
        request = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                "Anthropic tool request failed: HTTP {} {}".format(exc.code, detail[:500])
            ) from exc
        except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError("Anthropic tool request failed: {}".format(exc)) from exc

        self.usage_parts.append(usage_from_anthropic_payload(payload, model=self.model))
        calls: List[ToolCall] = []
        text_parts: List[str] = []
        for block in payload.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                calls.append(
                    ToolCall(str(block.get("name") or ""), dict(block.get("input") or {}))
                )
            elif block.get("type") == "text":
                text_parts.append(str(block.get("text") or ""))
        if not calls and text_parts:
            text = normalize_sim_message("\n".join(text_parts))
            if text:
                calls.append(ToolCall("send_message", {"message": text}))
        return calls

    def accumulated_usage(self):
        from playground.llm_usage import merge_usage

        return merge_usage(*self.usage_parts)


def _coerce_args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def build_tool_step_client(
    model: str,
    *,
    temperature: float = 0.7,
    capabilities: Sequence[ChatbotCapability] | None = None,
) -> ToolStepClient:
    from playground.model_client import (
        dashscope_openai_client_kwargs,
        openrouter_openai_client_kwargs,
    )

    value = (model or "openai/gpt-4o-mini").strip()
    if value.startswith("anthropic/"):
        proxy_base = (
            os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE") or ""
        ).strip()
        if proxy_base:
            # Route Claude tool-calling through the proxy's OpenAI-compatible
            # endpoint so it shares the global rate limiter. LiteLLM translates
            # OpenAI tool schema <-> Anthropic tool_use.
            return OpenAIToolStepClient(
                value,
                temperature=temperature,
                capabilities=capabilities,
                provider="anthropic",
            )
        return AnthropicToolStepClient(
            value.split("/", 1)[1],
            temperature=temperature,
            capabilities=capabilities,
        )
    if value.startswith("dashscope/"):
        kwargs = dashscope_openai_client_kwargs(value)
        return OpenAIToolStepClient(
            kwargs["model"],
            api_key=kwargs["api_key"],
            base_url=kwargs["base_url"],
            temperature=temperature,
            capabilities=capabilities,
            provider="dashscope",
        )
    if value.startswith("openrouter/"):
        kwargs = openrouter_openai_client_kwargs(value)
        return OpenAIToolStepClient(
            kwargs["model"],
            api_key=kwargs["api_key"],
            base_url=kwargs["base_url"],
            temperature=temperature,
            capabilities=capabilities,
            provider="openrouter",
        )
    if value.startswith("openai/"):
        return OpenAIToolStepClient(
            value.split("/", 1)[1],
            temperature=temperature,
            capabilities=capabilities,
            provider="openai",
        )
    if value.startswith("gpt-"):
        return OpenAIToolStepClient(
            value,
            temperature=temperature,
            capabilities=capabilities,
            provider="openai",
        )
    return AnthropicToolStepClient(
        value, temperature=temperature, capabilities=capabilities
    )
