"""
Оркестровка одного хода. Последовательность согласно docs/loop.md.

Вызовы LLM-агентов идут через registry (worldsim-workspace/agents.toml) —
loop.py не знает имён конкретных пакетов. Добавление нового агента =
правка agents.toml, без изменений здесь.

Хода нет без LLM-клиента, поэтому если ANTHROPIC_API_KEY не задан —
функции падают на этапе инициализации клиента.
"""

from __future__ import annotations

from worldsim_prompts import AnthropicClient
from worldsim_schemas import AgentPhase, TurnPatch

from .context import build_turn_context
from .intent import parse_intent
from .persistence import WorldSnapshot, append_session_log, apply_turn, save_world
from .registry import Registry, load_registry
from .renderer import print_error, print_info, print_scene
from .validators import validate_intent


def run_turn(
    snapshot: WorldSnapshot,
    player_input: str,
    *,
    client: AnthropicClient,
    registry: Registry | None = None,
) -> str:
    """
    Исполняет один ход. Возвращает текст сцены для игрока. Мутирует
    snapshot и пишет на диск (timeline, session_log, save).
    """

    reg = registry or load_registry()
    settings = snapshot.settings

    # 1. Контекст
    ctx = build_turn_context(snapshot)

    # 2. Intent (LLM, не агент)
    intent = parse_intent(player_input, ctx, client=client, model=settings.model_default)

    # 3. Hard-constraints
    entities = {
        **snapshot.characters,
        **snapshot.locations,
        **snapshot.factions,
    }
    result = validate_intent(
        intent,
        player=snapshot.player_progression,
        player_character=ctx.player_character,
        current_location=ctx.current_location,
        entities=entities,
    )
    if not result.ok:
        print_error(result.message or "Невозможное действие.", code=result.code)
        append_session_log(
            snapshot.meta.id,
            {
                "tick": snapshot.meta.tick,
                "player_input": player_input,
                "intent": intent.model_dump(),
                "rejected": {"code": result.code, "message": result.message},
            },
        )
        return ""

    # 4. npc-mind (опционально, только для converse с NPC)
    npc_response = None
    if intent.intent == "converse" and intent.target and intent.target in snapshot.characters:
        npc = snapshot.characters[intent.target]
        npc_response = reg.call(
            AgentPhase.NPC_RESPOND,
            {
                "npc": npc.model_dump(),
                "intent": intent.model_dump(),
                "context": ctx.to_dict(),
            },
            client=client,
            settings=settings,
        )

    # 5. world_update
    world_patch: TurnPatch = reg.call(
        AgentPhase.WORLD_UPDATE,
        {
            "intent": intent.model_dump(),
            "npc_response": npc_response,
            "context": ctx.to_dict(),
        },
        client=client,
        settings=settings,
    )

    # 6. progression_update
    progression_patch: TurnPatch = reg.call(
        AgentPhase.PROGRESSION_UPDATE,
        {
            "intent": intent.model_dump(),
            "world_patch": world_patch.model_dump(),
            "progression": snapshot.player_progression.model_dump(),
            "context": ctx.to_dict(),
        },
        client=client,
        settings=settings,
    )

    # 7. canon_validate
    validation = reg.call(
        AgentPhase.CANON_VALIDATE,
        {
            "patches": [*world_patch.world_changes, *progression_patch.world_changes],
            "snapshot": _snapshot_summary(snapshot),
        },
        client=client,
        settings=settings,
    )
    if not validation.get("ok"):
        print_error(
            "Канон отклонил патчи: " + "; ".join(validation.get("issues", [])),
            code="CANON_REJECTED",
        )
        return ""

    # 8. Применяем оба TurnPatch
    snapshot.meta.tick += 1
    combined = TurnPatch(
        world_changes=[*world_patch.world_changes, *progression_patch.world_changes],
        new_facts=[*world_patch.new_facts, *progression_patch.new_facts],
        timeline_event=world_patch.timeline_event,
        narrative_summary=world_patch.narrative_summary,
    )
    apply_turn(snapshot, combined)
    save_world(snapshot)

    # 9. scene_render
    new_ctx = build_turn_context(snapshot)
    scene_text: str = reg.call(
        AgentPhase.SCENE_RENDER,
        {
            "context": new_ctx.to_dict(),
            "last_action_summary": combined.narrative_summary,
        },
        client=client,
        settings=settings,
    )

    # 10. Session log
    append_session_log(
        snapshot.meta.id,
        {
            "tick": snapshot.meta.tick,
            "player_input": player_input,
            "intent": intent.model_dump(),
            "patches": [p.model_dump() for p in combined.world_changes],
            "new_facts": combined.new_facts,
            "rendered_scene": scene_text,
        },
    )

    return scene_text


def _snapshot_summary(snapshot: WorldSnapshot) -> dict:
    """Компактный срез канона для canon-keeper. Не весь мир — только ids и связи."""

    return {
        "location_ids": list(snapshot.locations),
        "character_ids": list(snapshot.characters),
        "faction_ids": list(snapshot.factions),
        "secret_ids": list(snapshot.secrets),
        "arc_ids": list(snapshot.arcs),
        "player_location": snapshot.characters[snapshot.meta.player_character_id].location_id,
    }


def show_welcome_scene(
    snapshot: WorldSnapshot,
    *,
    client: AnthropicClient,
    registry: Registry | None = None,
) -> None:
    """Печатает стартовую сцену нового мира."""

    reg = registry or load_registry()
    ctx = build_turn_context(snapshot)
    scene_text: str = reg.call(
        AgentPhase.SCENE_RENDER,
        {"context": ctx.to_dict(), "last_action_summary": None, "opening": True},
        client=client,
        settings=snapshot.settings,
    )
    print_scene(scene_text, header=f"{snapshot.meta.title} — начало")
    print_info(f"Мир «{snapshot.meta.id}» создан. Вводи действия свободным текстом.")
