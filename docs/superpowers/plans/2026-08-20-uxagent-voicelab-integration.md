# UXAgent–VoiceLab Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a clean-room, UXAgent-inspired dual-system persona agent that creates one VoiceLab persona session per Vita trial and drives `/api/agent/chat` while preserving existing verifier evidence.

**Architecture:** `persona-uxagent` remains a thin Harbor adapter. A new `playground.uxagent` package owns original prompts, memory/policy state, VoiceLab HTTP contracts, and the trial loop. Vita auto-selection changes only for `application/tasks/chat_vita-*`; other chat tasks keep `persona-user-sim`.

**Tech Stack:** Python 3.12, asyncio, httpx, Pydantic v2, existing Playground model clients and artifact types, Harbor `BaseAgent`, pytest.

---

## File Structure

**Create**

- `packages/playground/src/playground/uxagent/__init__.py` — public clean-room UXAgent API.
- `packages/playground/src/playground/uxagent/models.py` — validated policy, memory, provider request, and provider response models.
- `packages/playground/src/playground/uxagent/mapping.py` — persona/task-to-VoiceLab contract mapping; no model calls or I/O.
- `packages/playground/src/playground/uxagent/client.py` — async VoiceLab HTTP client and typed failures.
- `packages/playground/src/playground/uxagent/prompts.py` — original MatrAIx prompts; no copied UXAgent text.
- `packages/playground/src/playground/uxagent/policy.py` — fast loop, asynchronous slow loop, memory, and strict `send_message` action generation.
- `packages/playground/src/playground/uxagent/runner.py` — per-trial session lifecycle, turn loop, artifacts, and cleanup.
- `environment/agents/matraix/agents/persona/uxagent.py` — Harbor `PersonaUXAgent` adapter.
- `docs/third-party/uxagent-clean-room-notice.txt` — provenance and licensing constraint.
- `packages/playground/src/playground/tests/test_uxagent_mapping.py` — mapping contracts.
- `packages/playground/src/playground/tests/test_uxagent_client.py` — HTTP/auth/schema/failure contracts.
- `packages/playground/src/playground/tests/test_uxagent_policy.py` — dual-loop/action/cleanup behavior.
- `packages/playground/src/playground/tests/test_uxagent_runner.py` — trial lifecycle and artifacts.

**Modify**

- `packages/playground/pyproject.toml:7-9,18-19` — declare runtime dependencies and package prompt/provenance data only if needed.
- `environment/runtime/harbor/models/agent/name.py:35-46` — add `PERSONA_UXAGENT`.
- `environment/runtime/harbor/agents/factory.py:59-86` — lazy-map the new agent.
- `environment/agents/matraix/agents/persona/__init__.py:7-63` — export the adapter lazily.
- `src/matraix/persona_agent_context.py:1-7` — document the Vita-specific agent without changing global chatbot defaults.
- `application/playground/backend/service/harbor_job_service.py:135-167` — select `persona-uxagent` for Vita auto-mode before the generic `user_sim_chat` branch.
- `scripts/generate_vita_agent_tasks.py:843-869` — add the `uxagent` task tag so regenerated Vita tasks keep explicit catalog provenance.
- `application/tasks/chat_vita-*/task.toml` — regenerated tag-only changes.
- `tests/environment/test_persona_agents.py:44-70` — registration/export/package assertions.
- `application/playground/backend/tests/test_harbor_job_service.py:337-363` — Vita-specific selection and non-Vita regression tests.
- `tests/vita/test_task_catalog.py:27-58` — assert every generated Vita task is tagged for UXAgent evaluation.
- `docs/environment/README.md:107-131` and `docs/environment/agents.md` relevant agent table — operator configuration and run command.

Do not modify the existing Vita oracle, verifier, reporting JSON, `input/chatbot.yaml` structured-exposure fields, or global `DEFAULT_AGENT_BY_TYPE` mapping.

---

### Task 1: Clean-room provenance and contract models

**Files:**
- Create: `docs/third-party/uxagent-clean-room-notice.txt`
- Create: `packages/playground/src/playground/uxagent/__init__.py`
- Create: `packages/playground/src/playground/uxagent/models.py`
- Modify: `packages/playground/pyproject.toml:7-9`
- Test: `packages/playground/src/playground/tests/test_uxagent_mapping.py`

- [ ] **Step 1: Write the failing model/provenance test**

