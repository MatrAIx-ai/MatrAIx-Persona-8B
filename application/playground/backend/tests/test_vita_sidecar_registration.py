from __future__ import annotations

import pytest

from backend.service import chatbot_sidecar_service as svc


def test_vita_sidecar_has_apple_container_start_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.delenv("VITA_CHATBOT_API_URL", raising=False)

    # When
    health_url = svc.resolve_health_url("vita_climate")
    can_start = svc.sidecar_can_start("vita_climate")

    # Then
    assert health_url == "http://127.0.0.1:8907"
    assert can_start is True
