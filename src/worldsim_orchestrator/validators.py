"""
Hard-constraints: детерминированные проверки, которые Python делает ДО
любого LLM-вызова. Таблица правил — в workspace/docs/constraints.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from worldsim_schemas import Character, Intent, Location, PlayerProgression


@dataclass
class ConstraintResult:
    ok: bool
    code: str | None = None
    message: str | None = None

    @classmethod
    def passed(cls) -> ConstraintResult:
        return cls(ok=True)

    @classmethod
    def failed(cls, code: str, message: str) -> ConstraintResult:
        return cls(ok=False, code=code, message=message)


# --- атомарные проверки ---------------------------------------------------


def has_item(player: PlayerProgression, item_id: str) -> ConstraintResult:
    if item_id not in player.inventory:
        return ConstraintResult.failed("NO_ITEM", f"У тебя нет «{item_id}».")
    return ConstraintResult.passed()


def at_location(character: Character, location_id: str) -> ConstraintResult:
    if character.location_id != location_id:
        return ConstraintResult.failed(
            "WRONG_LOCATION",
            f"«{character.name}» сейчас не здесь (находится в «{character.location_id}»).",
        )
    return ConstraintResult.passed()


def is_connected(from_loc: Location, to_id: str) -> ConstraintResult:
    if to_id not in from_loc.connected_to:
        return ConstraintResult.failed(
            "NOT_CONNECTED",
            f"От «{from_loc.name}» нет прямого пути до «{to_id}».",
        )
    return ConstraintResult.passed()


def is_alive(character: Character) -> ConstraintResult:
    if not character.alive:
        return ConstraintResult.failed(
            "DEAD", f"«{character.name}» мёртв и не может действовать."
        )
    return ConstraintResult.passed()


def npc_knows(character: Character, fact: str) -> ConstraintResult:
    if fact not in character.knowledge:
        return ConstraintResult.failed(
            "UNKNOWN_TO_NPC",
            f"«{character.name}» не знает ничего о «{fact}».",
        )
    return ConstraintResult.passed()


def player_knows(player: PlayerProgression, fact: str) -> ConstraintResult:
    if fact not in player.known_facts:
        return ConstraintResult.failed(
            "UNKNOWN_TO_PLAYER",
            f"Ты ещё не знаешь ничего о «{fact}».",
        )
    return ConstraintResult.passed()


def condition_allows(player: PlayerProgression, min_level: str = "tired") -> ConstraintResult:
    """`exhausted` запрещает рискованные действия."""
    blocked = {"exhausted": {"low", "medium", "high"}}
    if player.condition.value in blocked:
        return ConstraintResult.failed(
            "CONDITION_BLOCKED",
            "Ты слишком истощён для этого. Нужно отдохнуть.",
        )
    return ConstraintResult.passed()


# --- высокоуровневая валидация Intent -------------------------------------


def validate_intent(
    intent: Intent,
    *,
    player: PlayerProgression,
    player_character: Character,
    current_location: Location,
    entities: dict[str, object],
) -> ConstraintResult:
    """
    Единая точка проверки. `entities` — словарь `id -> объект` (Character,
    Location и т.п.), загруженный из канона для текущего хода.
    """

    # 1. Если цель задана по id — она должна существовать
    if intent.target is not None and intent.target not in entities:
        return ConstraintResult.failed(
            "UNKNOWN_TARGET",
            f"В мире нет сущности с id «{intent.target}».",
        )

    # 2. Проверки по типу intent
    if intent.intent == "use_item":
        if intent.target_raw is None:
            return ConstraintResult.failed("NO_TARGET", "Не указано, какой предмет использовать.")
        # target для use_item — это item_id из инвентаря
        r = has_item(player, intent.target or intent.target_raw)
        if not r.ok:
            return r

    elif intent.intent == "move":
        if intent.target is None:
            return ConstraintResult.failed("NO_TARGET", "Куда именно двигаться?")
        r = is_connected(current_location, intent.target)
        if not r.ok:
            return r

    elif intent.intent == "converse":
        if intent.target is None:
            return ConstraintResult.passed()  # orchestrator запросит уточнение отдельно
        target = entities.get(intent.target)
        if isinstance(target, Character):
            r = is_alive(target)
            if not r.ok:
                return r
            r = at_location(target, player_character.location_id)
            if not r.ok:
                return r

    # 3. Состояние игрока для рискованных действий
    if intent.risk_level in ("medium", "high"):
        r = condition_allows(player)
        if not r.ok:
            return r

    return ConstraintResult.passed()