```python
# packages/playground/src/playground/tests/test_uxagent_mapping.py
from pathlib import Path

import pytest
from pydantic import ValidationError

from playground.uxagent.models import SendMessageAction, VoiceLabAgentChatResponse


def test_send_message_action_rejects_blank_message() -> None:
    with pytest.raises(ValidationError):
        SendMessageAction(message="   ")


def test_agent_chat_response_requires_reply_and_evidence_shape() -> None:
    response = VoiceLabAgentChatResponse.model_validate(
        {
            "reply": "Đã đặt 22 độ.",
            "decision": "executed",
            "vehicleState": {"temperature": 22},
            "action": {"tool": "set_temperature"},
            "toolResult": {"ok": True},
            "capabilityIds": ["climate.set_temperature"],
            "runtimeContext": {"vehicleMotion": "driving"},
        }
    )
    assert response.reply == "Đã đặt 22 độ."
    assert response.model_dump(by_alias=True)["vehicleState"] == {"temperature": 22}


def test_clean_room_notice_records_unlicensed_upstream_revision() -> None:
    root = Path(__file__).resolve().parents[5]
    notice = (root / "docs/third-party/uxagent-clean-room-notice.txt").read_text()
    assert "https://github.com/neuhai/UXAgent" in notice
    assert "4d3b1f1c1fef93c5e2ea7d104153ea164ba1acbd" in notice
    assert "No source code or prompt text was copied" in notice
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run:

```bash
uv run pytest packages/playground/src/playground/tests/test_uxagent_mapping.py -q
```

Expected: collection fails because `playground.uxagent` and the notice do not exist.

- [ ] **Step 3: Add validated models and the clean-room notice**

`packages/playground/src/playground/uxagent/models.py` must define the complete public wire/state types:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SendMessageAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["send_message"] = "send_message"
    message: str
    end_reason: str | None = None

    @field_validator("message")
    @classmethod
    def non_blank_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class VoiceLabPersonaSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sessionId: str
    source: Literal["matraix-uxagent"] = "matraix-uxagent"
    driver: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class VoiceLabAgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str
    drivingContext: str
    intent: str
    personaSessionId: str


class VoiceLabAgentChatResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    reply: str
    decision: str | None = None
    vehicle_state: dict[str, Any] | None = Field(default=None, alias="vehicleState")
    action: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = Field(default=None, alias="toolResult")
    capability_ids: list[str] = Field(default_factory=list, alias="capabilityIds")
    runtime_context: dict[str, Any] = Field(default_factory=dict, alias="runtimeContext")

    @field_validator("reply")
    @classmethod
    def non_blank_reply(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reply must not be blank")
        return value


class UXMemory(BaseModel):
    kind: Literal["observation", "reflection", "wonder", "plan", "action"]
    content: str
    importance: float = Field(ge=0.0, le=1.0)
    turn_index: int = Field(ge=0)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class UXObservation(BaseModel):
    task_intent: str
    turn_index: int = Field(ge=0)
    assistant_reply: str = ""
    decision: str | None = None
    vehicle_state: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    capability_ids: list[str] = Field(default_factory=list)
    runtime_context: dict[str, Any] = Field(default_factory=dict)
```

`packages/playground/src/playground/uxagent/__init__.py` exports only stable types initially:

```python
from playground.uxagent.models import (
    SendMessageAction,
    VoiceLabAgentChatRequest,
    VoiceLabAgentChatResponse,
    VoiceLabPersonaSessionRequest,
)

__all__ = [
    "SendMessageAction",
    "VoiceLabAgentChatRequest",
    "VoiceLabAgentChatResponse",
    "VoiceLabPersonaSessionRequest",
]
```

Add `httpx>=0.27.0` and `pydantic>=2.11.7` to `packages/playground/pyproject.toml` dependencies. Write `docs/third-party/uxagent-clean-room-notice.txt` with this exact factual content:

```text
UXAgent clean-room architecture notice

Concept source: https://github.com/neuhai/UXAgent
Revision inspected: 4d3b1f1c1fef93c5e2ea7d104153ea164ba1acbd

The inspected repository README displays an MIT badge, but that revision has no
LICENSE file and GitHub reports no detected license. No source code or prompt
text was copied into MatrAIx. The MatrAIx conversational policy independently
implements the published fast-loop and slow-loop concepts using original code
and prompts.
```

- [ ] **Step 4: Run the model/provenance test**

Run:

```bash
uv run pytest packages/playground/src/playground/tests/test_uxagent_mapping.py -q
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/playground/pyproject.toml packages/playground/src/playground/uxagent packages/playground/src/playground/tests/test_uxagent_mapping.py docs/third-party/uxagent-clean-room-notice.txt
git commit -m "feat: define VoiceLab UXAgent contracts"
```

---

### Task 2: Persona and Vita task mapping

**Files:**
- Create: `packages/playground/src/playground/uxagent/mapping.py`
- Modify: `packages/playground/src/playground/tests/test_uxagent_mapping.py`

- [ ] **Step 1: Add failing mapping tests**

Append tests using a small object with the same public fields as `matraix.agents.persona.loader.Persona`:

```python
from types import SimpleNamespace

from playground.chatbot_task_config import (
    ChatbotProtocolConfig,
    ChatbotRuntimeDefaults,
    ChatbotTaskConfig,
)
from playground.uxagent.mapping import build_chat_request, build_persona_session_request


def _persona():
    return SimpleNamespace(
        display_name="Anh Hải",
        summary="Bận rộn, thích câu trả lời ngắn.",
        system_prompt=None,
        communication={"style": "ngắn, tự nhiên"},
        psychology={"traits": ["thích sự riêng tư"]},
        preferences={"temperature": 22, "music": "nhạc nhẹ"},
        behavior={},
        data={"context": {"mood": "mệt", "fatigueLevel": "high"}},
    )


def _runtime():
    return ChatbotTaskConfig(
        runtime_defaults=ChatbotRuntimeDefaults(max_turns=4),
        protocol=ChatbotProtocolConfig(
            static_body={
                "scenarioId": "climate-temperature",
                "runtimeContext": {
                    "vehicleMotion": "driving",
                    "language": "vi",
                    "roadSituation": "đường đông",
                },
            }
        ),
    )


def test_maps_only_available_persona_and_runtime_fields() -> None:
    payload = build_persona_session_request(
        persona=_persona(), runtime=_runtime(), session_id="trial-001"
    ).model_dump(exclude_none=True)
    assert payload["sessionId"] == "trial-001"
    assert payload["driver"] == {
        "name": "Anh Hải",
        "persona": "Bận rộn, thích câu trả lời ngắn.",
        "communicationStyle": "ngắn, tự nhiên",
        "traits": ["thích sự riêng tư"],
        "preferences": {"temperature": 22, "music": "nhạc nhẹ"},
    }
    assert payload["context"] == {
        "mood": "mệt",
        "fatigueLevel": "high",
        "roadSituation": "đường đông",
    }
    assert "stressLevel" not in payload["context"]


def test_chat_request_uses_trial_session_and_vita_scenario() -> None:
    payload = build_chat_request(
        message="Cho anh 22 độ.", runtime=_runtime(), session_id="trial-001"
    )
    assert payload.model_dump() == {
        "message": "Cho anh 22 độ.",
        "drivingContext": "driving",
        "intent": "climate-temperature",
        "personaSessionId": "trial-001",
    }
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

```bash
uv run pytest packages/playground/src/playground/tests/test_uxagent_mapping.py -q
```

Expected: collection fails on `playground.uxagent.mapping`.

- [ ] **Step 3: Implement deterministic mapping without guessed values**

Create helpers that accept `object` rather than importing the Harbor persona package into Playground:

```python
from __future__ import annotations

