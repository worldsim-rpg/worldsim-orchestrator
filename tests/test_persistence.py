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
