"""
Интеграционные тесты run_turn: полный ход с мок-реестром агентов.

Не вызывает реальный LLM. Мокает parse_intent и Registry.call,
проверяет что:
  - данные правильно передаются по цепочке агентов;
  - snapshot мутируется: tick, known_facts, timeline;
  - invalid intent → возвращает "";
  - canon_rejected → возвращает "";
  - converse → npc_mind вызывается; остальные интенты — нет.
"""

import io
import json
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from worldsim_schemas import (
    Arc,
    Character,
    Condition,
    Faction,
    GameSettings,
    Intent,
    Location,
    PatchOp,
    PlayerProgression,
    PlotState,
    TurnPatch,
    WorldMeta,
    TimelineEvent,
)
from worldsim_orchestrator.loop import run_turn, show_welcome_scene
from worldsim_orchestrator.persistence import WorldSnapshot, save_world


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def saves_dir(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("WORLDSIM_SAVES_DIR", tmp)
    return tmp


@pytest.fixture
def snapshot(saves_dir):
    loc_a = Location(id="loc_a", name="Доки", short_description="Соль.", connected_to=["loc_b"])
    loc_b = Location(id="loc_b", name="Рынок", short_description="Шум.")
    pc = Character(id="pc", name="Странник", is_player=True, location_id="loc_a")
    npc = Character(id="npc_mira", name="Мира", location_id="loc_a")
    faction = Faction(id="f_guild", name="Гильдия", public_role="Торговцы")

    snap = WorldSnapshot(
        meta=WorldMeta(id="w_integration", title="Интеграционный", genre="фэнтези", premise="Тест."),
        settings=GameSettings(),
        locations={"loc_a": loc_a, "loc_b": loc_b},
        characters={"pc": pc, "npc_mira": npc},
        factions={"f_guild": faction},
        plot_state=PlotState(),
        player_progression=PlayerProgression(),
    )
    save_world(snap)
    return snap


def _empty_turn_patch() -> TurnPatch:
    return TurnPatch()


def _mock_registry(
    *,
    world_patch: TurnPatch | None = None,
    progression_patch: TurnPatch | None = None,
    canon_result: dict | None = None,
    scene_text: str = "Туман над доками.",
    npc_response: dict | None = None,
) -> MagicMock:
    from worldsim_schemas import AgentPhase

    reg = MagicMock()
    world_patch = world_patch or _empty_turn_patch()
    progression_patch = progression_patch or _empty_turn_patch()
    canon_result = canon_result or {"ok": True, "issues": []}

    def call_side_effect(phase, payload, *, client, settings):
        if phase == AgentPhase.NPC_RESPOND:
            return npc_response
        if phase == AgentPhase.WORLD_UPDATE:
            return world_patch
        if phase == AgentPhase.PROGRESSION_UPDATE:
            return progression_patch
        if phase == AgentPhase.CANON_VALIDATE:
            return canon_result
        if phase == AgentPhase.SCENE_RENDER:
            return scene_text
        return None

    reg.call.side_effect = call_side_effect
    return reg


def _mock_intent(intent_str: str = "examine", target: str | None = None) -> Intent:
    return Intent(intent=intent_str, target=target, raw_text=f"тест: {intent_str}")


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_run_turn_returns_scene(snapshot):
    client = MagicMock()
    registry = _mock_registry(scene_text="Тихий причал.")
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=_mock_intent()):
        with patch("worldsim_orchestrator.loop.print_scene"):
            scene = run_turn(snapshot, "осматриваюсь", client=client, registry=registry)
    assert scene == "Тихий причал."


def test_run_turn_increments_tick(snapshot):
    assert snapshot.meta.tick == 0
    client = MagicMock()
    registry = _mock_registry()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=_mock_intent()):
        run_turn(snapshot, "иду", client=client, registry=registry)
    assert snapshot.meta.tick == 1


def test_run_turn_applies_world_changes(snapshot):
    op = PatchOp(entity_type="character", id="npc_mira", field="alive", op="set", value=False)
    world_patch = TurnPatch(world_changes=[op], narrative_summary="NPC погиб.")
    registry = _mock_registry(world_patch=world_patch)
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=_mock_intent()):
        run_turn(snapshot, "действую", client=client, registry=registry)
    assert snapshot.characters["npc_mira"].alive is False


def test_run_turn_adds_new_facts(snapshot):
    world_patch = TurnPatch(new_facts=["контрабандисты_активны"])
    registry = _mock_registry(world_patch=world_patch)
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=_mock_intent()):
        run_turn(snapshot, "наблюдаю", client=client, registry=registry)
    assert "контрабандисты_активны" in snapshot.player_progression.known_facts


def test_run_turn_writes_timeline(snapshot):
    ev = TimelineEvent(tick=1, type="move", summary="Игрок осмотрел доки.")
    world_patch = TurnPatch(timeline_event=ev)
    registry = _mock_registry(world_patch=world_patch)
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=_mock_intent()):
        run_turn(snapshot, "иду", client=client, registry=registry)
    from worldsim_orchestrator.persistence import read_timeline
    events = read_timeline(snapshot.meta.id)
    assert len(events) == 1
    assert events[0].summary == "Игрок осмотрел доки."