from typing import Any, Mapping

from playground.chatbot_task_config import ChatbotTaskConfig
from playground.uxagent.models import VoiceLabAgentChatRequest, VoiceLabPersonaSessionRequest


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _without_empty(values: Mapping[str, object]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, "", [], {})}


def build_persona_session_request(
    *, persona: object, runtime: ChatbotTaskConfig, session_id: str
) -> VoiceLabPersonaSessionRequest:
    data = _mapping(getattr(persona, "data", {}))
    communication = _mapping(getattr(persona, "communication", {}))
    psychology = _mapping(getattr(persona, "psychology", {}))
    preferences = _mapping(getattr(persona, "preferences", {}))
    persona_context = _mapping(data.get("context"))
    runtime_context = _mapping(runtime.protocol.static_body.get("runtimeContext"))
    driver = _without_empty(
        {
            "name": _text(getattr(persona, "display_name", None)),
            "persona": _text(getattr(persona, "summary", None))
            or _text(getattr(persona, "system_prompt", None)),
            "communicationStyle": _text(communication.get("style")),
            "traits": psychology.get("traits"),
            "preferences": preferences,
        }
    )
    context = _without_empty(
        {
            "mood": persona_context.get("mood"),
            "tripPurpose": persona_context.get("tripPurpose"),
            "stressLevel": persona_context.get("stressLevel"),
            "fatigueLevel": persona_context.get("fatigueLevel"),
            "roadSituation": persona_context.get("roadSituation")
            or runtime_context.get("roadSituation"),
        }
    )
    return VoiceLabPersonaSessionRequest(
        sessionId=session_id,
        driver=driver,
        context=context,
        notes=[],
    )


def build_chat_request(
    *, message: str, runtime: ChatbotTaskConfig, session_id: str
) -> VoiceLabAgentChatRequest:
    static_body = runtime.protocol.static_body
    runtime_context = _mapping(static_body.get("runtimeContext"))
    return VoiceLabAgentChatRequest(
        message=message,
        drivingContext=_text(runtime_context.get("vehicleMotion")) or "unknown",
        intent=_text(static_body.get("scenarioId"))
        or runtime.runtime_defaults.application_context
        or runtime.runtime_defaults.application_id,
        personaSessionId=session_id,
    )
```

The `"unknown"` driving context is a protocol-required value, not inferred vehicle state. Vita fixtures provide `vehicleMotion`, so focused catalog tests must never observe it.

- [ ] **Step 4: Run mapping tests**

```bash
uv run pytest packages/playground/src/playground/tests/test_uxagent_mapping.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/playground/src/playground/uxagent/mapping.py packages/playground/src/playground/tests/test_uxagent_mapping.py
git commit -m "feat: map personas to VoiceLab sessions"
```

---

### Task 3: Strict asynchronous VoiceLab client

**Files:**
- Create: `packages/playground/src/playground/uxagent/client.py`
- Create: `packages/playground/src/playground/tests/test_uxagent_client.py`

- [ ] **Step 1: Write failing HTTP contract tests**

Use `httpx.MockTransport`; never start a real service in unit tests:

```python
import json

import httpx
import pytest

from playground.uxagent.client import VoiceLabContractError, VoiceLabPersonaClient
from playground.uxagent.models import VoiceLabAgentChatRequest, VoiceLabPersonaSessionRequest


