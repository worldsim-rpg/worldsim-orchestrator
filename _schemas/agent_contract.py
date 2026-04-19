"""
Контракт агента — единственная форма, которой orchestrator знает агента.

Каждый агент-пакет экспортирует либо `MANIFEST: AgentManifest`, либо
`MANIFESTS: list[AgentManifest]` (если агент обслуживает несколько фаз).

Каноничный реестр живёт в `worldsim-workspace/agents.toml`. Orchestrator
читает его и через `registry.py` вызывает нужную фазу — агенты в loop.py
больше не упоминаются по имени.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AgentPhase(str, Enum):
    """
    Фаза хода, на которой активен агент.

    Фазы выполняются в порядке объявления здесь. Одну фазу может
    обслуживать один агент (например, `world_update` — только
    `world-builder`).
    """

    WORLD_INIT = "world_init"
    LOCATION_DETAIL = "location_detail"
    NPC_RESPOND = "npc_respond"
    WORLD_UPDATE = "world_update"
    PROGRESSION_UPDATE = "progression_update"
    CANON_VALIDATE = "canon_validate"
    SCENE_RENDER = "scene_render"


ModelTier = Literal["default", "heavy"]


class AgentManifest(BaseModel):
    """
    Декларативное описание одной операции агента.

    Если агент обслуживает несколько фаз (как `world-builder` с init /
    location_detail / turn_update), заводится несколько манифестов с
    одним и тем же `package`, но разными `entrypoint` и `phase`.
    """

    name: str = Field(..., description="Уникальное имя операции, напр. 'world-builder.turn'.")
    package: str = Field(..., description="Python-пакет агента, напр. 'worldsim_world_builder'.")
    entrypoint: str = Field(..., description="Имя callable в пакете.")
    phase: AgentPhase
    version: str = Field(default="0.1.0", description="SemVer операции.")
    optional: bool = Field(
        default=False,
        description="Если True — отсутствие пакета не валит orchestrator, фаза пропускается.",
    )
    model_tier: ModelTier = Field(
        default="default",
        description="Какую модель использовать: settings.model_default или model_heavy.",
    )
    description: str = ""


class AgentRegistryFile(BaseModel):
    """Форма agents.toml в workspace."""

    schema_version: str = "0.1.0"
    agents: list[AgentManifest]


__all__ = ["AgentPhase", "AgentManifest", "AgentRegistryFile", "ModelTier"]
