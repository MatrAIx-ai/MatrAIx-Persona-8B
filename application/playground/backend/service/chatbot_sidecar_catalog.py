from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class SidecarRuntime(StrEnum):
    DOCKER_COMPOSE = "docker-compose"
    APPLE_CONTAINER = "apple-container"


@dataclass(frozen=True, slots=True)
class SidecarSpec:
    application_id: str
    compose_dir: str | None
    service_name: str | None
    build_context: str | None
    host_port: int
    primary_env: str
    legacy_env: str | None = None
    probe: Literal["http", "tcp"] = "http"
    runtime: SidecarRuntime = SidecarRuntime.DOCKER_COMPOSE
    containerfile: str | None = None
    image_name: str | None = None


SIDECAR_SPECS: dict[str, SidecarSpec] = {
    "recai": SidecarSpec(
        application_id="recai",
        compose_dir="environment/task-environments/application/chatbot-api-sidecar_recai",
        service_name="rec-agent-api",
        build_context="recommender-api",
        host_port=8000,
        primary_env="CHATBOT_API_URL",
    ),
    "finance_openbb": SidecarSpec(
        application_id="finance_openbb",
        compose_dir="environment/task-environments/application/chatbot-api-sidecar_openbb",
        service_name="finance-chatbot",
        build_context="finance-chatbot",
        host_port=8901,
        primary_env="CHATBOT_UPSTREAM_FINANCE",
        legacy_env="FINANCE_CHATBOT_URL",
    ),
    "medical_assistant": SidecarSpec(
        application_id="medical_assistant",
        compose_dir="environment/task-environments/application/chatbot-api-sidecar_multi-agent-medical-assistant",
        service_name="multi-agent-medical-assistant-api",
        build_context="multi-agent-medical-assistant-api",
        host_port=8902,
        primary_env="CHATBOT_UPSTREAM_MEDICAL",
        legacy_env="MEDICAL_CHATBOT_URL",
    ),
    "acme_support_api": SidecarSpec(
        application_id="acme_support_api",
        compose_dir="environment/task-environments/application/chatbot-api-sidecar_acme-support-api",
        service_name="support-api",
        build_context="support-api",
        host_port=8904,
        primary_env="CHATBOT_API_URL",
    ),
    "prescreening_assistant": SidecarSpec(
        application_id="prescreening_assistant",
        compose_dir="environment/task-environments/application/chatbot-api-sidecar_prescreening",
        service_name="prescreening-chatbot",
        build_context="prescreening-chatbot",
        host_port=8906,
        primary_env="CHATBOT_UPSTREAM_PRESCREENING",
        legacy_env="PRESCREENING_CHATBOT_URL",
    ),
    "acme_support_mcp": SidecarSpec(
        application_id="acme_support_mcp",
        compose_dir="environment/task-environments/application/chatbot-mcp-sidecar_acme-support",
        service_name="support-bot",
        build_context="support-bot",
        host_port=8903,
        primary_env="CHATBOT_MCP_URL",
        probe="tcp",
    ),
    "meal_planning_nutrition": SidecarSpec(
        application_id="meal_planning_nutrition",
        compose_dir="environment/task-environments/application/chatbot-api-sidecar_meal-plan-api",
        service_name="meal-plan-api",
        build_context="meal-plan-api",
        host_port=8905,
        primary_env="CHATBOT_API_URL",
    ),
    "deeptutor": SidecarSpec(
        application_id="deeptutor",
        compose_dir="environment/task-environments/application/chatbot-api-sidecar_deeptutor",
        service_name="tutor-adapter",
        build_context="tutor-adapter",
        host_port=8906,
        primary_env="CHATBOT_UPSTREAM_DEEPTUTOR",
    ),
    "vita_climate": SidecarSpec(
        application_id="vita_climate",
        compose_dir="environment/task-environments/application/vita-climate-sidecar",
        service_name="vita-climate",
        build_context=".",
        host_port=8907,
        primary_env="VITA_CHATBOT_API_URL",
        runtime=SidecarRuntime.APPLE_CONTAINER,
        containerfile="environment/task-environments/application/vita-climate-sidecar/Containerfile",
        image_name="vita-climate-sidecar:dev",
    ),
}