@pytest.mark.asyncio
async def test_client_sends_auth_and_exact_contract_paths() -> None:
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers, json.loads(request.content)))
        if request.url.path == "/api/persona/session":
            return httpx.Response(200, json={"active": {"sessionId": "trial-1"}, "sessions": []})
        return httpx.Response(200, json={"reply": "Đã hiểu.", "decision": "executed"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = VoiceLabPersonaClient(
            base_url="http://voicelab.test",
            app_password="secret-value",
            http_client=http,
        )
        await client.create_session(
            VoiceLabPersonaSessionRequest(sessionId="trial-1", driver={"persona": "x"})
        )
        await client.agent_chat(
            VoiceLabAgentChatRequest(
                message="Xin chào",
                drivingContext="driving",
                intent="casual_chat",
                personaSessionId="trial-1",
            )
        )

    assert [item[0] for item in seen] == ["/api/persona/session", "/api/agent/chat"]
    assert all(item[1]["x-app-password"] == "secret-value" for item in seen)
    assert seen[1][2]["personaSessionId"] == "trial-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [httpx.Response(503, text="down"), httpx.Response(200, text="not-json")],
)
async def test_client_raises_redacted_contract_error(response: httpx.Response) -> None:
    transport = httpx.MockTransport(lambda request: response)
    async with httpx.AsyncClient(transport=transport) as http:
        client = VoiceLabPersonaClient(
            base_url="http://voicelab.test",
            app_password="secret-value",
            http_client=http,
        )
        with pytest.raises(VoiceLabContractError) as exc:
            await client.create_session(
                VoiceLabPersonaSessionRequest(sessionId="trial-1", driver={"persona": "x"})
            )
    assert "secret-value" not in str(exc.value)
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest packages/playground/src/playground/tests/test_uxagent_client.py -q
```

Expected: collection fails because `playground.uxagent.client` does not exist.

- [ ] **Step 3: Implement the client with owned/unowned client lifecycle**

```python
from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import ValidationError

from playground.uxagent.models import (
    VoiceLabAgentChatRequest,
    VoiceLabAgentChatResponse,
    VoiceLabPersonaSessionRequest,
)


class VoiceLabContractError(RuntimeError):
    pass


class VoiceLabPersonaClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        app_password: str | None = None,
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("VOICELAB_API_URL") or "http://localhost:3001"
        ).rstrip("/")
        self._app_password = app_password if app_password is not None else os.environ.get("APP_PASSWORD", "")
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._app_password:
            headers["x-app-password"] = self._app_password
        return headers

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._http.post(
                f"{self.base_url}{path}", json=payload, headers=self._headers()
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VoiceLabContractError(f"VoiceLab request failed for {path}") from exc
        if not isinstance(body, dict):
            raise VoiceLabContractError(f"VoiceLab response for {path} must be an object")
        return body

    async def create_session(self, request: VoiceLabPersonaSessionRequest) -> dict[str, Any]:
        body = await self._post(
            "/api/persona/session", request.model_dump(exclude_none=True)
        )
        active = body.get("active")
        if not isinstance(active, dict) or active.get("sessionId") != request.sessionId:
            raise VoiceLabContractError("VoiceLab persona response has wrong active session")
        return body

    async def agent_chat(
        self, request: VoiceLabAgentChatRequest
    ) -> VoiceLabAgentChatResponse:
        body = await self._post("/api/agent/chat", request.model_dump())
        try:
            return VoiceLabAgentChatResponse.model_validate(body)
        except ValidationError as exc:
            raise VoiceLabContractError("VoiceLab agent response violates contract") from exc

    async def close(self) -> None:
        if self._owns_client:
            await self._http.aclose()
```

Do not add retries. A retry can duplicate a vehicle action when the server executes the request but the client misses the response.

- [ ] **Step 4: Run client tests**

```bash
uv run pytest packages/playground/src/playground/tests/test_uxagent_client.py -q
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/playground/src/playground/uxagent/client.py packages/playground/src/playground/tests/test_uxagent_client.py
git commit -m "feat: add VoiceLab persona client"
```

---

### Task 4: Clean-room dual-system conversational policy

**Files:**
- Create: `packages/playground/src/playground/uxagent/prompts.py`
- Create: `packages/playground/src/playground/uxagent/policy.py`
- Create: `packages/playground/src/playground/tests/test_uxagent_policy.py`

- [ ] **Step 1: Write failing policy behavior tests**

Use a deterministic fake JSON client so tests defend behavior rather than model wording:

```python
import asyncio

import pytest

from playground.uxagent.models import UXObservation
from playground.uxagent.policy import ConversationalUXPolicy


class FakeJsonClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def complete_json(self, system: str, user: str):
        self.calls.append((system, user))
        return self.outputs.pop(0)


@pytest.mark.asyncio
async def test_fast_loop_returns_only_send_message_and_records_memory() -> None:
    llm = FakeJsonClient(
        [
            {"observations": ["Xe đang chạy; người lái muốn giảm nhiệt độ."], "importance": 0.8},
            {"plan": "Yêu cầu đặt nhiệt độ ngắn gọn."},
            {"action": "send_message", "message": "Cho anh 22 độ.", "end_reason": None},
        ]
    )
    policy = ConversationalUXPolicy(
        persona_system="Anh Hải thích câu trả lời ngắn.",
        task_intent="Đặt điều hòa 22 độ.",
        json_client=llm,
    )
    action = await policy.next_action(UXObservation(task_intent="climate-temperature", turn_index=0))
    assert action.message == "Cho anh 22 độ."
    assert [memory.kind for memory in policy.memories] == ["observation", "plan", "action"]
    await policy.close()


@pytest.mark.asyncio
async def test_slow_loop_processes_observation_and_closes_without_leaking_task() -> None:
    llm = FakeJsonClient(
        [
            {"reflections": ["Giữ câu ngắn vì xe đang chạy."], "wonders": ["Phản hồi có xác nhận hành động không?"]},
        ]
    )
    policy = ConversationalUXPolicy(
        persona_system="Persona",
        task_intent="Task",
        json_client=llm,
    )
    policy.start_slow_loop()
    await policy.enqueue_slow_observation(
        UXObservation(task_intent="task", turn_index=1, assistant_reply="Đã hiểu.")
    )
    await asyncio.wait_for(policy.wait_until_slow_idle(), timeout=1)
    await policy.close()
    assert policy.slow_task is None
    assert {memory.kind for memory in policy.memories} == {"reflection", "wonder"}
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest packages/playground/src/playground/tests/test_uxagent_policy.py -q
```

Expected: collection fails because policy modules do not exist.

- [ ] **Step 3: Write original prompts**

`prompts.py` defines MatrAIx-owned prompts. They must state the JSON schema, Vietnamese-driver constraint, safety boundary, and that the persona cannot authorize unsafe actions. Do not consult or reproduce upstream prompt files while writing them.

```python
PERCEIVE_SYSTEM = """Extract only facts relevant to the driver's current goal, persona, and vehicle context. Persona preferences affect wording and choices but never override vehicle safety. Return JSON: {\"observations\": [string], \"importance\": number from 0 to 1}."""

PLAN_SYSTEM = """Choose the next conversational move for a Vietnamese driver. Keep the move consistent with the persona and task, avoid claiming that a vehicle action succeeded before the assistant reports it, and respect the turn limit. Return JSON: {\"plan\": string}."""

ACT_SYSTEM = """Produce exactly one driver utterance in Vietnamese. The only allowed action is send_message. Do not emit browser, shell, or vehicle-tool actions; VoiceLab owns tool execution and safety checks. Return JSON: {\"action\": \"send_message\", \"message\": string, \"end_reason\": string or null}."""

SLOW_SYSTEM = """Review the latest conversation observation against the persona and goal. Return durable insights and unanswered questions without inventing state. Return JSON: {\"reflections\": [string], \"wonders\": [string]}."""
```

- [ ] **Step 4: Implement policy with a queue-backed slow loop**

`policy.py` must:

- accept any existing `build_json_client()` object through a `JsonClient` protocol;
- call synchronous clients via `asyncio.to_thread`;
- serialize persona, task, recent memories, and observation to JSON;
- validate every action with `SendMessageAction`;
- cap retained memory to the newest 100 entries;
- process each post-turn observation once through an `asyncio.Queue`;
- use `queue.join()` for deterministic cleanup and cancel/await the worker.

Expose these exact methods on `ConversationalUXPolicy`: constructor keyword arguments `persona_system: str`, `task_intent: str`, and `json_client: JsonClient`; read-only `memories -> tuple[UXMemory, ...]`; async `next_action(observation: UXObservation) -> SendMessageAction`; synchronous `start_slow_loop() -> None`; async `enqueue_slow_observation(observation: UXObservation) -> None`; async `wait_until_slow_idle() -> None`; and async `close() -> None`.

The fast loop performs three model calls in order: perceive, plan, act. The slow worker performs one combined reflect/wonder call per queued post-turn observation. `close()` first waits for queued work, then cancels and awaits the worker under `contextlib.suppress(asyncio.CancelledError)`.

- [ ] **Step 5: Run policy tests**

```bash
uv run pytest packages/playground/src/playground/tests/test_uxagent_policy.py -q
```

Expected: 2 passed and no pending-task warning.

- [ ] **Step 6: Commit**

```bash
git add packages/playground/src/playground/uxagent/prompts.py packages/playground/src/playground/uxagent/policy.py packages/playground/src/playground/tests/test_uxagent_policy.py
git commit -m "feat: add clean-room conversational UX policy"
```

---

### Task 5: Per-trial VoiceLab runner and artifacts

**Files:**
- Create: `packages/playground/src/playground/uxagent/runner.py`
- Create: `packages/playground/src/playground/tests/test_uxagent_runner.py`
- Modify: `packages/playground/src/playground/uxagent/__init__.py`

- [ ] **Step 1: Write the failing lifecycle test**

Build fakes for the policy, client, and Harbor environment. The test must observe call order and uploaded artifacts:

```python
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from playground.chatbot_task_config import (
    ChatbotProtocolConfig,
    ChatbotRuntimeDefaults,
    ChatbotStructuredExposureField,
    ChatbotTaskConfig,
)
from playground.uxagent.models import SendMessageAction, VoiceLabAgentChatResponse
from playground.types import Questionnaire
from playground.uxagent.runner import UXAgentTrialRunner

class FakeVoiceLabClient:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.closed = False

    async def create_session(self, request):
        self.calls.append(("create_session", request.sessionId))
        return {"active": {"sessionId": request.sessionId}, "sessions": []}

    async def agent_chat(self, request):
        self.calls.append(("agent_chat", request.personaSessionId))
        return self.response

    async def close(self):
        self.closed = True


class FakePolicy:
    def __init__(self, actions):
        self.actions = list(actions)
        self.closed = False
        self.slow_task = None
        self._memories = ()

    @property
    def memories(self):
        return self._memories

    def start_slow_loop(self):
        self.slow_task = object()

    async def next_action(self, observation):
        return self.actions.pop(0)

    async def enqueue_slow_observation(self, observation):
        return None

    async def close(self):
        self.closed = True
        self.slow_task = None


class FakeEnvironment:
    def __init__(self, root: Path, trial_name: str):
        self.trial_paths = SimpleNamespace(trial_dir=root / trial_name)
        self.uploads = {}

    async def upload_file(self, source: Path, destination: str):
        self.uploads[destination] = source.read_text(encoding="utf-8")


def _persona():
    return SimpleNamespace(
        persona_id="persona-1",
        display_name="Anh Hải",
        summary="Thích câu ngắn.",
        system_prompt=None,
        communication={"style": "ngắn"},
        psychology={},
        preferences={},
        behavior={},
        data={},
        persona_path=Path("persona.yaml"),
    )


@pytest.mark.asyncio
async def test_runner_creates_one_session_and_preserves_voicelab_evidence(tmp_path: Path) -> None:
    # Fake client records one create followed by one chat and returns a terminal decision.
    client = FakeVoiceLabClient(
        VoiceLabAgentChatResponse.model_validate(
            {
                "reply": "Đã đặt 22 độ.",
                "decision": "executed",
                "vehicleState": {"temperature": 22},
                "action": {"tool": "set_temperature"},
                "toolResult": {"ok": True},
                "capabilityIds": ["climate.set_temperature"],
                "runtimeContext": {"vehicleMotion": "driving"},
            }
        )
    )
    policy = FakePolicy([SendMessageAction(message="Cho anh 22 độ.")])
    environment = FakeEnvironment(tmp_path, trial_name="trial-abc")
    runtime = ChatbotTaskConfig(
        runtime_defaults=ChatbotRuntimeDefaults(
            application_id="vita_climate", application_context="automotive", domain="automotive", max_turns=4
        ),
        protocol=ChatbotProtocolConfig(
            static_body={"scenarioId": "climate-temperature", "runtimeContext": {"vehicleMotion": "driving"}}
        ),
        structured_exposure=(
            ChatbotStructuredExposureField("decision", "Decision", "decision"),
            ChatbotStructuredExposureField("vehicle_state", "Vehicle", "vehicleState", "json"),
            ChatbotStructuredExposureField("tool_result", "Tool", "toolResult", "json"),
        ),
    )

    runner = UXAgentTrialRunner(
        client=client,
        policy=policy,
        questionnaire_builder=lambda **kwargs: Questionnaire(
            5, "ok", 5, "ok", 5, "ok", False, ""
        ),
    )
    result = await runner.run(
        environment=environment,
        persona=_persona(),
        runtime=runtime,
        task_intent="Đặt điều hòa 22 độ.",
        on_event=None,
    )

    assert client.calls[0] == ("create_session", "trial-abc")
    assert client.calls[1] == ("agent_chat", "trial-abc")
    transcript = json.loads(environment.uploads["/app/output/transcript.json"])
    assert transcript["turns"][0]["structuredExposure"][0]["value"] == "executed"
    assert result.metric_scores.num_turns == 1
    assert policy.closed is True
    assert client.closed is True
```

The runner accepts a `questionnaire_builder` callable; production defaults to the existing task-owned self-report builder, while the test injects the deterministic builder shown above.

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest packages/playground/src/playground/tests/test_uxagent_runner.py -q
```

Expected: collection fails because `UXAgentTrialRunner` does not exist.

- [ ] **Step 3: Implement the runner using existing normalization/reporting contracts**

The runner must use:

- `normalize_agent_turn(response.model_dump(by_alias=True), message, structured_exposure_fields=runtime.structured_exposure)`;
- `PlaygroundTurn`, `PlaygroundResult`, and `MetricScores` from `playground.types`;
- `final_self_report` with the existing task-owned schema after the turn loop;
- `normalize_transcript_payload` before upload;
- `harbor_output_artifacts_from_result` to keep artifact names and application metadata stable.

Implement `UXAgentTrialRunner.run` as this ordered algorithm:

1. Set `session_id = environment.trial_paths.trial_dir.name`.
2. Build and create exactly one persona session before starting the policy.
3. Start the slow loop and iterate `range(1, (runtime.runtime_defaults.max_turns or 4) + 1)`.
4. Build `UXObservation` from the previous VoiceLab response, call `policy.next_action`, build a chat request, and await `client.agent_chat`.
5. Normalize the response with the task's `structured_exposure` selectors, append one `PlaygroundTurn`, enqueue the post-turn observation, and stop on `cancelled`, `denied`, `executed`, `failed`, `unsupported`, or `action.end_reason`.
6. Build `PlaygroundConfig` from `runtime.runtime_defaults`, convert the loaded persona with the same field mapping currently used by `harbor.chat_eval`, call the injected questionnaire builder, and construct `PlaygroundResult`.
7. Normalize `{"sessionId": session_id, "turns": [turn.to_dict() for turn in turns]}` with `normalize_transcript_payload`.
8. Upload `harbor_output_artifacts_from_result(result, session_id=session_id, transcript_payload=transcript_payload)` plus `{"sessionId": session_id, "memories": [memory.model_dump() for memory in self.policy.memories]}` as `uxagent_memory.json`.
9. Return the result.
10. In `finally`, await `policy.close()` and then `client.close()`.

Failure events use only operation, exception type, and safe message; never include request headers or payloads. Example:

```python
emit({"type": "error", "operation": "voicelab_agent_chat", "error": str(exc)})
raise
```

`uxagent_memory.json` contains `{"sessionId": session_id, "memories": [memory.model_dump() for memory in self.policy.memories]}`. Upload all JSON using the existing temporary-file plus `environment.upload_file` pattern.

- [ ] **Step 4: Add malformed-response and cleanup tests**

Add a second test where `client.agent_chat` raises `VoiceLabContractError`. Assert:

```python
assert policy.closed is True
assert client.closed is True
assert events[-1]["type"] == "error"
assert "APP_PASSWORD" not in json.dumps(events)
```

- [ ] **Step 5: Run runner and existing normalization tests**

```bash
uv run pytest \
  packages/playground/src/playground/tests/test_uxagent_runner.py \
  packages/playground/src/playground/tests/test_structured_exposure.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Export the stable runner API and commit**

Update `playground.uxagent.__init__` to export `UXAgentTrialRunner`, then:

```bash
git add packages/playground/src/playground/uxagent packages/playground/src/playground/tests/test_uxagent_runner.py
git commit -m "feat: run UXAgent trials through VoiceLab"
```

---

### Task 6: Harbor persona agent registration

**Files:**
- Create: `environment/agents/matraix/agents/persona/uxagent.py`
- Modify: `environment/runtime/harbor/models/agent/name.py:35-46`
- Modify: `environment/runtime/harbor/agents/factory.py:59-86`
- Modify: `environment/agents/matraix/agents/persona/__init__.py:7-63`
- Modify: `src/matraix/persona_agent_context.py:1-7`
- Modify: `tests/environment/test_persona_agents.py:44-70`

- [ ] **Step 1: Use LSP references before changing exported registries**

Run LSP references for `AgentName.PERSONA_USER_SIM`, `AgentFactory._AGENT_MAP`, and the persona package exports. If the active Ruff server still reports `textDocument/references` unsupported, record that limitation and use the existing factory/export tests plus `grep` results as the callsite inventory; do not rename any symbol.

- [ ] **Step 2: Add failing registration tests**

Extend `test_harbor_factory_registers_matraix_persona_agents` with:

```python
"matraix.agents.persona.uxagent:PersonaUXAgent",
```

Add:

```python
def test_persona_uxagent_is_registered_and_lazy_exported(tmp_path) -> None:
    from harbor.agents.factory import AgentFactory
    from harbor.models.agent.name import AgentName
    from matraix.agents.persona import PersonaUXAgent

    assert AgentName.PERSONA_UXAGENT.value == "persona-uxagent"
    assert AgentFactory.get_agent_class(AgentName.PERSONA_UXAGENT) is PersonaUXAgent
```

- [ ] **Step 3: Run and confirm failure**

```bash
uv run pytest tests/environment/test_persona_agents.py -q
```

Expected: missing enum member/import path/export failures.

- [ ] **Step 4: Implement the thin adapter and registrations**

`PersonaUXAgent` must not duplicate runner logic:

```python
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.agent.name import AgentName
from matraix.agents.persona.mixin import PersonaMixin
from playground.chatbot_task_config import load_chatbot_task_config_for_task_path
from playground.harbor.chat_eval import harbor_chat_task_path_from_env
from playground.harbor.playground import _repo_root
from playground.model_client import build_json_client
from playground.task_content_bundle import load_task_content_bundle_for_task_path
from playground.uxagent.client import VoiceLabPersonaClient
from playground.uxagent.policy import ConversationalUXPolicy
from playground.uxagent.runner import UXAgentTrialRunner


class PersonaUXAgent(PersonaMixin, BaseAgent):
    SUPPORTS_WINDOWS = True

    @staticmethod
    def name() -> str:
        return AgentName.PERSONA_UXAGENT.value

    def version(self) -> str:
        return "1.0.0"

    def __init__(self, logs_dir: Path, persona_path: str | None = None,
                 persona_template_path: str | None = None, **kwargs) -> None:
        self._init_persona(persona_path, self.name(), persona_template_path=persona_template_path)
        super().__init__(logs_dir=logs_dir, **kwargs)

    async def setup(self, environment: BaseEnvironment) -> None:
        return None

    async def run(self, instruction: str, environment: BaseEnvironment,
                  context: AgentContext) -> None:
        del context
        await self._prepare_persona_trial(environment)
        repo_root = _repo_root()
        task_path = harbor_chat_task_path_from_env()
        if not task_path:
            raise RuntimeError("MATRIX_CHATBOT_TASK_PATH is required for persona-uxagent")
        runtime = load_chatbot_task_config_for_task_path(task_path, repo_root=repo_root)
        if runtime is None:
            raise RuntimeError(f"Missing chatbot config for {task_path}")
        bundle = load_task_content_bundle_for_task_path(task_path, repo_root=repo_root)
        task_intent = bundle.instruction_markdown or instruction
        policy = ConversationalUXPolicy(
            persona_system=self._render_persona_system(),
            task_intent=task_intent,
            json_client=build_json_client(self.model_name or "openai/gpt-4o-mini"),
        )
        runner = UXAgentTrialRunner(client=VoiceLabPersonaClient(), policy=policy)
        await runner.run(
            environment=environment,
            persona=self._persona,
            runtime=runtime,
            task_intent=task_intent,
            on_event=TrialEventWriter.for_trial_dir(self.logs_dir.parent).append,
        )
```

Include the missing `TrialEventWriter` import. Add `PERSONA_UXAGENT = "persona-uxagent"`, the factory map entry, and the `PersonaUXAgent` lazy export. Update only the module docstring in `persona_agent_context.py` to state that Vita chat tasks select `persona-uxagent`; global chat remains `persona-user-sim`.

- [ ] **Step 5: Run registration tests**

```bash
uv run pytest tests/environment/test_persona_agents.py tests/unit/agents/test_factory.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add environment/runtime/harbor/models/agent/name.py environment/runtime/harbor/agents/factory.py environment/agents/matraix/agents/persona src/matraix/persona_agent_context.py tests/environment/test_persona_agents.py
git commit -m "feat: register persona UXAgent"
```

---

### Task 7: Migrate Vita auto-selection without changing other chat tasks

**Files:**
- Modify: `application/playground/backend/service/harbor_job_service.py:135-167`
- Modify: `application/playground/backend/tests/test_harbor_job_service.py:337-363`
- Modify: `scripts/generate_vita_agent_tasks.py:843-869`
- Modify: `application/tasks/chat_vita-*/task.toml`
- Modify: `tests/vita/test_task_catalog.py:27-58`

- [ ] **Step 1: Write failing selection and catalog tests**

Add a Vita-specific test while retaining the existing non-Vita assertion:

```python
def test_resolve_agent_name_for_vita_chat_task(tmp_path):
    repo = tmp_path
    task_dir = repo / "application/tasks/chat_vita-climate-temperature"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        '[metadata]\ntype = "agent"\ntags = ["vita", "uxagent"]\n',
        encoding="utf-8",
    )
    from backend.service.harbor_job_service import resolve_agent_name

    assert resolve_agent_name(
        "application/tasks/chat_vita-climate-temperature",
        repo_root=repo,
        mode="auto",
        trial_profile="user_sim_chat",
    ) == "persona-uxagent"
    assert resolve_agent_name(
        "application/tasks/chat_vita-climate-temperature",
        repo_root=repo,
        explicit="persona-user-sim",
    ) == "persona-user-sim"
