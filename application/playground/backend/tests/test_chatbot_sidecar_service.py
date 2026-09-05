"""Tests for chatbot sidecar health + start helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.service import chatbot_sidecar_service as svc


def test_resolve_health_url_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHATBOT_API_URL", raising=False)
    monkeypatch.delenv("CHATBOT_MCP_URL", raising=False)
    assert svc.resolve_health_url("finance_openbb") == "http://127.0.0.1:8901"
    assert svc.resolve_health_url("acme_support_api") == "http://127.0.0.1:8904"
    assert svc.resolve_health_url("acme_support_mcp") == "http://127.0.0.1:8903"
    assert svc.resolve_health_url("meal_planning_nutrition") == "http://127.0.0.1:8905"


def test_ensure_sidecar_url_env_seeds_meal_planning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CHATBOT_API_URL", raising=False)
    url = svc.ensure_sidecar_url_env("meal_planning_nutrition")
    assert url == "http://127.0.0.1:8905"
    assert os.environ["CHATBOT_API_URL"] == url


def test_ensure_sidecar_url_env_keeps_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHATBOT_API_URL", "https://chat.prod.example")
    url = svc.ensure_sidecar_url_env("meal_planning_nutrition")
    assert url == "https://chat.prod.example"
    assert os.environ["CHATBOT_API_URL"] == url


def test_sidecar_host_ports_are_unique() -> None:
    ports = [spec.host_port for spec in svc._SIDECAR_SPECS.values()]
    assert len(ports) == len(set(ports)), ports


def test_sidecar_status_unknown_application() -> None:
    with pytest.raises(ValueError, match="unknown chatbot application"):
        svc.sidecar_status("not_real")


def test_list_sidecar_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_sidecar_probe_ok", lambda _spec, _url, timeout=1.5: True)
    statuses = svc.list_sidecar_statuses()
    assert {item["applicationId"] for item in statuses} == {
        "finance_openbb",
        "acme_support_api",
        "acme_support_mcp",
        "meal_planning_nutrition",
    }
    assert all(item["ok"] for item in statuses)
    by_id = {item["applicationId"]: item for item in statuses}
    assert by_id["finance_openbb"]["canStart"] is True
    assert by_id["acme_support_api"]["canStart"] is True
    assert by_id["acme_support_mcp"]["canStart"] is True
    assert by_id["meal_planning_nutrition"]["canStart"] is True


def test_start_sidecar_runs_compose_for_sidecar_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    (compose_dir / "docker-compose.yaml").write_text(
        "services:\n  main:\n    depends_on: [meal-plan-api]\n  meal-plan-api:\n    build: .\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        svc,
        "_SIDECAR_SPECS",
        {
            "meal_planning_nutrition": svc.SidecarSpec(
                application_id="meal_planning_nutrition",
                compose_dir=str(compose_dir.relative_to(tmp_path)),
                service_name="meal-plan-api",
                build_context="meal-plan-api",
                host_port=8905,
                primary_env="CHATBOT_API_URL",
            )
        },
    )
    monkeypatch.setattr(svc, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(svc, "sidecar_reachable", lambda _url, timeout=1.5: True)

    captured: dict[str, list[str]] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = list(command)
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(svc.subprocess, "run", fake_run)
    result = svc.start_sidecar("meal_planning_nutrition", repo_root=tmp_path)
    assert result["ok"] is True
    assert captured["command"][-1] == "meal-plan-api"
    assert "main" not in captured["command"]


def test_start_sidecar_rejects_external_only_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        svc,
        "_SIDECAR_SPECS",
        {
            "external_only": svc.SidecarSpec(
                application_id="external_only",
                compose_dir=None,
                service_name=None,
                build_context=None,
                host_port=8999,
                primary_env="CHATBOT_UPSTREAM_EXTERNAL",
            )
        },
    )
    with pytest.raises(RuntimeError, match="does not provide a local startable sidecar"):
        svc.start_sidecar("external_only")


def test_sidecar_status_uses_tcp_probe_for_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "sidecar_port_reachable", lambda _host, _port, timeout=1.5: True)
    status = svc.sidecar_status("acme_support_mcp")
    assert status["ok"] is True
    assert "MCP server ready" in status["detail"]


def test_sidecar_reachable_probes_ready_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN001
            return False

        def getcode(self):
            return 200

    def fake_urlopen(request, timeout=0):  # noqa: ANN001
        seen["url"] = request.full_url
        return _Resp()

    monkeypatch.setattr(svc.urllib.request, "urlopen", fake_urlopen)
    assert svc.sidecar_reachable("http://127.0.0.1:8902") is True
    assert seen["url"] == "http://127.0.0.1:8902/ready"
