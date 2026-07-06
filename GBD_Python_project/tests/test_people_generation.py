from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from GBD_Python.people import PeopleManager


def test_generate_10_people_in_province_1():
    manager = PeopleManager()

    manager.generate_people(location=1, ammount=10)

    generated_people = manager.people_list[1:]

    assert len(generated_people) == 10
    assert manager.people_alive == 10
    assert manager.counter == 11

    for index, person in enumerate(generated_people, start=1):
        assert person.id == index
        assert person.nation == 1
        assert person.home == 1
        assert person.location == 1
        assert person.alive is True