```

Extend `test_vita_catalog_contains_distinct_logic_cases`:

```python
assert "uxagent" in metadata["tags"]
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest \
  application/playground/backend/tests/test_harbor_job_service.py::test_resolve_agent_name_for_vita_chat_task \
  tests/vita/test_task_catalog.py::test_vita_catalog_contains_distinct_logic_cases \
  -q
```

Expected: Vita resolves to `persona-user-sim`, and catalog tags lack `uxagent`.

- [ ] **Step 3: Change selection precedence**

In `resolve_agent_name`, normalize the task path immediately after the explicit-agent branch, then place this condition before `profile == "user_sim_chat"`:

```python
normalized = task_path.replace("\\", "/").lower().rstrip("/")
if profile == "json_survey":
    return "persona-json-survey"
if normalized.startswith("application/tasks/chat_vita-") and profile == "user_sim_chat":
    return "persona-uxagent"
if profile == "user_sim_chat":
    return "persona-user-sim"
```

Remove the later duplicate `normalized = task_path.replace("\\", "/").lower()` assignment. Explicit agent selection and force-Docker behavior remain unchanged.

- [ ] **Step 4: Update the generator and regenerate Vita tasks**

In `_task_toml`, add `"uxagent"` to the generated metadata tag list. Run:

```bash
uv run scripts/generate_vita_agent_tasks.py
```

Expected: `Generated 10 Vita agent logic-case tasks.` Only generated Vita task files change; inspect the command output/diff list before committing and exclude unrelated user changes.

- [ ] **Step 5: Run selection and catalog tests**

```bash
uv run pytest \
  application/playground/backend/tests/test_harbor_job_service.py \
  tests/vita/test_task_catalog.py \
  -q
