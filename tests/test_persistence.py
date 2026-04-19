"""Тесты сохранения/загрузки и применения патчей."""

import os
import tempfile

import pytest

from worldsim_schemas import (
    Character,
    GameSettings,
    Location,
    PatchOp,
    PlayerProgression,
    PlotState,
    TurnPatch,
    WorldMeta,
)

from worldsim_orchestrator.persistence import (
    WorldSnapshot,
    apply_patches,
    apply_turn,
    load_world,
    new_world_id,
    save_world,
)


@pytest.fixture
def snapshot(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("WORLDSIM_SAVES_DIR", tmp)

    wid = new_world_id()
    return WorldSnapshot(
        meta=WorldMeta(id=wid, title="T", genre="g", premise="p"),
        settings=GameSettings(),
        locations={"loc_a": Location(id="loc_a", name="A", short_description="a")},
        characters={
            "pc": Character(id="pc", name="Player", is_player=True, location_id="loc_a"),
            "npc_1": Character(id="npc_1", name="Npc", location_id="loc_a", attitude_to_player=0.0),
        },
        plot_state=PlotState(),
        player_progression=PlayerProgression(),
    )


def test_save_and_load(snapshot):
    save_world(snapshot)
    loaded = load_world(snapshot.meta.id)
    assert loaded.meta.title == "T"
    assert "pc" in loaded.characters
    assert "loc_a" in loaded.locations


def test_apply_set(snapshot):
    op = PatchOp(entity_type="character", id="npc_1", field="attitude_to_player", op="set", value=0.5)
    apply_patches(snapshot, [op])
    assert snapshot.characters["npc_1"].attitude_to_player == 0.5


def test_apply_inc(snapshot):
    op = PatchOp(
        entity_type="player_progression",
        id="_",
        field="attributes.perception",
        op="inc",
        value=1,
    )
    apply_patches(snapshot, [op])
    assert snapshot.player_progression.attributes.perception == 2


def test_apply_append(snapshot):
    op = PatchOp(
        entity_type="player_progression",
        id="_",
        field="inventory",
        op="append",
        value="rope",
    )
    apply_patches(snapshot, [op])
    assert "rope" in snapshot.player_progression.inventory


def test_apply_remove(snapshot):
    snapshot.player_progression.inventory = ["a", "b"]
    op = PatchOp(
        entity_type="player_progression",
        id="_",
        field="inventory",
        op="remove",
        value="a",
    )
    apply_patches(snapshot, [op])
    assert snapshot.player_progression.inventory == ["b"]


def test_apply_turn_merges_new_facts(snapshot):
    patch = TurnPatch(new_facts=["fact_1", "fact_2"])
    apply_turn(snapshot, patch)
    assert snapshot.player_progression.known_facts == ["fact_1", "fact_2"]


def test_apply_turn_deduplicates_facts(snapshot):
    snapshot.player_progression.known_facts = ["fact_1"]
    patch = TurnPatch(new_facts=["fact_1", "fact_2"])
    apply_turn(snapshot, patch)
    assert snapshot.player_progression.known_facts.count("fact_1") == 1
    assert "fact_2" in snapshot.player_progression.known_facts


def test_load_world_missing_raises(monkeypatch):
    import tempfile
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("WORLDSIM_SAVES_DIR", tmp)
    with pytest.raises(FileNotFoundError):
        load_world("nonexistent_world_id")


def test_apply_patches_empty_list(snapshot):
    original_loc = snapshot.locations["loc_a"].name
    apply_patches(snapshot, [])
    assert snapshot.locations["loc_a"].name == original_loc


def test_apply_patches_location(snapshot):
    op = PatchOp(entity_type="location", id="loc_a", field="visited", op="set", value=True)
    apply_patches(snapshot, [op])
    assert snapshot.locations["loc_a"].visited is True


def test_apply_patches_world_meta(snapshot):
    op = PatchOp(entity_type="world_meta", id="_", field="tick", op="inc", value=1)
    apply_patches(snapshot, [op])
    assert snapshot.meta.tick == 1


def test_apply_patches_plot_state(snapshot):
    op = PatchOp(entity_type="plot_state", id="_", field="dramatic_pressure", op="set", value=0.9)
    apply_patches(snapshot, [op])
    assert snapshot.plot_state.dramatic_pressure == pytest.approx(0.9)


def test_apply_patches_player_progression(snapshot):
    op = PatchOp(entity_type="player_progression", id="_", field="known_facts", op="append", value="new_fact")
    apply_patches(snapshot, [op])
    assert "new_fact" in snapshot.player_progression.known_facts


def test_apply_patches_append_non_list_raises(snapshot):
    op = PatchOp(entity_type="character", id="pc", field="name", op="append", value="x")
    with pytest.raises(TypeError):
        apply_patches(snapshot, [op])


def test_apply_patches_unknown_entity_type_raises(snapshot):
    from worldsim_schemas import PatchOp as RealPatchOp
    import pydantic
    # Создаём PatchOp в обход validation через construct
    op = RealPatchOp.model_construct(entity_type="monster", id="x", field="hp", op="set", value=1)
    with pytest.raises(ValueError, match="Неизвестный entity_type"):
        apply_patches(snapshot, [op])


def test_apply_patches_unknown_op_raises(snapshot):
    from worldsim_schemas import PatchOp as RealPatchOp
    op = RealPatchOp.model_construct(entity_type="character", id="pc", field="name", op="delete", value="x")
    with pytest.raises(ValueError, match="Неизвестная операция"):
        apply_patches(snapshot, [op])


def test_timeline_append_and_read(snapshot, monkeypatch):
    import tempfile
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("WORLDSIM_SAVES_DIR", tmp)
    from worldsim_schemas import TimelineEvent
    from worldsim_orchestrator.persistence import append_timeline, read_timeline

    save_world(snapshot)
    ev1 = TimelineEvent(tick=1, type="move", summary="Игрок пошёл в доки.")
    ev2 = TimelineEvent(tick=2, type="converse", summary="Игрок поговорил с Мирой.")
    append_timeline(snapshot.meta.id, ev1)
    append_timeline(snapshot.meta.id, ev2)

    events = read_timeline(snapshot.meta.id)
    assert len(events) == 2
    assert events[0].tick == 1
    assert events[1].tick == 2


def test_timeline_read_last_n(snapshot, monkeypatch):
    import tempfile
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("WORLDSIM_SAVES_DIR", tmp)
    from worldsim_schemas import TimelineEvent
    from worldsim_orchestrator.persistence import append_timeline, read_timeline

    save_world(snapshot)
    for i in range(5):
        append_timeline(snapshot.meta.id, TimelineEvent(tick=i, type="t", summary=f"event {i}"))

    last2 = read_timeline(snapshot.meta.id, last_n=2)
    assert len(last2) == 2
    assert last2[-1].tick == 4


def test_timeline_read_empty(snapshot, monkeypatch):
    import tempfile
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("WORLDSIM_SAVES_DIR", tmp)
    from worldsim_orchestrator.persistence import read_timeline

    save_world(snapshot)
    assert read_timeline(snapshot.meta.id) == []


def test_list_worlds(monkeypatch):
    import tempfile
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("WORLDSIM_SAVES_DIR", tmp)
    from worldsim_orchestrator.persistence import list_worlds

    assert list_worlds() == []

    snap = WorldSnapshot(
        meta=WorldMeta(id="w_test", title="Тестовый", genre="фэнтези", premise="p"),
        settings=GameSettings(),
        player_progression=PlayerProgression(),
        plot_state=PlotState(),
    )
    save_world(snap)
    worlds = list_worlds()
    assert len(worlds) == 1
    assert worlds[0]["id"] == "w_test"
    assert worlds[0]["title"] == "Тестовый"
