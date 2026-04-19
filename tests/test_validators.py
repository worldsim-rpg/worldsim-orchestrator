"""Unit-тесты hard-constraints."""

from worldsim_schemas import (
    Character,
    Condition,
    Intent,
    Location,
    PlayerProgression,
)

from worldsim_orchestrator.validators import (
    at_location,
    condition_allows,
    has_item,
    is_alive,
    is_connected,
    npc_knows,
    player_knows,
    validate_intent,
)


def _pc(location_id: str = "loc_a") -> Character:
    return Character(id="pc", name="Игрок", is_player=True, location_id=location_id)


def test_has_item_ok():
    pp = PlayerProgression(inventory=["key"])
    assert has_item(pp, "key").ok


def test_has_item_missing():
    pp = PlayerProgression()
    r = has_item(pp, "key")
    assert not r.ok
    assert r.code == "NO_ITEM"


def test_at_location_ok():
    c = Character(id="npc", name="Npc", location_id="loc_a")
    assert at_location(c, "loc_a").ok


def test_at_location_wrong():
    c = Character(id="npc", name="Npc", location_id="loc_b")
    r = at_location(c, "loc_a")
    assert r.code == "WRONG_LOCATION"


def test_is_connected_ok():
    loc = Location(id="loc_a", name="A", short_description="a", connected_to=["loc_b"])
    assert is_connected(loc, "loc_b").ok


def test_is_connected_no():
    loc = Location(id="loc_a", name="A", short_description="a", connected_to=["loc_b"])
    r = is_connected(loc, "loc_c")
    assert r.code == "NOT_CONNECTED"


def test_is_alive():
    dead = Character(id="x", name="X", location_id="l", alive=False)
    assert is_alive(dead).code == "DEAD"


def test_npc_knows():
    npc = Character(id="x", name="X", location_id="l", knowledge=["fact_a"])
    assert npc_knows(npc, "fact_a").ok
    assert npc_knows(npc, "fact_b").code == "UNKNOWN_TO_NPC"


def test_player_knows():
    pp = PlayerProgression(known_facts=["fact_a"])
    assert player_knows(pp, "fact_a").ok
    assert player_knows(pp, "fact_b").code == "UNKNOWN_TO_PLAYER"


def test_condition_blocks_high_risk():
    pp = PlayerProgression(condition=Condition.EXHAUSTED)
    assert condition_allows(pp).code == "CONDITION_BLOCKED"


def test_validate_intent_move_requires_connection():
    pc = _pc("loc_a")
    loc = Location(id="loc_a", name="A", short_description="a", connected_to=["loc_b"])
    intent = Intent(intent="move", target="loc_c", raw_text="иду в loc_c")
    r = validate_intent(
        intent,
        player=PlayerProgression(),
        player_character=pc,
        current_location=loc,
        entities={"loc_a": loc, "pc": pc, "loc_c": Location(id="loc_c", name="C", short_description="c")},
    )
    assert r.code == "NOT_CONNECTED"


def test_validate_intent_converse_checks_coplace():
    pc = _pc("loc_a")
    npc = Character(id="npc_mira", name="Мира", location_id="loc_b")
    loc = Location(id="loc_a", name="A", short_description="a")
    intent = Intent(intent="converse", target="npc_mira", raw_text="говорю с Мирой")
    r = validate_intent(
        intent,
        player=PlayerProgression(),
        player_character=pc,
        current_location=loc,
        entities={"pc": pc, "npc_mira": npc, "loc_a": loc},
    )
    assert r.code == "WRONG_LOCATION"


def test_validate_intent_use_item_requires_inventory():
    pc = _pc("loc_a")
    loc = Location(id="loc_a", name="A", short_description="a")
    intent = Intent(intent="use_item", target_raw="key", raw_text="использую ключ")
    r = validate_intent(
        intent,
        player=PlayerProgression(),
        player_character=pc,
        current_location=loc,
        entities={"pc": pc, "loc_a": loc},
    )
    assert r.code == "NO_ITEM"