```

Expected: all selected tests pass, including non-Vita `chat_recai → persona-user-sim`.

- [ ] **Step 6: Commit only migration files**

```bash
git add application/playground/backend/service/harbor_job_service.py application/playground/backend/tests/test_harbor_job_service.py scripts/generate_vita_agent_tasks.py tests/vita/test_task_catalog.py application/tasks/chat_vita-*/task.toml
git commit -m "feat: route Vita trials through persona UXAgent"
```

---

### Task 8: Documentation, focused verification, and live smoke

**Files:**
- Modify: `docs/environment/README.md:107-131`
- Modify: `docs/environment/agents.md` agent table and chat examples
- Modify: `packages/playground/src/playground/uxagent/__init__.py` only if final public exports are missing

- [ ] **Step 1: Document operator-owned configuration**

Add these variables to the environment table:

```text
VOICELAB_API_URL  VoiceLab base URL used by persona-uxagent; local default http://localhost:3001.
APP_PASSWORD      Optional VoiceLab x-app-password value. Configure on the local/remote worker; never place it in task files or Playground payloads.
```

Document that `persona-uxagent` is host-native, only auto-selected for `chat_vita-*`, uses the persona model credential already required by `build_json_client`, and does not use Playwright or the legacy `/v1/messages` path.

- [ ] **Step 2: Run focused automated verification**

```bash
uv run pytest \
  packages/playground/src/playground/tests/test_uxagent_mapping.py \
  packages/playground/src/playground/tests/test_uxagent_client.py \
  packages/playground/src/playground/tests/test_uxagent_policy.py \
  packages/playground/src/playground/tests/test_uxagent_runner.py \
  tests/environment/test_persona_agents.py \
  tests/unit/agents/test_factory.py \
  application/playground/backend/tests/test_harbor_job_service.py \
  tests/vita/test_task_catalog.py \
  -q
