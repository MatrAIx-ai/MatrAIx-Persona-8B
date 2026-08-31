"""Studio run configuration and its mapping to ``INTERECAGENT_*`` env vars.

A Studio "config" is a small dict that controls how the in-process RecAI agent
is built and how it ranks/serves recommendations. :class:`ConfigManager` is the
single source of truth for:

* the **allowed** values for each config key (``options``),
* the **defaults**,
* **validation** of a candidate config,
* the translation of a config to the ``INTERECAGENT_*`` environment variables
  that :func:`recbot.interecagent_bridge.run_turn` reads, and
* whether a config change **invalidates the cached agent** (so the API can warn
  the user that the next turn will pay a cold start again).

The module imports only the stdlib so it is safe to import anywhere.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

PERSONA_MODEL_ENV = "MATRIX_PERSONA_MODEL"
HARBOR_PERSONA_MODEL_ENV = "MATRIX_HARBOR_PERSONA_MODEL"
PLAYGROUND_RUNTIME_ENV = "MATRIX_PLAYGROUND_RUNTIME"
EXECUTION_PLANE_ENV = "MATRIX_EXECUTION_PLANE"
REMOTE_RUNNER_API_URL_ENV = "REMOTE_RUNNER_API_URL"
DEFAULT_PERSONA_MODEL = "anthropic/claude-haiku-4-5"

# Persona-model IDs use LiteLLM provider prefixes (``anthropic/``, ``openai/``,
# ``gemini/``, ``xai/``, ``deepseek/``, ``zai/``, ``dashscope/``, ``openrouter/``,
# ``orcarouter/``).
# OpenAI-compatible providers use their own credentials and endpoints.
PERSONA_MODEL_KNOB_META: Dict[str, Dict[str, str]] = {
    "anthropic/claude-haiku-4-5": {
        "label": "Claude Haiku 4.5",
        "description": "Lower-cost persona simulation; the default.",
    },
    "anthropic/claude-sonnet-4-6": {
        "label": "Claude Sonnet 4.6",
        "description": "Stronger persona simulation at higher cost.",
    },
    "anthropic/claude-opus-4-8": {
        "label": "Claude Opus 4.8",
        "description": "Highest-capability Claude persona simulation; highest cost.",
    },
    "openai/gpt-4o-mini": {
        "label": "GPT-4o mini",
        "description": "OpenAI persona simulation with lower cost.",
    },
    "openai/gpt-4o": {
        "label": "GPT-4o",
        "description": "OpenAI persona simulation with stronger reasoning.",
    },
    "openai/gpt-5.4": {
        "label": "GPT-5.4",
        "description": "OpenAI computer-use CUA (macOS/Linux desktop via Responses API).",
    },
    "openai/gpt-5.5": {
        "label": "GPT-5.5",
        "description": "OpenAI computer-use CUA (default OpenAI desktop CUA model).",
    },
    "gemini/gemini-2.5-flash": {
        "label": "Gemini 2.5 Flash",
        "description": "Google persona simulation with lower cost.",
    },
    "gemini/gemini-2.5-pro": {
        "label": "Gemini 2.5 Pro",
        "description": "Google persona simulation with stronger reasoning.",
    },
    "gemini/gemini-2.5-computer-use-preview-10-2025": {
        "label": "Gemini 2.5 Computer Use",
        "description": "Google computer-use CUA (macOS/Linux desktop).",
    },
    "xai/grok-4.5": {
        "label": "Grok 4.5",
        "description": "xAI flagship persona simulation.",
    },
    "xai/grok-3-mini": {
        "label": "Grok 3 Mini",
        "description": "xAI lower-cost persona simulation.",
    },
    "deepseek/deepseek-v4-pro": {
        "label": "DeepSeek V4 Pro",
        "description": "DeepSeek official API flagship.",
    },
    "deepseek/deepseek-chat": {
        "label": "DeepSeek Chat",
        "description": "DeepSeek official API chat alias.",
    },
    "zai/glm-5": {
        "label": "GLM 5",
        "description": "Z.ai official GLM flagship.",
    },
    "zai/glm-4.7": {
        "label": "GLM 4.7",
        "description": "Z.ai official GLM 4.7.",
    },
    "dashscope/qwen3.6-plus-2026-04-02": {
        "label": "Qwen 3.6 Plus · Apr 2026",
        "description": "Pinned DashScope release — use for reproducible runs.",
    },
    "dashscope/qwen3.6-plus": {
        "label": "Qwen 3.6 Plus · latest",
        "description": "Rolling alias — tracks DashScope updates.",
    },
    "dashscope/qwen3.5-plus-2026-04-20": {
        "label": "Qwen 3.5 Plus · Apr 2026",
        "description": "Pinned prior-gen release — stable for reproducible runs.",
    },
    "dashscope/qwen3.7-max": {
        "label": "Qwen 3.7 Max",
        "description": "DashScope latest Qwen flagship.",
    },
    "dashscope/qwen3-max": {
        "label": "Qwen 3 Max",
        "description": "DashScope prior flagship generation.",
    },
    "dashscope/qwen-max": {
        "label": "Qwen Max",
        "description": "DashScope Max stable alias.",
    },
    "dashscope/qwen-plus": {
        "label": "Qwen Plus",
        "description": "DashScope balanced cost/quality.",
    },
    "dashscope/qwen-flash": {
        "label": "Qwen Flash",
        "description": "DashScope fast, lower-cost text.",
    },
    "dashscope/qwen-turbo": {
        "label": "Qwen Turbo",
        "description": "DashScope lightweight, cheapest text tier.",
    },
    "dashscope/qwen3-coder-plus": {
        "label": "Qwen 3 Coder Plus",
        "description": "DashScope code-focused flagship.",
    },
    "dashscope/qwen3-coder-flash": {
        "label": "Qwen 3 Coder Flash",
        "description": "DashScope fast code model.",
    },
    "dashscope/qwen3-vl-plus": {
        "label": "Qwen 3 VL Plus",
        "description": "DashScope vision understanding.",
    },
    "dashscope/qwen3-vl-flash": {
        "label": "Qwen 3 VL Flash",
        "description": "DashScope fast vision model.",
    },
    "dashscope/deepseek-v4-pro": {
        "label": "DeepSeek V4 Pro",
        "description": "DeepSeek via DashScope OpenAI-compatible API.",
    },
    "dashscope/deepseek-v3.2": {
        "label": "DeepSeek V3.2",
        "description": "DeepSeek V3.2 via DashScope compatible API.",
    },
    "openrouter/z-ai/glm-4.7": {
        "label": "GLM 4.7",
        "description": "Z.ai GLM 4.7 served through OpenRouter.",
    },
    "openrouter/anthropic/claude-haiku-4.5": {
        "label": "Claude Haiku 4.5",
        "description": "Anthropic Claude Haiku 4.5 served through OpenRouter.",
    },
    "orcarouter/auto": {
        "label": "OrcaRouter auto",
        "description": "Adaptive routing across many models via OrcaRouter.",
    },
    "orcarouter/anthropic/claude-haiku-4.5": {
        "label": "Claude Haiku 4.5",
        "description": "Anthropic Claude Haiku 4.5 served through OrcaRouter.",
    },
}

PERSONA_MODEL_OPTIONS = list(PERSONA_MODEL_KNOB_META.keys())
DEFAULT_HARBOR_PERSONA_MODEL = DEFAULT_PERSONA_MODEL
HARBOR_PERSONA_MODEL_OPTIONS = PERSONA_MODEL_OPTIONS
RUNTIME_OPTIONS = ("local", "harbor")
EXECUTION_PLANE_OPTIONS = ("harbor", "remote")

__all__ = [
    "ConfigError",
    "ConfigManager",
    "DEFAULT_PERSONA_MODEL",
    "DEFAULT_HARBOR_PERSONA_MODEL",
    "PERSONA_MODEL_KNOB_META",
    "PERSONA_MODEL_OPTIONS",
    "HARBOR_PERSONA_MODEL_OPTIONS",
    "PERSONA_MODEL_ENV",
    "HARBOR_PERSONA_MODEL_ENV",
    "PLAYGROUND_RUNTIME_ENV",
    "EXECUTION_PLANE_ENV",
    "REMOTE_RUNNER_API_URL_ENV",
    "RUNTIME_OPTIONS",
    "EXECUTION_PLANE_OPTIONS",
    "persona_model",
    "harbor_persona_model",
    "playground_runtime",
    "default_execution_plane",
    "remote_runner_configured",
]


def persona_model() -> str:
    """Return the persona-agent model currently configured."""
    return (
        os.environ.get(PERSONA_MODEL_ENV, "").strip()
        or os.environ.get(HARBOR_PERSONA_MODEL_ENV, "").strip()
        or DEFAULT_PERSONA_MODEL
    )


def harbor_persona_model() -> str:
    """Backward-compatible alias for the old Harbor model env helper."""
    return persona_model()


def playground_runtime() -> str:
    """Return the selected Playground execution runtime."""
    value = os.environ.get(PLAYGROUND_RUNTIME_ENV, "local").strip().lower()
    if value not in RUNTIME_OPTIONS:
        raise ConfigError(
            "{} must be one of {}".format(
                PLAYGROUND_RUNTIME_ENV,
                ", ".join(RUNTIME_OPTIONS),
            )
        )
    return value


def default_execution_plane() -> str:
    """Return the default Harbor vs remote execution plane."""
    from backend.service.execution_plane import default_execution_plane as _default_plane

    return _default_plane()


def remote_runner_configured() -> bool:
    from backend.service.execution_plane import remote_runner_configured as _configured

    return _configured()


class ConfigError(ValueError):
    """Raised when a Playground config fails validation."""


class ConfigManager:
    """Validate Playground configs and map them to backend environment variables.

    The class is effectively a namespace of class attributes / class methods;
    there is no per-instance state, but it is instantiated by the API so it can
    be swapped or extended in tests.
    """

    #: Allowed values for each config key. Order is meaningful: the first entry
    #: of each list is the canonical default surfaced in :attr:`DEFAULTS`.
    ALLOWED: Dict[str, List[str]] = {
        "applicationId": [
            "meal_planning_nutrition",
            "finance_openbb",
            "acme_support_api",
            "acme_support_mcp",
        ],
        "engine": ["gpt-4o-mini", "gpt-4o"],
        "rankerMode": ["native"],
        "resourceMode": ["recai_resources"],
        "domain": ["movie", "beauty_product", "game"],
        "botType": ["chat", "completion"],
    }

    #: Default config used for brand-new sessions.
    DEFAULTS: Dict[str, str] = {
        "applicationId": "meal_planning_nutrition",
        "engine": "gpt-4o-mini",
        "rankerMode": "native",
        "resourceMode": "recai_resources",
        "domain": "movie",
        "botType": "chat",
    }

    #: Config keys whose change requires rebuilding (re-warming) the cached
    #: agent, because they alter agent construction / resources rather than
    #: just per-turn behavior.
    CACHE_INVALIDATING_KEYS: List[str] = [
        "applicationId",
        "engine",
        "rankerMode",
        "resourceMode",
        "domain",
        "botType",
    ]

    #: The user-editable knobs surfaced in the config bar, in display order.
    #: ``rankerMode`` / ``resourceMode`` are intentionally excluded — each has a
    #: single allowed value and is reported instead as a read-only fact in
    #: :attr:`ENVIRONMENT` (the native SASRec ranker / the ``all_resources``
    #: bundle), so the UI does not present a choice where none exists.
    EDITABLE_KEYS: List[str] = [
        "applicationId",
        "engine",
        "personaModel",
        "domain",
        "botType",
    ]

    #: Human-readable metadata per editable knob: a label, a one-line
    #: description, and per-value labels/descriptions. Keyed by config key; the
    #: allowed values come from :attr:`ALLOWED` so the two cannot drift.
    KNOB_META: Dict[str, Dict[str, object]] = {
        "applicationId": {
            "label": "Chatbot application",
            "description": "The application-under-test adapter used by the local runner.",
            "values": {
                "meal_planning_nutrition": {
                    "label": "Meal Planning Nutrition",
                    "description": "Nutrition and meal-planning chatbot adapter.",
                },
                "finance_openbb": {
                    "label": "FinAI / OpenBB",
                    "description": "Financial research chatbot adapter backed by OpenBB MCP.",
                },
                "acme_support_api": {
                    "label": "ACME Support API",
                    "description": "HTTP support chatbot adapter for the ACME support task.",
                },
                "acme_support_mcp": {
                    "label": "ACME Support MCP",
                    "description": "MCP support chatbot adapter for the ACME support task.",
                },
            },
        },
        "engine": {
            "label": "Application model",
            "description": "The OpenAI chat model that plans tool use and writes "
            "the application chatbot's replies.",
            "values": {
                "gpt-4o-mini": {
                    "label": "GPT-4o mini",
                    "description": "Faster and cheaper; the default.",
                },
                "gpt-4o": {
                    "label": "GPT-4o",
                    "description": "Higher quality, slower and pricier.",
                },
            },
        },
        "personaModel": {
            "label": "Persona model",
            "description": "The base model used to simulate the user side of Playground runs.",
            "values": PERSONA_MODEL_KNOB_META,
        },
        "domain": {
            "label": "Domain",
            "description": "Application-specific context. Changing it rebuilds "
            "the application adapter.",
            "values": {
                "movie": {
                    "label": "Movies",
                    "description": "The movie recommendation catalog.",
                },
                "beauty_product": {
                    "label": "Beauty products",
                    "description": "The beauty-product recommendation catalog.",
                },
                "game": {
                    "label": "Games",
                    "description": "The video-game recommendation catalog.",
                },
            },
        },
        "botType": {
            "label": "Reply style",
            "description": "How the agent is prompted to converse. Changing it "
            "rebuilds the agent (it is part of the agent's cache key).",
            "values": {
                "chat": {
                    "label": "Chat",
                    "description": "Conversational, multi-turn replies.",
                },
                "completion": {
                    "label": "Completion",
                    "description": "Single-shot completion-style replies.",
                },
            },
        },
    }

    #: Read-only facts about the fixed parts of the stack, surfaced alongside the
    #: editable knobs so the UI can show what is *not* configurable and why.
    ENVIRONMENT: Dict[str, object] = {
        "runtime": "In-process Harbor runner",
        "personaAgent": "Playground simulated user",
        "applicationApi": "direct application adapter",
        "scorer": "Playground self-report scorer",
        "cache": "local service and model caches",
        "ranker": "application-specific ranking / tool selection",
        "resources": "adapter-specific resources",
        "agent": "chatbot application adapter",
        "promptOwnership": {
            "personaSystemPrompt": "Persona prompt from Playground",
            "taskPrompt": "Application-provided chatbot simulation prompt",
        },
    }

    def options(self) -> Dict[str, object]:
        """Return the config metadata the UI renders.

        Shape::

            {
              "knobs": [
                {
                  "key": "engine",
                  "label": "Model",
                  "description": "...",
                  "options": [
                    {"value": "gpt-4o-mini", "label": "...", "description": "..."},
                    ...
                  ],
                  "rebuildsAgent": false
                },
                ...
              ],
              "defaults": {<full config defaults>},
              "environment": {"ranker": "...", "resources": "...", "agent": "..."}
            }

        ``knobs`` covers only the user-editable keys (:attr:`EDITABLE_KEYS`), each
        enriched from :attr:`KNOB_META` with per-value labels/descriptions and a
        ``rebuildsAgent`` flag (whether changing it cold-starts the agent —
        :attr:`CACHE_INVALIDATING_KEYS`). ``defaults`` is the *full* canonical
        config (all keys, including the fixed ranker/resource modes) so callers
        can still seed a complete session. ``environment`` reports the fixed
        parts of the stack as read-only facts.
        """
        knobs: List[Dict[str, object]] = []
        for key in self.EDITABLE_KEYS:
            meta = self.KNOB_META.get(key, {})
            value_meta = meta.get("values", {})
            value_meta = value_meta if isinstance(value_meta, dict) else {}
            option_views: List[Dict[str, str]] = []
            allowed_values = (
                PERSONA_MODEL_OPTIONS
                if key == "personaModel"
                else self.ALLOWED.get(key, [])
            )
            for value in allowed_values:
                vm = value_meta.get(value, {})
                vm = vm if isinstance(vm, dict) else {}
                option_views.append(
                    {
                        "value": value,
                        "label": str(vm.get("label", value)),
                        "description": str(vm.get("description", "")),
                    }
                )
            knobs.append(
                {
                    "key": key,
                    "label": str(meta.get("label", key)),
                    "description": str(meta.get("description", "")),
                    "options": option_views,
                    "rebuildsAgent": key in self.CACHE_INVALIDATING_KEYS,
                }
            )
        return {
            "knobs": knobs,
            "defaults": dict(self.DEFAULTS),
            "environment": {
                **self.ENVIRONMENT,
                "runtime": _runtime_label(playground_runtime()),
                "executionPlane": default_execution_plane(),
                "remoteRunnerConfigured": remote_runner_configured(),
                "personaModel": persona_model(),
            },
        }

    def normalize(self, cfg: Optional[Dict[str, object]]) -> Dict[str, str]:
        """Return a full, validated config, filling missing keys from defaults.

        Unknown keys are rejected (raises :class:`ConfigError`). The returned
        dict is a fresh copy containing exactly the keys in :attr:`DEFAULTS`.
        """
        merged: Dict[str, str] = dict(self.DEFAULTS)
        if cfg:
            for key, value in cfg.items():
                if key not in self.ALLOWED:
                    raise ConfigError("Unknown config key: {!r}".format(key))
                merged[key] = value  # type: ignore[assignment]
        self.validate(merged)
        return merged

    def validate(self, cfg: Dict[str, object]) -> None:
        """Validate a (possibly partial) config; raise on the first problem.

        Each present key must be one of :attr:`ALLOWED`; each value must be in
        the allowed list for that key. Missing keys are permitted here so the
        method can be used on patches; use :meth:`normalize` to also fill
        defaults.
        """
        if not isinstance(cfg, dict):
            raise ConfigError("config must be an object/dict")
        for key, value in cfg.items():
            if key not in self.ALLOWED:
                raise ConfigError("Unknown config key: {!r}".format(key))
            allowed = self.ALLOWED[key]
            if value not in allowed:
                raise ConfigError(
                    "Invalid value {!r} for {!r}; allowed: {}".format(
                        value, key, ", ".join(allowed)
                    )
                )

    def to_env(self, cfg: Dict[str, object]) -> Dict[str, str]:
        """Translate a config to the ``INTERECAGENT_*`` environment variables.

        The input is normalized first (defaults filled, validated), so callers
        may pass a partial config. ``INTERECAGENT_CACHE_AGENT`` is always set to
        ``'1'`` so the backend reuses its module-global agent cache.
        """
        full = self.normalize(cfg)
        return {
            "INTERECAGENT_ENGINE": str(full["engine"]),
            "INTERECAGENT_RANKER_MODE": str(full["rankerMode"]),
            "INTERECAGENT_RESOURCE_MODE": str(full["resourceMode"]),
            "INTERECAGENT_DOMAIN": str(full["domain"]),
            "INTERECAGENT_BOT_TYPE": str(full["botType"]),
            "INTERECAGENT_CACHE_AGENT": "1",
            "MATRIX_CHATBOT_APPLICATION_ID": str(full["applicationId"]),
        }

    def apply(
        self,
        cfg: Dict[str, object],
        environ: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Write the config's ``INTERECAGENT_*`` variables into the environment.

        Computes :meth:`to_env` (which normalizes + validates ``cfg``) and sets
        each variable on ``environ`` (defaulting to :data:`os.environ`). This is
        called by the session right before invoking the backend so the cached
        agent is (re)built with the active knobs. Returns the env dict applied.
        """
        target = os.environ if environ is None else environ
        env = self.to_env(cfg)
        for key, value in env.items():
            target[key] = value
        return env

    def cache_invalidating(
        self, old: Optional[Dict[str, object]], new: Optional[Dict[str, object]]
    ) -> bool:
        """Return ``True`` if moving from ``old`` to ``new`` rebuilds the agent.

        A change to any of :attr:`CACHE_INVALIDATING_KEYS`
        (engine / rankerMode / resourceMode / domain / botType) invalidates the
        cached agent — ``botType`` is included because the bridge folds
        ``INTERECAGENT_BOT_TYPE`` into its agent cache key. Both configs are
        normalized first so that "default vs. explicit-default" comparisons do
        not register as changes.
        """
        old_full = self.normalize(old)
        new_full = self.normalize(new)
        for key in self.CACHE_INVALIDATING_KEYS:
            if old_full.get(key) != new_full.get(key):
                return True
        return False


def _runtime_label(runtime: str) -> str:
    if runtime == "harbor":
        return "Harbor persona runner"
    return "In-process Harbor runner"
