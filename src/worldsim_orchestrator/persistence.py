"""
JSON-персистентность канона мира.

Каждый мир — папка в `saves/<world_id>/` со своими файлами. Изменения
применяются через `PatchOp`, не полной перезаписью.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from worldsim_schemas import (
    Arc,
    Character,
    Faction,
    GameSettings,
    Location,
    PatchOp,
    PlayerProgression,
    PlotState,
    Secret,
    TimelineEvent,
    TurnPatch,
    WorldMeta,
)


# --- модель сейва на диске -----------------------------------------------


@dataclass
class WorldSnapshot:
    """Полный срез канона одного мира, загруженный в память."""

    meta: WorldMeta
    settings: GameSettings
    locations: dict[str, Location] = field(default_factory=dict)
    characters: dict[str, Character] = field(default_factory=dict)
    factions: dict[str, Faction] = field(default_factory=dict)
    secrets: dict[str, Secret] = field(default_factory=dict)
    arcs: dict[str, Arc] = field(default_factory=dict)
    plot_state: PlotState = field(default_factory=PlotState)
    player_progression: PlayerProgression = field(default_factory=PlayerProgression)


# --- файлы и пути ---------------------------------------------------------


def saves_root() -> Path:
    base = os.environ.get("WORLDSIM_SAVES_DIR", "saves")
    path = Path(base).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def world_dir(world_id: str) -> Path:
    return saves_root() / world_id


def new_world_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


# --- I/O низкоуровневый ---------------------------------------------------


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_list(items: dict[str, BaseModel]) -> list[dict]:
    return [item.model_dump() for item in items.values()]


def _load_list(data: list[dict], model: type[BaseModel]) -> dict[str, Any]:
    return {item["id"]: model.model_validate(item) for item in data}


# --- сохранение / загрузка мира ------------------------------------------


def save_world(snapshot: WorldSnapshot) -> None:
    d = world_dir(snapshot.meta.id)
    _write_json(d / "world_meta.json", snapshot.meta.model_dump())
    _write_json(d / "game_settings.json", snapshot.settings.model_dump())
    _write_json(d / "locations.json", _dump_list(snapshot.locations))
    _write_json(d / "characters.json", _dump_list(snapshot.characters))
    _write_json(d / "factions.json", _dump_list(snapshot.factions))
    _write_json(d / "secrets.json", _dump_list(snapshot.secrets))
    _write_json(d / "arcs.json", _dump_list(snapshot.arcs))
    _write_json(d / "plot_state.json", snapshot.plot_state.model_dump())
    _write_json(
        d / "player_progression.json",
        snapshot.player_progression.model_dump(),
    )
    # timeline и session_log — append-only, их тут не трогаем


def load_world(world_id: str) -> WorldSnapshot:
    d = world_dir(world_id)
    if not d.exists():
        raise FileNotFoundError(f"Мир «{world_id}» не найден в {saves_root()}")

    return WorldSnapshot(
        meta=WorldMeta.model_validate(_read_json(d / "world_meta.json")),
        settings=GameSettings.model_validate(_read_json(d / "game_settings.json")),
        locations=_load_list(_read_json(d / "locations.json"), Location),
        characters=_load_list(_read_json(d / "characters.json"), Character),
        factions=_load_list(_read_json(d / "factions.json"), Faction),
        secrets=_load_list(_read_json(d / "secrets.json"), Secret),
        arcs=_load_list(_read_json(d / "arcs.json"), Arc),
        plot_state=PlotState.model_validate(_read_json(d / "plot_state.json")),
        player_progression=PlayerProgression.model_validate(
            _read_json(d / "player_progression.json")
        ),
    )


def list_worlds() -> list[dict[str, str]]:
    root = saves_root()
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        meta_file = d / "world_meta.json"
        if not meta_file.exists():
            continue
        meta = _read_json(meta_file)
        out.append({"id": meta.get("id", d.name), "title": meta.get("title", "?"), "tick": str(meta.get("tick", 0))})
    return out


# --- применение патчей ---------------------------------------------------


def apply_patches(snapshot: WorldSnapshot, patches: list[PatchOp]) -> None:
    """
    Мутирует snapshot in-place. Вызывающий сам отвечает за save_world
    после применения.
    """

    for patch in patches:
        _apply_one(snapshot, patch)


def _apply_one(snapshot: WorldSnapshot, p: PatchOp) -> None:
    target = _resolve_target(snapshot, p)
    _set_field(target, p.field, p.op, p.value)


def _resolve_target(snapshot: WorldSnapshot, p: PatchOp) -> BaseModel:
    if p.entity_type == "character":
        return snapshot.characters[p.id]
    if p.entity_type == "location":
        return snapshot.locations[p.id]
    if p.entity_type == "faction":
        return snapshot.factions[p.id]
    if p.entity_type == "secret":
        return snapshot.secrets[p.id]
    if p.entity_type == "arc":
        return snapshot.arcs[p.id]
    if p.entity_type == "world_meta":
        return snapshot.meta
    if p.entity_type == "plot_state":
        return snapshot.plot_state
    if p.entity_type == "player_progression":
        return snapshot.player_progression
    raise ValueError(f"Неизвестный entity_type: {p.entity_type}")


def _set_field(obj: BaseModel, field_path: str, op: str, value: Any) -> None:
    """Поддерживает dot-пути: 'attributes.perception'."""

    parts = field_path.split(".")
    *head, last = parts

    # Спуск по вложенности
    cur: Any = obj
    for part in head:
        cur = getattr(cur, part)

    if op == "set":
        setattr(cur, last, value)
    elif op == "inc":
        setattr(cur, last, getattr(cur, last) + value)
    elif op == "append":
        current_list = getattr(cur, last)
        if not isinstance(current_list, list):
            raise TypeError(f"append в поле не-список: {field_path}")
        current_list.append(value)
    elif op == "remove":
        current_list = getattr(cur, last)
        if not isinstance(current_list, list):
            raise TypeError(f"remove в поле не-список: {field_path}")
        if value in current_list:
            current_list.remove(value)
    else:
        raise ValueError(f"Неизвестная операция: {op}")


# --- timeline (append-only) ----------------------------------------------


def append_timeline(world_id: str, event: TimelineEvent) -> None:
    path = world_dir(world_id) / "timeline.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")


def read_timeline(world_id: str, *, last_n: int | None = None) -> list[TimelineEvent]:
    path = world_dir(world_id) / "timeline.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if last_n is not None:
        lines = lines[-last_n:]
    return [TimelineEvent.model_validate(json.loads(ln)) for ln in lines]


def append_session_log(world_id: str, entry: dict) -> None:
    path = world_dir(world_id) / "session_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --- применение TurnPatch ------------------------------------------------


def apply_turn(snapshot: WorldSnapshot, patch: TurnPatch) -> None:
    """
    Применяет TurnPatch целиком: патчи + новые факты (в knowledge игрока)
    + timeline event. snapshot мутируется, timeline пишется на диск.
    """

    apply_patches(snapshot, patch.world_changes)

    for fact in patch.new_facts:
        if fact not in snapshot.player_progression.known_facts:
            snapshot.player_progression.known_facts.append(fact)

    if patch.timeline_event is not None:
        append_timeline(snapshot.meta.id, patch.timeline_event)