def test_run_turn_saves_world(snapshot, saves_dir):
    registry = _mock_registry()
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=_mock_intent()):
        run_turn(snapshot, "иду", client=client, registry=registry)
    from pathlib import Path
    assert (Path(saves_dir) / snapshot.meta.id / "world_meta.json").exists()


# ---------------------------------------------------------------------------
# validate_intent rejects
# ---------------------------------------------------------------------------


def test_run_turn_rejected_intent_returns_empty(snapshot):
    blocked_intent = Intent(intent="move", target="loc_unknown", raw_text="иду в никуда")
    registry = _mock_registry()
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=blocked_intent):
        with patch("worldsim_orchestrator.loop.print_error") as mock_err:
            scene = run_turn(snapshot, "иду в никуда", client=client, registry=registry)
    assert scene == ""
    mock_err.assert_called_once()


def test_run_turn_rejected_no_world_agents_called(snapshot):
    from worldsim_schemas import AgentPhase
    blocked = Intent(intent="move", target="loc_unknown", raw_text="иду в никуда")
    registry = _mock_registry()
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=blocked):
        with patch("worldsim_orchestrator.loop.print_error"):
            run_turn(snapshot, "иду в никуда", client=client, registry=registry)
    # Ни WORLD_UPDATE, ни SCENE_RENDER не должны вызываться
    phases_called = [c.args[0] for c in registry.call.call_args_list]
    assert AgentPhase.WORLD_UPDATE not in phases_called
    assert AgentPhase.SCENE_RENDER not in phases_called


def test_run_turn_tick_not_incremented_on_rejection(snapshot):
    blocked = Intent(intent="move", target="loc_unknown", raw_text="иду никуда")
    registry = _mock_registry()
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=blocked):
        with patch("worldsim_orchestrator.loop.print_error"):
            run_turn(snapshot, "иду никуда", client=client, registry=registry)
    assert snapshot.meta.tick == 0


# ---------------------------------------------------------------------------
# canon validation rejects
# ---------------------------------------------------------------------------


def test_run_turn_canon_rejected_returns_empty(snapshot):
    registry = _mock_registry(canon_result={"ok": False, "issues": ["arc_1 progress decreases"]})
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=_mock_intent()):
        with patch("worldsim_orchestrator.loop.print_error") as mock_err:
            scene = run_turn(snapshot, "действую", client=client, registry=registry)
    assert scene == ""
    mock_err.assert_called_once()


def test_run_turn_canon_rejected_no_patch_applied(snapshot):
    op = PatchOp(entity_type="character", id="npc_mira", field="alive", op="set", value=False)
    world_patch = TurnPatch(world_changes=[op])
    registry = _mock_registry(
        world_patch=world_patch,
        canon_result={"ok": False, "issues": ["ошибка"]}
    )
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=_mock_intent()):
        with patch("worldsim_orchestrator.loop.print_error"):
            run_turn(snapshot, "действую", client=client, registry=registry)
    assert snapshot.characters["npc_mira"].alive is True


# ---------------------------------------------------------------------------
# NPC converse flow
# ---------------------------------------------------------------------------


def test_run_turn_converse_calls_npc_mind(snapshot):
    from worldsim_schemas import AgentPhase
    intent = _mock_intent("converse", target="npc_mira")
    npc_response = {"speech": "Слышала кое-что...", "attitude_delta": 0.05, "revealed_facts": []}
    registry = _mock_registry(npc_response=npc_response)
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=intent):
        run_turn(snapshot, "говорю с Мирой", client=client, registry=registry)
    phases = [c.args[0] for c in registry.call.call_args_list]
    assert AgentPhase.NPC_RESPOND in phases


def test_run_turn_non_converse_skips_npc_mind(snapshot):
    from worldsim_schemas import AgentPhase
    intent = _mock_intent("examine")
    registry = _mock_registry()
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=intent):
        run_turn(snapshot, "осматриваюсь", client=client, registry=registry)
    phases = [c.args[0] for c in registry.call.call_args_list]
    assert AgentPhase.NPC_RESPOND not in phases


def test_run_turn_converse_without_target_skips_npc_mind(snapshot):
    from worldsim_schemas import AgentPhase
    intent = _mock_intent("converse", target=None)
    registry = _mock_registry()
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.parse_intent", return_value=intent):
        run_turn(snapshot, "говорю", client=client, registry=registry)
    phases = [c.args[0] for c in registry.call.call_args_list]
    assert AgentPhase.NPC_RESPOND not in phases


# ---------------------------------------------------------------------------
# show_welcome_scene
# ---------------------------------------------------------------------------


def test_show_welcome_scene_calls_scene_render(snapshot):
    from worldsim_schemas import AgentPhase
    registry = _mock_registry(scene_text="Добро пожаловать!")
    client = MagicMock()
    with patch("worldsim_orchestrator.loop.print_scene") as mock_print:
        with patch("worldsim_orchestrator.loop.print_info"):
            show_welcome_scene(snapshot, client=client, registry=registry)
    phases = [c.args[0] for c in registry.call.call_args_list]
    assert AgentPhase.SCENE_RENDER in phases
    mock_print.assert_called_once()
