"""
Детерминированный context builder.

Не все поля канона нужны каждому агенту. Для конкретного хода мы
собираем минимальный релевантный срез:
  - текущую локацию (full);
  - соединённые локации (short);
  - NPC в локации игрока;
  - фракции, связанные с этими NPC;
  - арки, где замешаны затронутые сущности;
  - последние 5-10 timeline-событий;
  - прогрессию игрока.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from worldsim_schemas import (
    Arc,
    Character,
    Faction,
    Location,
    PlayerProgression,
    Secret,
    TimelineEvent,
)

from .persistence import WorldSnapshot, read_timeline


@dataclass
class TurnContext:
    """Передаётся каждому агенту. Сериализуется в JSON для user-message."""

    current_location: Location
    connected_locations: list[Location]
    player_character: Character
    nearby_npcs: list[Character]
    relevant_factions: list[Faction]
    relevant_arcs: list[Arc]
    known_secrets: list[Secret]  # только те, что игрок уже узнал
    recent_events: list[TimelineEvent]
    player_progression: PlayerProgression

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_location": self.current_location.model_dump(),
            "connected_locations": [loc.model_dump() for loc in self.connected_locations],
            "player_character": self.player_character.model_dump(),
            "nearby_npcs": [n.model_dump() for n in self.nearby_npcs],
            "relevant_factions": [f.model_dump() for f in self.relevant_factions],
            "relevant_arcs": [a.model_dump() for a in self.relevant_arcs],
            "known_secrets": [s.model_dump() for s in self.known_secrets],
            "recent_events": [e.model_dump() for e in self.recent_events],
            "player_progression": self.player_progression.model_dump(),
        }


def build_turn_context(snapshot: WorldSnapshot, *, recent_n: int = 8) -> TurnContext:
    pc = _player_character(snapshot)
    cur_loc = snapshot.locations[pc.location_id]

    connected = [
        snapshot.locations[lid]
        for lid in cur_loc.connected_to
        if lid in snapshot.locations
    ]

    nearby = [c for c in snapshot.characters.values() if c.location_id == cur_loc.id and not c.is_player]

    faction_ids = {c.faction_id for c in nearby if c.faction_id}
    relevant_factions = [f for fid, f in snapshot.factions.items() if fid in faction_ids]

    relevant_entity_ids = {cur_loc.id} | {c.id for c in nearby} | faction_ids
    relevant_arcs = [
        a
        for a in snapshot.arcs.values()
        if any(eid in relevant_entity_ids for eid in a.involved_entities)
    ]

    known_secrets = [
        s
        for s in snapshot.secrets.values()
        if s.status in ("hinted", "revealed") and _player_knows_secret(pc, snapshot.player_progression, s)
    ]

    recent = read_timeline(snapshot.meta.id, last_n=recent_n)

    return TurnContext(
        current_location=cur_loc,
        connected_locations=connected,
        player_character=pc,
        nearby_npcs=nearby,
        relevant_factions=relevant_factions,
        relevant_arcs=relevant_arcs,
        known_secrets=known_secrets,
        recent_events=recent,
        player_progression=snapshot.player_progression,
    )


def _player_character(snapshot: WorldSnapshot) -> Character:
    pc_id = snapshot.meta.player_character_id
    if pc_id in snapshot.characters:
        return snapshot.characters[pc_id]
    # fallback — первый is_player=True
    for c in snapshot.characters.values():
        if c.is_player:
            return c
    raise RuntimeError("В мире нет персонажа игрока (is_player=True).")


def _player_knows_secret(
    pc: Character, progression: PlayerProgression, secret: Secret
) -> bool:
    if pc.id in secret.known_by:
        return True
    return secret.id in progression.known_facts