```

Expected: all selected tests pass with no leaked-task warnings.

- [ ] **Step 3: Run static diagnostics on changed Python files**

Use LSP workspace diagnostics for the changed Python paths. Then run the project formatter/linter once:

```bash
uv run ruff check packages/playground/src/playground/uxagent environment/agents/matraix/agents/persona/uxagent.py
```

Expected: no diagnostics or Ruff errors.

- [ ] **Step 4: Start/configure VoiceLab and run the real Vita path**

With a reachable VoiceLab instance and a valid persona-model credential:

```bash
export VOICELAB_API_URL="http://localhost:3001"
: "${APP_PASSWORD:?Set APP_PASSWORD in the operator environment}"
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY in the operator environment}"
uv run harbor run \
  -p application/tasks/chat_vita-climate-temperature \
  -a persona-uxagent \
  -m anthropic/claude-haiku-4-5 \
  --ak persona_path=persona/datasets/vita-vn-driver-v1/persona_vita-vn-001.yaml
```

Expected behavioral evidence in the produced trial artifacts:

- exactly one persona-session creation for the trial session ID;
- at least one `/api/agent/chat` call with the same `personaSessionId`;
- `transcript.json` includes `decision`, `vehicle_state`, and `tool_result` structured exposure;
- `application_result.json` uses the same session ID;
- `uxagent_memory.json` contains observation/plan/action memories and no secrets;
- the existing task verifier completes.

If VoiceLab is unavailable, do not claim the live smoke passed. Report the exact missing external prerequisite after all automated checks complete.

- [ ] **Step 5: Rebuild Graphify after all edits**

```bash
graphify update . --force
```

Expected: `graphify-out/graph.json` and `GRAPH_REPORT.md` update successfully. Do not commit graph output unless repository policy already tracks and expects it for this branch.

- [ ] **Step 6: Commit docs and any final export correction**

```bash
git add docs/environment/README.md docs/environment/agents.md packages/playground/src/playground/uxagent/__init__.py
git commit -m "docs: document VoiceLab persona UXAgent"
```

---

## Completion Checklist

- `persona-uxagent` resolves through `AgentName`, `AgentFactory`, and the lazy persona package export.
- Only Vita auto-mode routes to `persona-uxagent`; non-Vita chat behavior and explicit overrides remain unchanged.
- One VoiceLab persona session is created per trial, and every turn carries that trial session ID.
- The only policy action is a validated Vietnamese `send_message`.
- VoiceLab remains the sole owner of vehicle tool execution and safety enforcement.
- Decision, vehicle state, action, tool result, capabilities, and runtime context reach existing verifier artifacts unchanged.
- No source code or prompt text is copied from the unlicensed UXAgent repository.
- `APP_PASSWORD` is never serialized into prompts, events, trajectories, or artifacts.
- Contract failures are visible and do not fall back to the old simulator or endpoint.
- Focused tests pass; live smoke evidence is recorded only if VoiceLab was actually reachable.
