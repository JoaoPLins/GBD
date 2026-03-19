from pathlib import Path
from map import Map


class Game():
    def __init__(self):
        self.map = Map(0, 0)
        geojson_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "provinces.geojson"
        self.map.load_provinces(str(geojson_path))
        self.test = self.map.get_all_provinces()
        print(self.test)
        self.test = self.map.get_province_by_id(1)
        print(self.test)




game = Game()