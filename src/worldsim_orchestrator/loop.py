"""
Оркестровка одного хода. Последовательность согласно docs/loop.md.

Хода нет без LLM-клиента, поэтому если ANTHROPIC_API_KEY не задан —
функции падают на этапе инициализации клиента.

NB: агенты (worldsim-*-agent) импортируются лениво. Если какого-то из
них ещё нет в окружении — orchestrator упадёт с понятной ошибкой и
укажет на docs/setup.md.
"""

from __future__ import annotations

from worldsim_prompts import AnthropicClient
from worldsim_schemas import Intent, TurnPatch

from .context import TurnContext, build_turn_context
from .intent import parse_intent
from .persistence import WorldSnapshot, append_session_log, apply_turn, save_world
from .renderer import print_error, print_info, print_scene
from .validators import validate_intent
from .acquisition_renderer import render_acquisition_plan


class AgentUnavailable(RuntimeError):
    """Поднимается если нужный агент-пакет не установлен."""


def _import_agent(module: str, fn: str = "run"):
    try:
        mod = __import__(module, fromlist=[fn])
    except ImportError as e:
        raise AgentUnavailable(
            f"Агент-пакет «{module}» не установлен. См. "
            f"worldsim-workspace/docs/setup.md"
        ) from e
    return getattr(mod, fn)


def run_turn(
    snapshot: WorldSnapshot,
    player_input: str,
    *,
    client: AnthropicClient,
) -> str:
    """
    Исполняет один ход. Возвращает текст сцены для игрока. Мутирует
    snapshot и пишет на диск (timeline, session_log, save).
    """

    settings = snapshot.settings
    model_default = settings.model_default
    model_heavy = settings.model_heavy

    # 1. Контекст
    ctx = build_turn_context(snapshot)

    # 2. Intent (LLM)
    intent = parse_intent(player_input, ctx, client=client, model=model_default)

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

    # 4. Особая ветка: планирование приобретения возможности
    if intent.intent == "acquire_capability":
        return _run_acquisition_turn(snapshot, intent, ctx, player_input, client=client)

    # 5. npc-mind (если применимо)
    npc_response = None
    if intent.intent == "converse" and intent.target and intent.target in snapshot.characters:
        npc = snapshot.characters[intent.target]
        npc_mind_run = _import_agent("worldsim_npc_mind")
        npc_response = npc_mind_run(
            {"npc": npc.model_dump(), "intent": intent.model_dump(), "context": ctx.to_dict()},
            client=client,
            model=model_default,
        )

    # 6. world-builder.turn_update
    world_builder_turn = _import_agent("worldsim_world_builder", "run_turn_update")
    world_patch: TurnPatch = world_builder_turn(
        {
            "intent": intent.model_dump(),
            "npc_response": npc_response,
            "context": ctx.to_dict(),
        },
        client=client,
        model=model_heavy,
    )

    # 7. personal-progression.update
    progression_run = _import_agent("worldsim_personal_progression")
    progression_patch: TurnPatch = progression_run(
        {
            "intent": intent.model_dump(),
            "world_patch": world_patch.model_dump(),
            "progression": snapshot.player_progression.model_dump(),
            "context": ctx.to_dict(),
        },
        client=client,
        model=model_default,
    )

    # 8. canon-keeper.validate
    canon_validate = _import_agent("worldsim_canon_keeper", "validate")
    validation = canon_validate(
        {
            "patches": [*world_patch.world_changes, *progression_patch.world_changes],
            "snapshot": _snapshot_summary(snapshot),
        },
        client=client,
        model=model_heavy,
    )
    if not validation.get("ok"):
        print_error(
            "Канон отклонил патчи: " + "; ".join(validation.get("issues", [])),
            code="CANON_REJECTED",
        )
        return ""

    # 9. Применяем оба TurnPatch
    snapshot.meta.tick += 1
    combined = TurnPatch(
        world_changes=[*world_patch.world_changes, *progression_patch.world_changes],
        new_facts=[*world_patch.new_facts, *progression_patch.new_facts],
        timeline_event=world_patch.timeline_event,
        narrative_summary=world_patch.narrative_summary,
    )
    apply_turn(snapshot, combined)
    save_world(snapshot)

    # 10. scene-master.render
    scene_run = _import_agent("worldsim_scene_master")
    new_ctx = build_turn_context(snapshot)
    scene_text: str = scene_run(
        {
            "context": new_ctx.to_dict(),
            "last_action_summary": combined.narrative_summary,
        },
        client=client,
        model=model_default,
    )

    # 11. Session log
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


def _run_acquisition_turn(
    snapshot: WorldSnapshot,
    intent: Intent,
    ctx: TurnContext,
    player_input: str,
    *,
    client: AnthropicClient,
) -> str:
    """
    Ветка планирования приобретения возможности.

    Не изменяет канон — возвращает план испытаний игроку. Запись в
    session_log для истории. Мир не меняется до завершения испытаний.
    """
    settings = snapshot.settings

    # Описание цели: target_raw (если есть) иначе raw_text.
    # Тип: из method (intent_parser должен заполнить), иначе "general".
    acquisition_request = {
        "description": intent.target_raw or intent.raw_text,
        "type": intent.method or "general",
        "preferred_vector": None,
    }

    plan_fn = _import_agent("worldsim_personal_progression", "plan_acquisition")
    plan = plan_fn(
        {
            "acquisition_request": acquisition_request,
            "player_progression": snapshot.player_progression.model_dump(),
            "context": ctx.to_dict(),
        },
        client=client,
        model=settings.model_heavy,
    )

    scene_text = render_acquisition_plan(plan)

    append_session_log(
        snapshot.meta.id,
        {
            "tick": snapshot.meta.tick,
            "player_input": player_input,
            "intent": intent.model_dump(),
            "acquisition_plan": plan.model_dump(),
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


def show_welcome_scene(snapshot: WorldSnapshot, *, client: AnthropicClient) -> None:
    """Печатает стартовую сцену нового мира."""

    scene_run = _import_agent("worldsim_scene_master")
    ctx = build_turn_context(snapshot)
    scene_text: str = scene_run(
        {"context": ctx.to_dict(), "last_action_summary": None, "opening": True},
        client=client,
        model=snapshot.settings.model_default,
    )
    print_scene(scene_text, header=f"{snapshot.meta.title} — начало")
    print_info(f"Мир «{snapshot.meta.id}» создан. Вводи действия свободным текстом.")
