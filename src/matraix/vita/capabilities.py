from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class CapabilityContract(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str
    name: str
    owner: str = "vita_global"
    expected_evidence: tuple[str, ...] = Field(alias="expectedEvidence")
    metrics: tuple[str, ...]


class CapabilityRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    schema_version: str = Field(alias="schemaVersion")
    capabilities: tuple[CapabilityContract, ...]


@lru_cache(maxsize=1)
def load_capability_registry() -> CapabilityRegistry:
    path = Path(__file__).with_name("capability_contracts.yaml")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CapabilityRegistry.model_validate(payload)


def load_capability_contracts() -> tuple[CapabilityContract, ...]:
    return load_capability_registry().capabilities
