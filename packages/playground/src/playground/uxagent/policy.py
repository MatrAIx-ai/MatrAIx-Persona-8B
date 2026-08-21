"""Clean-room, dual-loop conversational UX policy."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any, Literal, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from playground.uxagent.models import SendMessageAction, UXMemory, UXObservation
from playground.uxagent.prompts import ACT_SYSTEM, PERCEIVE_SYSTEM, PLAN_SYSTEM, SLOW_SYSTEM


class JsonClient(Protocol):
    """Synchronous client for a JSON-only model completion."""

    def complete_json(self, system: str, user: str) -> Mapping[str, Any]: ...


class UXAgentPolicyError(ValueError):
    """Safe, provider-independent error raised for invalid policy responses."""


class _StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _PerceptionResponse(_StrictResponse):
    observations: list[str] = Field(min_length=1)
    importance: float = Field(ge=0.0, le=1.0)

    @field_validator("observations")
    @classmethod
    def observations_are_nonblank(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("observations must not contain blank items")
        return values


class _PlanResponse(_StrictResponse):
    plan: str
    importance: float = Field(..., ge=0.0, le=1.0)

    @field_validator("plan")
    @classmethod
    def plan_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("plan must not be blank")
        return value


class _ActionResponse(_StrictResponse):
    action: Literal["send_message"]
    message: str
    end_reason: str | None

    @field_validator("message")
    @classmethod
    def message_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value



class _SlowResponse(_StrictResponse):
    reflections: list[str]
    wonders: list[str]

    @field_validator("reflections", "wonders")
    @classmethod
    def items_are_nonblank(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("slow-loop items must not be blank")
        return values


class ConversationalUXPolicy:
    """A bounded fast perceive-plan-act loop plus a queue-backed slow loop."""

    PERCEIVE_SYSTEM = PERCEIVE_SYSTEM
    PLAN_SYSTEM = PLAN_SYSTEM
    ACT_SYSTEM = ACT_SYSTEM
    SLOW_SYSTEM = SLOW_SYSTEM
    _MEMORY_LIMIT = 100
    _RECENT_MEMORY_LIMIT = 20

    def __init__(
        self,
        persona_system: str,
        task_intent: str,
        json_client: JsonClient,
    ) -> None:
        self.persona_system = persona_system
        self.task_intent = task_intent
        self.json_client = json_client
        self._memories: list[UXMemory] = []
        self._slow_queue: asyncio.Queue[UXObservation] = asyncio.Queue()
        self._slow_task: asyncio.Task[None] | None = None
        self._slow_started = False
        self._slow_failed = False
        self._slow_lock = asyncio.Lock()
        self._slow_error: UXAgentPolicyError | None = None
    @property
    def memories(self) -> tuple[UXMemory, ...]:
        """Read-only memories, ordered oldest to newest."""
        return tuple(self._memories)

    @property
    def slow_task(self) -> asyncio.Task[None] | None:
        return self._slow_task

    async def next_action(self, observation: UXObservation) -> SendMessageAction:
        """Run exactly one perceive-plan-act cycle and return one message action."""
        perceived = await self._complete(self.PERCEIVE_SYSTEM, observation, phase="perception")
        perception = self._validate(_PerceptionResponse, perceived, "perception")
        for content in perception.observations:
            self._append_memory(
                UXMemory(
                    kind="observation",
                    content=content,
                    importance=perception.importance,
                    turn_index=observation.turn_index,
                )
            )

        planned = await self._complete(self.PLAN_SYSTEM, observation, phase="plan")
        plan = self._validate(_PlanResponse, planned, "plan")
        self._append_memory(
            UXMemory(
                kind="plan",
                content=plan.plan,
                importance=plan.importance,
                turn_index=observation.turn_index,
            )
        )

        acted = await self._complete(self.ACT_SYSTEM, observation, phase="action")
        action = self._validate_action(acted)
        self._append_memory(
            UXMemory(
                kind="action",
                content=action.message,
                importance=0.5,
                turn_index=observation.turn_index,
            )
        )
        return action
    def start_slow_loop(self) -> None:
        """Start the slow worker once; repeated starts are idempotent."""
        if self._slow_task is not None and not self._slow_task.done():
            if not self._slow_failed:
                self._slow_started = True
            return
        self._slow_failed = False
        self._slow_started = True
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        self._slow_error = None
        self._slow_task = asyncio.create_task(self._slow_worker())

    async def enqueue_slow_observation(self, observation: UXObservation) -> None:
        async with self._slow_lock:
            if self._slow_failed:
                raise UXAgentPolicyError("slow loop unavailable")
            if not self._slow_started or self._slow_task is None or self._slow_task.done():
                self.start_slow_loop()
            if self._slow_task is None:
                self.start_slow_loop()
            if self._slow_task is None:
                raise UXAgentPolicyError("slow loop unavailable")
            await self._slow_queue.put(observation)

    async def wait_until_slow_idle(self) -> None:
        await self._slow_queue.join()
        if self._slow_error is not None:
            raise self._slow_error

    async def close(self) -> None:
        """Drain queued slow work, cancel the idle worker, and release its task."""
        task = self._slow_task
        if task is None:
            self._drain_slow_queue()
            self._slow_started = False
            self._slow_failed = False
            return
        await self._slow_queue.join()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        self._slow_task = None
        self._slow_started = False
        self._slow_failed = False

    async def _slow_worker(self) -> None:
        while True:
            observation = await self._slow_queue.get()
            should_stop = False
            try:
                await self._process_slow_observation(observation)
            except UXAgentPolicyError as error:
                self._slow_error = error
                should_stop = True
            except Exception:
                self._slow_error = UXAgentPolicyError("slow-loop model call failed")
                should_stop = True
            finally:
                if should_stop:
                    self._slow_queue.task_done()
                    async with self._slow_lock:
                        self._slow_failed = True
                        self._slow_started = False
                        self._drain_slow_queue()
                else:
                    self._slow_queue.task_done()
            if should_stop:
                return

    async def _process_slow_observation(self, observation: UXObservation) -> None:
        raw = await self._complete(self.SLOW_SYSTEM, observation, phase="slow")
        result = self._validate(_SlowResponse, raw, "slow")
        for content in result.reflections:
            self._append_memory(
                UXMemory(
                    kind="reflection",
                    content=content,
                    importance=0.5,
                    turn_index=observation.turn_index,
                )
            )
        for content in result.wonders:
            self._append_memory(
                UXMemory(
                    kind="wonder",
                    content=content,
                    importance=0.5,
                    turn_index=observation.turn_index,
                )
            )

    async def _complete(
        self,
        system: str,
        observation: UXObservation,
        *,
        phase: str,
    ) -> Mapping[str, Any]:
        payload = {
            "phase": phase,
            "persona": self.persona_system,
            "task_intent": self.task_intent,
            "recent_memories": [memory.model_dump(mode="json") for memory in self._memories[-self._RECENT_MEMORY_LIMIT :]],
            "observation": observation.model_dump(mode="json"),
        }
        user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        raw = await asyncio.to_thread(self.json_client.complete_json, system, user)
        if not isinstance(raw, Mapping):
            raise UXAgentPolicyError(f"invalid {phase} response")
        return raw

    @staticmethod
    def _validate(model: type[BaseModel], raw: Mapping[str, Any], phase: str) -> BaseModel:
        try:
            return model.model_validate(raw, strict=True)
        except (ValidationError, TypeError, ValueError):
            raise UXAgentPolicyError(f"invalid {phase} response") from None

    @staticmethod
    def _validate_action(raw: Mapping[str, Any]) -> SendMessageAction:
        try:
            envelope = _ActionResponse.model_validate(raw, strict=True)
            return SendMessageAction.model_validate(envelope.model_dump(), strict=True)
        except (ValidationError, TypeError, ValueError):
            raise UXAgentPolicyError("invalid action response") from None

    def _append_memory(self, memory: UXMemory) -> None:
        self._memories.append(memory)
        del self._memories[:-self._MEMORY_LIMIT]

    def _drain_slow_queue(self) -> None:
        while True:
            with suppress(asyncio.QueueEmpty):
                self._slow_queue.get_nowait()
                self._slow_queue.task_done()
                continue
            return
