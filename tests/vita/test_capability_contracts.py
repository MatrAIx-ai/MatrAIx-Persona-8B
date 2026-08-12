from __future__ import annotations

from matraix.vita.capabilities import load_capability_contracts


def test_registry_loads_all_vita_ux_capability_contracts() -> None:
    contracts = load_capability_contracts()

    assert len(contracts) == 14
    assert len({contract.id for contract in contracts}) == 14
    assert {contract.id for contract in contracts} >= {
        "one_shot_interaction",
        "clarification_disambiguation",
        "action_orchestration",
        "execution_status",
        "guardrail_refusal",
    }
    for contract in contracts:
        assert contract.owner == "vita_global"
        assert contract.expected_evidence
        assert contract.metrics
