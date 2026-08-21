from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import pytest

from playground.uxagent.models import SendMessageAction, UXMemory, UXObservation
from playground.uxagent.policy import ConversationalUXPolicy, UXAgentPolicyError


class FakeJsonClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls.append((system, user))
        return self.responses.pop(0)



class BlockingFailingJsonClient:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.entered.set()
        if not self.release.wait(timeout=2):
            raise RuntimeError("test release timeout")
        raise RuntimeError("controlled slow failure")


class BlockingSlowJsonClient:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.entered.set()
        self.release.wait(timeout=2)
        return {"reflections": [], "wonders": []}


class BlockingActionJsonClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.entered = threading.Event()
        self.release = threading.Event()

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls.append((system, user))
        if len(self.calls) == 3:
            self.entered.set()
            self.release.wait(timeout=2)
            return {
                "action": "send_message",
                "message": "Bạn muốn đi đâu?",
                "end_reason": None,
            }
        if len(self.calls) == 1:
            return {"observations": ["Tín hiệu"], "importance": 0.5}
        return {"plan": "Hỏi điểm đến", "importance": 0.5}

def _observation(turn_index: int = 3) -> UXObservation:
    return UXObservation(
        task_intent="Tìm đường an toàn đến trường",
        turn_index=turn_index,
        assistant_reply="Bạn muốn đi tuyến nào?",
        decision="continue",
    )


def test_fast_loop_perceives_plans_and_acts_in_order() -> None:
    client = FakeJsonClient(
        [
            {"observations": ["Tài xế cần một câu hỏi rõ ràng"], "importance": 0.8},
            {"plan": "Hỏi điểm đến cụ thể", "importance": 0.7},
            {
                "action": "send_message",
                "message": "Bạn muốn đến khu vực nào trước?",
                "end_reason": None,
            },
        ]
    )
    policy = ConversationalUXPolicy("Điềm tĩnh và ngắn gọn", "Tìm đường an toàn đến trường", client)

    action = asyncio.run(policy.next_action(_observation()))

    assert action == SendMessageAction(
        action="send_message", message="Bạn muốn đến khu vực nào trước?"
    )
    assert len(client.calls) == 3
    assert [call[0] for call in client.calls] == [
        policy.PERCEIVE_SYSTEM,
        policy.PLAN_SYSTEM,
        policy.ACT_SYSTEM,
    ]
    assert [memory.kind for memory in policy.memories] == [
        "observation",
        "plan",
        "action",
    ]
    assert all(memory.turn_index == 3 for memory in policy.memories)
    assert all(0 <= memory.importance <= 1 for memory in policy.memories)
    for _, payload in client.calls:
        assert "Điềm tĩnh và ngắn gọn" in payload
        assert "Tìm đường an toàn đến trường" in payload
        assert "OPENAI_API_KEY" not in payload
        json.loads(payload)


def test_fast_loop_rejects_empty_perception() -> None:
    client = FakeJsonClient([{"observations": [], "importance": 0.5}])
    policy = ConversationalUXPolicy("Persona", "Task", client)

    with pytest.raises(UXAgentPolicyError):
        asyncio.run(policy.next_action(_observation()))


def test_fast_loop_requires_plan_importance() -> None:
    client = FakeJsonClient(
        [
            {"observations": ["Cần làm rõ"], "importance": 0.5},
            {"plan": "Hỏi lại"},
        ]
    )
    policy = ConversationalUXPolicy("Persona", "Task", client)

    with pytest.raises(UXAgentPolicyError):
        asyncio.run(policy.next_action(_observation()))


def test_fast_loop_requires_explicit_nullable_end_reason() -> None:
    client = FakeJsonClient(
        [
            {"observations": ["Cần làm rõ"], "importance": 0.5},
            {"plan": "Hỏi lại", "importance": 0.5},
            {"action": "send_message", "message": "Thiếu lý do kết thúc"},
        ]
    )
    policy = ConversationalUXPolicy("Persona", "Task", client)

    with pytest.raises(UXAgentPolicyError):
        asyncio.run(policy.next_action(_observation()))


def test_fast_loop_preserves_non_null_end_reason() -> None:
    client = FakeJsonClient(
        [
            {"observations": ["Cần làm rõ"], "importance": 0.5},
            {"plan": "Hỏi lại", "importance": 0.5},
            {
                "action": "send_message",
                "message": "Đã hoàn tất trao đổi",
                "end_reason": "driver_finished",
            },
        ]
    )
    policy = ConversationalUXPolicy("Persona", "Task", client)

    action = asyncio.run(policy.next_action(_observation()))

    assert action.end_reason == "driver_finished"


def test_fast_loop_rejects_invalid_action_without_reinterpretation() -> None:
    client = FakeJsonClient(
        [
            {"observations": ["Cần làm rõ"], "importance": 0.5},
            {"plan": "Hỏi lại", "importance": 0.5},
            {"action": "open_browser", "message": "ignored", "end_reason": None},
        ]
    )
    policy = ConversationalUXPolicy("Persona", "Task", client)

    with pytest.raises((UXAgentPolicyError, ValueError)) as error:
        asyncio.run(policy.next_action(_observation()))

    assert "ignored" not in str(error.value)


