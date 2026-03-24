import json
import csv
from shapely.geometry import Point, Polygon

class Map():
    def __init__(self, center_x, center_y):
        self.center_x = center_x
        self.center_y = center_y
        self.provinces = []
        self._province_index = {}

    def load_provinces(self, geojson_file, nearby_csv_file=None):
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
                "is_water": props["is_water"],
                "owner": props["owner"],
                "controler": props["controler"],
                "nearby_provinces": []
            }

            self.provinces.append(province)
            self._province_index[province["id"]] = province
        
        # Load nearby provinces if CSV file is provided
        if nearby_csv_file:
            self._load_nearby_from_csv(nearby_csv_file)
    
    def _load_nearby_from_csv(self, csv_file):
        """Load nearby provinces data from a CSV file."""
        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                province_id = int(row["province_id"])
                nearby = row["nearby_provinces"].strip()
                
                if nearby:
                    nearby_ids = [int(id_str) for id_str in nearby.split(",")]
                else:
                    nearby_ids = []
                
                province = self.get_province_by_id(province_id)
                if province:
                    province["nearby_provinces"] = nearby_ids
    
    def get_all_provinces(self):
        """Return a list of all loaded provinces."""
        # Return a copy to prevent callers from accidentally modifying internal state.
        return list(self.provinces)

    def get_province_by_id(self, province_id):
        """Return the province dict with the given id, or None if not found."""
        return self._province_index.get(province_id)

    def get_bbox(self, province=None):
        """Return the bounding box for the given province or the whole map.

        Returns (min_x, min_y, max_x, max_y) or None if there are no coordinates.
        """
        pts = []

        if province is None:
            for prov in self.provinces:
                for poly in prov["polygons"]:
                    pts.extend(poly)
        else:
            for poly in province["polygons"]:
                pts.extend(poly)

        if not pts:
            return None

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def get_province_at_point(self, x: float, y: float):
        """Return the province that contains the given point (x, y), or None if no province contains it."""
        point = Point(x, y)
        for province in self.provinces:
            for polygon_coords in province["polygons"]:
                polygon = Polygon(polygon_coords)
                if polygon.contains(point):
                    return province
        return None

    def get_nearby_provinces(self, province_id):
        """Return a list of nearby province dicts for the given province ID."""
        province = self.get_province_by_id(province_id)
        if not province:
            return []
        
        nearby = []
        for nearby_id in province.get("nearby_provinces", []):
            nearby_province = self.get_province_by_id(nearby_id)
            if nearby_province:
                nearby.append(nearby_province)
        
        return nearby