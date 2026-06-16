from pathlib import Path
import sys
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from GBD_Python.gameGraphics import Graphics
from GBD_Python.nations import Nation, NationManager


class DummyMap:
    def __init__(self, provinces):
        self.provinces = provinces

    def get_province_by_id(self, province_id):
        return self.provinces.get(province_id)


class DummyArmy:
    def __init__(self, units):
        self.units = {unit.id: unit for unit in units}

    def get_all_units(self):
        return list(self.units.values())

    def get_unit(self, unit_id):
        return self.units.get(unit_id)


class DummyUnit:
    def __init__(self, unit_id, nation, location=1, spoted_by=None):
        self.id = unit_id
        self.nation = nation
        self.location = location
        self.spoted_by = spoted_by or []
        self.name = f"Unit {unit_id}"


def build_graphics():
    nation_manager = NationManager()
    nation_manager.nations = {
        "URU": Nation(tag="URU", name="Uruguay", nation_type="nation"),
        "SUB": Nation(tag="SUB", name="Substate", nation_type="state", parent="URU"),
        "ARG": Nation(tag="ARG", name="Argentina", nation_type="nation"),
    }

    player_unit = DummyUnit(1, "SUB", location=2)
    visible_enemy = DummyUnit(2, "ARG", location=2, spoted_by=[1])
    hidden_enemy = DummyUnit(3, "ARG", location=3, spoted_by=[])

    game = SimpleNamespace(
        nation="SUB",
        nation_manager=nation_manager,
        map=DummyMap(
            {
                1: {"id": 1, "controler": "URU", "owner": "URU", "nearby_provinces": [2]},
                2: {"id": 2, "controler": "ARG", "owner": "ARG", "nearby_provinces": [1, 3]},
                3: {"id": 3, "controler": "ARG", "owner": "ARG", "nearby_provinces": [2]},
            }
        ),
        armies={
            "player": DummyArmy([player_unit]),
            "enemy": DummyArmy([visible_enemy, hidden_enemy]),
        },
    )

    graphics = Graphics.__new__(Graphics)
    graphics.game = game
    graphics.fog_of_war = 1
    return graphics, player_unit, visible_enemy, hidden_enemy


def test_fog_of_war_uses_root_nation_visibility():
    graphics, player_unit, visible_enemy, hidden_enemy = build_graphics()

    assert graphics._get_root_nation_tag("SUB") == "URU"
    assert graphics._is_player_side_nation("URU")
    assert graphics._is_unit_visible_to_player(player_unit)
    assert graphics._is_unit_visible_to_player(visible_enemy)
    assert not graphics._is_unit_visible_to_player(hidden_enemy)


def test_fog_of_war_lights_controlled_and_adjacent_provinces():
    graphics, _, _, _ = build_graphics()

    assert graphics._province_is_visible_under_fog(graphics.game.map.get_province_by_id(1))
    assert graphics._province_is_visible_under_fog(graphics.game.map.get_province_by_id(2))
    assert graphics._province_is_visible_under_fog(graphics.game.map.get_province_by_id(3))
