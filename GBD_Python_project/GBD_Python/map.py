import json

class Map():
    def __init__(self, center_x, center_y):
        self.center_x = center_x
        self.center_y = center_y
        self.provinces = []
        self._province_index = {}

    def load_provinces(self, geojson_file):
        with open(geojson_file, encoding="utf-8") as f:
            data = json.load(f)

        for feature in data["features"]:
            props = feature["properties"]
            geom = feature["geometry"]

            polygons = []

            if geom["type"] == "Polygon":
                polygons.append(geom["coordinates"][0])

            elif geom["type"] == "MultiPolygon":
                for poly in geom["coordinates"]:
                    polygons.append(poly[0])

            province = {
                "id": props["id"],
                "polygons": polygons,
                "terrain": props["terrain"],
                "is_water": props["is_water"]
            }

            self.provinces.append(province)
            self._province_index[province["id"]] = province
    
    def get_all_provinces(self):
        """Return a list of all loaded provinces."""
        # Return a copy to prevent callers from accidentally modifying internal state.
        return list(self.provinces)

    def get_province_by_id(self, province_id):
        """Return the province dict with the given id, or None if not found."""
        return self._province_index.get(province_id)

    