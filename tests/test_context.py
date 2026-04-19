"""Тесты детерминированного context builder."""

import os
import tempfile

import pytest

from worldsim_schemas import (
    Arc,
    ArcStage,
    Character,
    Faction,
    GameSettings,
    Location,
    PlayerProgression,
    PlotState,
    Secret,
    WorldMeta,
)
from worldsim_orchestrator.context import TurnContext, build_turn_context, _player_character
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
def base_snapshot(saves_dir):
    loc_a = Location(id="loc_a", name="Доки", short_description="Соль и верёвки.", connected_to=["loc_b"])
    loc_b = Location(id="loc_b", name="Рынок", short_description="Шум.")
    guild = Faction(id="f_guild", name="Гильдия", public_role="Торговцы")
    npc = Character(id="npc_mira", name="Мира", location_id="loc_a", faction_id="f_guild")
    npc_away = Character(id="npc_away", name="Вдали", location_id="loc_b")
    pc = Character(id="pc", name="Странник", is_player=True, location_id="loc_a")
    arc = Arc(
        id="arc_1",
        title="Тайна",
        stage=ArcStage.HOOK,
        involved_entities=["loc_a", "npc_mira"],
    )
    secret = Secret(id="s1", truth="Правда", known_by=["pc"], status="hinted")
    secret_hidden = Secret(id="s2", truth="Скрытое", status="hidden")

    snap = WorldSnapshot(
        meta=WorldMeta(id="w_ctx", title="Мир", genre="фэнтези", premise="p"),
        settings=GameSettings(),
        locations={"loc_a": loc_a, "loc_b": loc_b},
        characters={"pc": pc, "npc_mira": npc, "npc_away": npc_away},
        factions={"f_guild": guild},
        arcs={"arc_1": arc},
        secrets={"s1": secret, "s2": secret_hidden},
        plot_state=PlotState(),
        player_progression=PlayerProgression(),
    )
    save_world(snap)
    return snap


# ---------------------------------------------------------------------------
# _player_character
# ---------------------------------------------------------------------------


def test_player_character_by_id(base_snapshot):
    pc = _player_character(base_snapshot)
    assert pc.id == "pc"


def test_player_character_fallback():
    # Нет player_character_id в словаре — fallback к is_player=True
    snap = WorldSnapshot(
        meta=WorldMeta(id="w_f", title="t", genre="g", premise="p", player_character_id="missing"),
        settings=GameSettings(),
        characters={"hero": Character(id="hero", name="Герой", is_player=True, location_id="l")},
        locations={"l": Location(id="l", name="L", short_description="d")},
        plot_state=PlotState(),
        player_progression=PlayerProgression(),
    )
    pc = _player_character(snap)
    assert pc.id == "hero"


def test_player_character_missing_raises():
    snap = WorldSnapshot(
        meta=WorldMeta(id="w_e", title="t", genre="g", premise="p", player_character_id="nobody"),
        settings=GameSettings(),
        characters={},
        plot_state=PlotState(),
        player_progression=PlayerProgression(),
    )
    with pytest.raises(RuntimeError, match="is_player"):
        _player_character(snap)


# ---------------------------------------------------------------------------
# build_turn_context
# ---------------------------------------------------------------------------


def test_build_turn_context_current_location(base_snapshot, saves_dir):
    ctx = build_turn_context(base_snapshot)
    assert ctx.current_location.id == "loc_a"


def test_build_turn_context_connected_locations(base_snapshot):
    ctx = build_turn_context(base_snapshot)
    assert any(loc.id == "loc_b" for loc in ctx.connected_locations)


def test_build_turn_context_nearby_npcs_only_same_location(base_snapshot):
    ctx = build_turn_context(base_snapshot)
    npc_ids = [n.id for n in ctx.nearby_npcs]
    assert "npc_mira" in npc_ids
    assert "npc_away" not in npc_ids
    assert "pc" not in npc_ids


def test_build_turn_context_relevant_factions(base_snapshot):
    ctx = build_turn_context(base_snapshot)
    faction_ids = [f.id for f in ctx.relevant_factions]
    assert "f_guild" in faction_ids


def test_build_turn_context_relevant_arcs(base_snapshot):
    ctx = build_turn_context(base_snapshot)
    arc_ids = [a.id for a in ctx.relevant_arcs]
    assert "arc_1" in arc_ids


def test_build_turn_context_known_secrets_filtered(base_snapshot):
    ctx = build_turn_context(base_snapshot)
    secret_ids = [s.id for s in ctx.known_secrets]
    assert "s1" in secret_ids   # hinted + known_by includes pc
    assert "s2" not in secret_ids  # hidden


def test_build_turn_context_player_progression(base_snapshot):
    ctx = build_turn_context(base_snapshot)
    assert isinstance(ctx.player_progression, PlayerProgression)


def test_build_turn_context_recent_events_empty(base_snapshot):
    ctx = build_turn_context(base_snapshot)
    assert ctx.recent_events == []


# ---------------------------------------------------------------------------
# TurnContext.to_dict
# ---------------------------------------------------------------------------


def test_turn_context_to_dict_keys(base_snapshot):
    ctx = build_turn_context(base_snapshot)
    d = ctx.to_dict()
    expected_keys = {
        "current_location",
        "connected_locations",
        "player_character",
        "nearby_npcs",
        "relevant_factions",
        "relevant_arcs",
        "known_secrets",
        "recent_events",
        "player_progression",
    }
    assert expected_keys == set(d.keys())


def test_turn_context_to_dict_serializable(base_snapshot):
    import json
    ctx = build_turn_context(base_snapshot)
    d = ctx.to_dict()
    # Должно сериализоваться без ошибок
    raw = json.dumps(d, ensure_ascii=False)
    assert "loc_a" in raw


def test_turn_context_to_dict_current_location_structure(base_snapshot):
    ctx = build_turn_context(base_snapshot)
    d = ctx.to_dict()
    assert d["current_location"]["id"] == "loc_a"
    assert isinstance(d["nearby_npcs"], list)
    assert isinstance(d["connected_locations"], list)