def test_fast_loop_rejects_blank_action_message() -> None:
    client = FakeJsonClient(
        [
            {"observations": ["Cần làm rõ"], "importance": 0.5},
            {"plan": "Hỏi lại", "importance": 0.5},
            {"action": "send_message", "message": "   ", "end_reason": None},
        ]
    )
    policy = ConversationalUXPolicy("Persona", "Task", client)

    with pytest.raises((UXAgentPolicyError, ValueError)):
        asyncio.run(policy.next_action(_observation()))

def test_fast_loop_cancellation_does_not_commit_partial_memories() -> None:
    client = BlockingActionJsonClient()
    policy = ConversationalUXPolicy("Persona", "Task", client)

    async def scenario() -> None:
        action_task = asyncio.create_task(policy.next_action(_observation()))
        entered = await asyncio.wait_for(asyncio.to_thread(client.entered.wait, 1), timeout=1)
        assert entered
        action_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await action_task
        assert policy.memories == ()
        client.release.set()

    asyncio.run(scenario())


def test_slow_loop_processes_observation_once_and_closes_cleanly() -> None:
    client = FakeJsonClient(
        [
            {
                "reflections": ["Câu hỏi mở giúp giảm nhầm lẫn"],
                "wonders": ["Tài xế có muốn nghe thêm lựa chọn không?"],
            }
        ]
    )
    policy = ConversationalUXPolicy("Thân thiện", "Đi đến bệnh viện", client)

    async def scenario() -> None:
        policy.start_slow_loop()
        policy.start_slow_loop()
        await policy.enqueue_slow_observation(_observation(8))
        await policy.wait_until_slow_idle()

    asyncio.run(scenario())

    assert len(client.calls) == 1
    assert [memory.kind for memory in policy.memories] == ["reflection", "wonder"]
    assert [memory.turn_index for memory in policy.memories] == [8, 8]

    asyncio.run(policy.close())
    assert policy.slow_task is None


def test_close_cancels_hung_slow_thread_without_waiting_for_model() -> None:
    client = BlockingSlowJsonClient()
    policy = ConversationalUXPolicy("Persona", "Task", client)

    async def scenario() -> None:
        policy.start_slow_loop()
        await policy.enqueue_slow_observation(_observation(12))
        entered = await asyncio.wait_for(asyncio.to_thread(client.entered.wait, 1), timeout=1)
        assert entered
        await asyncio.wait_for(policy.close(), timeout=1)
        client.release.set()

    asyncio.run(scenario())
    assert policy._slow_queue._unfinished_tasks == 0
    assert policy.slow_task is None


def test_close_before_start_is_safe() -> None:
    policy = ConversationalUXPolicy("Persona", "Task", FakeJsonClient([]))
    asyncio.run(policy.close())
    assert policy.slow_task is None


def test_slow_failure_is_raised_after_queue_becomes_idle() -> None:
    client = FakeJsonClient([{"reflections": "not a list", "wonders": []}])
    policy = ConversationalUXPolicy("Persona", "Task", client)

    async def scenario() -> None:
        policy.start_slow_loop()
        await policy.enqueue_slow_observation(_observation())
        with pytest.raises(UXAgentPolicyError, match="slow"):
            await policy.wait_until_slow_idle()
        await policy.close()

    asyncio.run(scenario())
    assert policy.slow_task is None


def test_slow_failure_rejects_racing_enqueue_and_close_does_not_hang() -> None:
    client = FakeJsonClient([{"reflections": "not a list", "wonders": []}])
    policy = ConversationalUXPolicy("Persona", "Task", client)

    async def scenario() -> None:
        policy.start_slow_loop()
        await policy.enqueue_slow_observation(_observation())
        with pytest.raises(UXAgentPolicyError, match="slow"):
            await policy.wait_until_slow_idle()
        with pytest.raises(UXAgentPolicyError, match="unavailable"):
            await policy.enqueue_slow_observation(_observation(9))
        with pytest.raises(UXAgentPolicyError, match="slow"):
            await policy.wait_until_slow_idle()
        await policy.close()

    asyncio.run(scenario())
    assert policy.slow_task is None




def test_slow_failure_coordinates_concurrent_enqueue_without_hanging() -> None:
    client = BlockingFailingJsonClient()
    policy = ConversationalUXPolicy("Persona", "Task", client)

    async def scenario() -> None:
        policy.start_slow_loop()
        first_enqueue = asyncio.create_task(
            policy.enqueue_slow_observation(_observation(10))
        )
        entered = await asyncio.wait_for(asyncio.to_thread(client.entered.wait, 1), timeout=1)
        assert entered

        second_enqueue = asyncio.create_task(
            policy.enqueue_slow_observation(_observation(11))
        )
        await asyncio.wait_for(second_enqueue, timeout=1)
        client.release.set()

        await asyncio.wait_for(first_enqueue, timeout=1)

        with pytest.raises(UXAgentPolicyError, match="slow"):
            await asyncio.wait_for(policy.wait_until_slow_idle(), timeout=1)
        await asyncio.wait_for(policy.close(), timeout=1)

    asyncio.run(scenario())
    assert policy._slow_queue._unfinished_tasks == 0


def test_memory_retains_exactly_newest_100() -> None:
    policy = ConversationalUXPolicy("Persona", "Task", FakeJsonClient([]))
    for index in range(105):
        policy._append_memory(
            UXMemory(
                kind="wonder",
                content=f"wonder-{index}",
                importance=0.5,
                turn_index=index,
            )
        )

    assert len(policy.memories) == 100
    assert policy.memories[0].content == "wonder-5"
    assert policy.memories[-1].content == "wonder-104"
