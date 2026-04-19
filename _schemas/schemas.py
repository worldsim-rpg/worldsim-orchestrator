"""
Канонические модели мира.

Всё, что живёт дольше одного хода, описано здесь. Pydantic следит за типами
и даёт `.model_dump()` / `.model_validate()` для сохранения и загрузки.

Разделение, которое важно помнить:
  - ontological   — что ЕСТЬ в мире (Character, Location, Faction, Secret)
  - epistemic     — кто что ЗНАЕТ (Character.knowledge, PlayerProgression.known_facts)
  - narrative     — что СЕЙЧАС важно (Arc.urgency, PlotState.dramatic_pressure)
  - player-facing — что ПОКАЗЫВАЕМ игроку (фильтруется scene-master на лету)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- базовые ---------------------------------------------------------------


class Condition(str, Enum):
    OK = "ok"
    TIRED = "tired"
    WOUNDED = "wounded"
    EXHAUSTED = "exhausted"


class ArcStage(str, Enum):
    HOOK = "hook"
    DEVELOPMENT = "development"
    COMPLICATION = "complication"
    REVERSAL = "reversal"
    CRISIS = "crisis"
    RESOLUTION = "resolution"
    AFTERMATH = "aftermath"


class Goal(BaseModel):
    text: str
    priority: float = Field(default=0.5, ge=0.0, le=1.0)


# --- сущности мира --------------------------------------------------------


class Location(BaseModel):
    id: str
    name: str
    short_description: str
    full_description: str | None = None  # догенерируется при первом посещении
    tags: list[str] = Field(default_factory=list)
    connected_to: list[str] = Field(default_factory=list)
    parent_region_id: str | None = None
    active_elements: list[str] = Field(default_factory=list)
    discovered: bool = False  # игрок о ней слышал
    visited: bool = False  # игрок там был


class Character(BaseModel):
    """Общая модель и для NPC, и для игрока (игрок — is_player=True)."""

    id: str
    name: str
    is_player: bool = False
    role: str | None = None
    faction_id: str | None = None
    public_traits: list[str] = Field(default_factory=list)
    hidden_traits: list[str] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)
    knowledge: list[str] = Field(default_factory=list)
    attitude_to_player: float = Field(default=0.0, ge=-1.0, le=1.0)
    location_id: str
    condition: Condition = Condition.OK
    alive: bool = True


class Faction(BaseModel):
    id: str
    name: str
    public_role: str
    hidden_agenda: str | None = None
    resources: list[str] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)
    relations: dict[str, float] = Field(default_factory=dict)
    status: str = "stable"


class Secret(BaseModel):
    id: str
    truth: str
    known_by: list[str] = Field(default_factory=list)
    discoverability: float = Field(default=0.3, ge=0.0, le=1.0)
    status: Literal["hidden", "hinted", "revealed"] = "hidden"


class Arc(BaseModel):
    id: str
    title: str
    type: str = "mystery"
    stage: ArcStage = ArcStage.HOOK
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    stakes: str = "local"
    urgency: float = Field(default=0.5, ge=0.0, le=1.0)
    clarity_to_player: float = Field(default=0.0, ge=0.0, le=1.0)
    involved_entities: list[str] = Field(default_factory=list)
    possible_escalations: list[str] = Field(default_factory=list)
    possible_revelations: list[str] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    tick: int
    type: str
    summary: str


# --- прогрессия игрока ----------------------------------------------------


class Attributes(BaseModel):
    perception: int = 1
    empathy: int = 1
    lore: int = 1
    athletics: int = 1
    subterfuge: int = 1


class PlayerProgression(BaseModel):
    character_id: str = "pc"
    attributes: Attributes = Field(default_factory=Attributes)
    # Счётчики-накопители: {"talked_to_npcs": 12, "explored_locations": 5}.
    # Из них вырастают повышения атрибутов.
    skill_counters: dict[str, int] = Field(default_factory=dict)
    reputation: dict[str, float] = Field(default_factory=dict)  # faction_id -> [-1..1]
    known_facts: list[str] = Field(default_factory=list)
    inventory: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    condition: Condition = Condition.OK


# --- мета мира и настройки ------------------------------------------------


class WorldInspiration(BaseModel):
    """Что игрок говорит при создании мира. Вход для world-builder."""

    genre: str
    tone: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    desired_player_activity: str | None = None
    magic_level: Literal["none", "low", "medium", "high"] = "low"
    scale: Literal["village", "town", "city", "region"] = "town"
    harshness: Literal["cozy", "neutral", "grim"] = "neutral"
    free_notes: str | None = None


class WorldMeta(BaseModel):
    id: str
    title: str
    genre: str
    tone: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    premise: str
    tick: int = 0
    player_character_id: str = "pc"


class PlotState(BaseModel):
    main_tensions: list[str] = Field(default_factory=list)
    active_arcs: list[Arc] = Field(default_factory=list)
    dramatic_pressure: float = Field(default=0.3, ge=0.0, le=1.0)


class GameSettings(BaseModel):
    """Хранится оркестратором per-world. Задаётся при создании мира."""

    language: Literal["ru", "en"] = "ru"
    difficulty: Literal["casual", "normal", "hardcore"] = "normal"
    generation_depth: Literal["compact", "rich"] = "compact"
    # Модели per-agent: можно подменять для экспериментов
    model_default: str = "claude-sonnet-4-6"
    model_heavy: str = "claude-sonnet-4-6"
    # Темп: сколько "внутриигрового времени" проходит за ход
    turn_tempo: Literal["scene", "minute", "hour"] = "scene"


# --- ход игры: intent + patch --------------------------------------------


class Intent(BaseModel):
    """Нормализованное намерение игрока. Orchestrator превращает в это free-text."""

    intent: str  # move | examine | converse | gather_information | use_item | wait | custom
    method: str | None = None
    target: str | None = None  # id сущности, если удалось сопоставить
    target_raw: str | None = None  # как игрок это назвал
    tone: str | None = None
    risk_level: Literal["low", "medium", "high"] = "low"
    raw_text: str


class PatchOp(BaseModel):
    """Одно атомарное изменение канона."""

    entity_type: Literal[
        "character",
        "location",
        "faction",
        "arc",
        "secret",
        "player_progression",
        "world_meta",
        "plot_state",
    ]
    id: str  # id сущности; для синглтонов ("player_progression", "world_meta", "plot_state") — "_"
    field: str  # имя поля верхнего уровня; вложенные через dot: "attributes.perception"
    op: Literal["set", "inc", "append", "remove"] = "set"
    value: Any = None


class TurnPatch(BaseModel):
    """Всё, что произошло за один ход. Результат работы агентов."""

    world_changes: list[PatchOp] = Field(default_factory=list)
    new_facts: list[str] = Field(default_factory=list)
    timeline_event: TimelineEvent | None = None
    # Нарративный отчёт агента о том, что произошло — для scene-master
    narrative_summary: str | None = None
