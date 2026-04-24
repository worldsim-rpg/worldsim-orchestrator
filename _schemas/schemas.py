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


class VectorType(str, Enum):
    """Канал, через который персонаж движется к цели."""

    INFORMATION = "information"   # знания, данные, секреты
    PROPERTY = "property"         # предметы, ресурсы, активы
    SKILLS = "skills"             # умения, техники, опыт
    CONNECTIONS = "connections"   # люди, доступы, покровители


class Capability(BaseModel):
    """Возможность, которой владеет персонаж — итог завершённого пути."""

    id: str
    description: str
    type: str                                                        # доменный тип (combat, magic, social, …)
    vector: VectorType
    world_impact: float = Field(default=0.0, ge=0.0, le=100.0)
    persona_impact: float = Field(default=0.0, ge=0.0, le=100.0)
    acquired_at_tick: int = 0


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
    capabilities: list[Capability] = Field(default_factory=list)


# --- планирование приобретения возможностей (v0.4-rev) -------------------


class AcquisitionRequest(BaseModel):
    """Что персонаж хочет приобрести. Минимальный ввод от оркестратора."""

    description: str
    type: str                               # доменный тип: combat, magic, social, …
    preferred_vector: VectorType | None = None


class FeasibilityComponents(BaseModel):
    """Шаг 2: три компонента выполнимости [0..1]."""

    channel_access: float = Field(ge=0.0, le=1.0)
    resource_readiness: float = Field(ge=0.0, le=1.0)
    world_permission: float = Field(ge=0.0, le=1.0)


class ImpactEstimate(BaseModel):
    """Шаг 3: влияние на мир и персонажа [0..100] каждое."""

    world_impact: float = Field(ge=0.0, le=100.0)
    persona_impact: float = Field(ge=0.0, le=100.0)


class UniquenessComponents(BaseModel):
    """Шаг 5: три компонента уникальности сценария [0..1]."""

    path_rarity: float = Field(ge=0.0, le=1.0)
    persona_fit: float = Field(ge=0.0, le=1.0)
    condition_rarity: float = Field(ge=0.0, le=1.0)


class ConflictInfo(BaseModel):
    """Шаг 8: информация о конфликтах с имеющимися возможностями."""

    conflicting_capability_ids: list[str] = Field(default_factory=list)
    conflict_types_affected: int = Field(default=0, ge=0, le=4)
    alternative_vectors: list[VectorType] = Field(default_factory=list)


class AcquisitionEval(BaseModel):
    """
    Полная оценка LLM для шагов 2–5, 8.

    LLM выставляет все числовые оценки; движок (acquisition_engine.py)
    применяет к ним формулы из схемы v0.4-rev.
    """

    # Шаг 1: метрики цели (LLM выводит из description + context)
    universality: float = Field(ge=0.0, le=100.0)
    prevalence: float = Field(ge=0.0, le=100.0)
    divergence: float = Field(ge=0.0, le=100.0)
    favorable_factors: float = Field(ge=0.0, le=100.0)

    # Шаги 2–5, 8
    chosen_vector: VectorType
    feasibility: FeasibilityComponents
    impact: ImpactEstimate
    uniqueness: UniquenessComponents
    conflicts: ConflictInfo
    blocking_factor: str | None = None


class FeasibilityStatus(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class ConflictStatus(str, Enum):
    CLEAN = "clean"
    ALTERNATIVE_ROUTE = "alternative_route"
    PARTIAL_CONFLICT = "partial_conflict"
    FULL_CONFLICT_PENDING = "full_conflict_pending"
    IMPOSSIBLE = "impossible"


class Trial(BaseModel):
    """Атомарное испытание внутри маршрута."""

    id: str
    description: str
    difficulty: float = Field(ge=0.0, le=100.0)
    error_chance: float = Field(ge=0.0, le=1.0)
    error_cost: float = Field(ge=0.0, le=100.0)
    irreversibility: float | None = Field(default=None, ge=0.0, le=1.0)
    accumulation: float | None = Field(default=None, ge=0.0, le=1.0)


class CapabilityRoute(BaseModel):
    """Один маршрут с плоским списком испытаний."""

    vector: VectorType
    trials: list[Trial]
    total_difficulty: float
    inflation_factor: float   # сумма сложностей испытаний / difficulty_target


class AcquisitionPlan(BaseModel):
    """Полный план приобретения возможности — результат plan_acquisition()."""

    routes: list[CapabilityRoute]
    value: float = Field(ge=0.0, le=100.0)
    value_core: float
    value_bonus: float
    difficulty_target: float = Field(ge=0.0, le=100.0)
    type_saturation_penalty: float
    vector: VectorType
    world_impact: float
    persona_impact: float
    scenario_uniqueness: float = Field(ge=0.0, le=1.0)
    feasibility_status: FeasibilityStatus
    feasibility_score: float
    partial_coverage: bool
    conflict_status: ConflictStatus
    conflicting_capability_ids: list[str] = Field(default_factory=list)
    blocking_factor: str | None = None


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
