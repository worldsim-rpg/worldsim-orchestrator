"""
Тесты версионирования схем.

Покрывает:
- Pre-versioning сейв (без поля или с "0.0.0") грузится молча и штампуется.
- Сейв с той же MAJOR-версией грузится.
- Сейв с другой MAJOR-версией — SchemaVersionMismatch.
- Свежесохранённый сейв имеет SCHEMA_VERSION в world_meta.json.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from worldsim_schemas import (
    SCHEMA_VERSION,
    Character,
    GameSettings,
    Location,
    PlayerProgression,
    PlotState,
    WorldMeta,
    is_compatible,
    major,
)
from worldsim_orchestrator.persistence import (
    SchemaVersionMismatch,
    WorldSnapshot,
    load_world,
    new_world_id,
    save_world,
    saved_schema_version,
)


@pytest.fixture
def snap(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("WORLDSIM_SAVES_DIR", tmp)
    wid = new_world_id()
    return WorldSnapshot(
        meta=WorldMeta(id=wid, title="T", genre="g", premise="p"),
        settings=GameSettings(),
        locations={"loc_a": Location(id="loc_a", name="A", short_description="a")},
        characters={
            "pc": Character(id="pc", name="Player", is_player=True, location_id="loc_a"),
        },
        plot_state=PlotState(),
        player_progression=PlayerProgression(),
    )


# --- version.py API --------------------------------------------------------


def test_semver_parsing():
    assert major("0.1.2") == 0
    assert major("3.7.11") == 3


def test_compatibility():
    assert is_compatible("0.1.0", "0.5.9")
    assert is_compatible("1.0.0", "1.99.99")
    assert not is_compatible("0.9.9", "1.0.0")
    assert not is_compatible("2.0.0", "1.0.0")


def test_invalid_version_rejected():
    with pytest.raises(ValueError):
        major("not-a-version")


# --- save/load round-trip -------------------------------------------------


def test_save_stamps_current_version(snap):
    save_world(snap)
    stamped = saved_schema_version(snap.meta.id)
    assert stamped == SCHEMA_VERSION


def test_load_roundtrip_same_version(snap):
    save_world(snap)
    loaded = load_world(snap.meta.id)
    assert loaded.meta.schema_version == SCHEMA_VERSION


# --- pre-versioning совместимость -----------------------------------------


def test_pre_versioning_save_loads_silently(snap):
    """Старый сейв без schema_version (или с "0.0.0") грузится и потом перештампуется."""
    save_world(snap)
    # Симулируем старый сейв: удалим schema_version из world_meta.json.
    meta_path = Path(tempfile.gettempdir()) / "..." / "noop"  # placeholder, resolved below
    from worldsim_orchestrator.persistence import world_dir
    meta_file = world_dir(snap.meta.id) / "world_meta.json"
    data = json.loads(meta_file.read_text("utf-8"))
    data.pop("schema_version", None)
    meta_file.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_world(snap.meta.id)
    # pydantic-дефолт из WorldMeta = "0.0.0"
    assert loaded.meta.schema_version == "0.0.0"

    # После save перештамповано.
    save_world(loaded)
    assert saved_schema_version(snap.meta.id) == SCHEMA_VERSION


# --- несовместимая MAJOR-версия -------------------------------------------


def test_major_mismatch_refuses_load(snap):
    save_world(snap)
    from worldsim_orchestrator.persistence import world_dir
    meta_file = world_dir(snap.meta.id) / "world_meta.json"
    data = json.loads(meta_file.read_text("utf-8"))

    # Подменяем на заведомо чужой MAJOR.
    current_major = major(SCHEMA_VERSION)
    data["schema_version"] = f"{current_major + 5}.0.0"
    meta_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SchemaVersionMismatch):
        load_world(snap.meta.id)


def test_minor_mismatch_loads(snap):
    """Другой MINOR при том же MAJOR — грузится без ошибки."""
    save_world(snap)
    from worldsim_orchestrator.persistence import world_dir
    meta_file = world_dir(snap.meta.id) / "world_meta.json"
    data = json.loads(meta_file.read_text("utf-8"))
    # Бампаем MINOR в сейве (эмулируя сейв из более свежей MINOR).
    current_major = major(SCHEMA_VERSION)
    data["schema_version"] = f"{current_major}.99.0"
    meta_file.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_world(snap.meta.id)
    assert major(loaded.meta.schema_version) == current_major
