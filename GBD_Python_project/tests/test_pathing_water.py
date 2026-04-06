from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from GBD_Python.simulation import Simulation


class DummyUnit:
    def __init__(self, unit_id, location, status=1):
        self.id = unit_id
        self.location = location
        self.status = status
        self.counter = 0
        self.speed = 1


class DummyArmy:
    def __init__(self, unit):
        self._unit = unit

    def get_unit(self, unit_id):
        if self._unit.id == unit_id:
            return self._unit
        return None


class DummyMap:
    def __init__(self, provinces):
        self._provinces = provinces

    def get_province_by_id(self, province_id):
        return self._provinces.get(province_id)


def _build_simulation(unit, provinces):
    armies = {1: DummyArmy(unit)}
    return Simulation(nation_manager=None, game_map=DummyMap(provinces), armies=armies)


def test_pathing_returns_empty_when_only_route_crosses_water():
    unit = DummyUnit(unit_id=7, location=1, status=1)
    provinces = {
        1: {"id": 1, "is_water": False, "nearby_provinces": [2]},
        2: {"id": 2, "is_water": True, "nearby_provinces": [1, 3]},
        3: {"id": 3, "is_water": False, "nearby_provinces": [2]},
    }

    simulation = _build_simulation(unit, provinces)
    path = simulation.pathing(unit_id=7, destination_province_id=3)

    assert path == []
    assert simulation.moviment_list == []
    assert simulation.moviment_time == []


def test_pathing_avoids_water_when_land_route_exists():
    unit = DummyUnit(unit_id=7, location=1, status=1)
    provinces = {
        1: {"id": 1, "is_water": False, "nearby_provinces": [2, 4]},
        2: {"id": 2, "is_water": True, "nearby_provinces": [1, 3]},
        3: {"id": 3, "is_water": False, "nearby_provinces": [2, 4]},
        4: {"id": 4, "is_water": False, "nearby_provinces": [1, 3]},
    }

    simulation = _build_simulation(unit, provinces)
    path = simulation.pathing(unit_id=7, destination_province_id=3)

    assert path == [1, 4, 3]
    assert simulation.moviment_list == [[7, 4, 3]]
    assert simulation.moviment_time == [[7, 16]]
