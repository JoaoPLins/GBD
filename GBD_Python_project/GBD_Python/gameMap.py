import json
import csv
from shapely.geometry import Point, Polygon
from provinces import Province

class Map():
    def __init__(self, center_x, center_y):
        self.center_x = center_x
        self.center_y = center_y
        self.provinces = []
        self.provinceObjects = []
        self._province_index = {}
        self._province_objects_index = {}

    def load_provinces(self, geojson_file, nearby_csv_file=None, centers_csv_file=None):
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
                "name": props.get("p_name") or props.get("name") or f"Province {props['id']}",
                "polygons": polygons,
                "terrain": props["terrain"],
                "is_water": props["is_water"],
                "owner": props["owner"],
                "controler": props["controler"],
                "nearby_provinces": [],
                "center": None,
            }

            self.provinces.append(province)
            self._province_index[province["id"]] = province

            prov_obj = Province(
                province_id=province["id"],
                name=province["name"],
                owner=province["owner"],
                controller=province["controler"],
                iswater=province["is_water"],
                terrain=province["terrain"],
            )
            self.provinceObjects.append(prov_obj)
            self._province_objects_index[prov_obj.province_id] = prov_obj
        
        # Load nearby provinces if CSV file is provided
        if nearby_csv_file:
            self._load_nearby_from_csv(nearby_csv_file)

        # Load precomputed province centers if CSV file is provided
        if centers_csv_file:
            self._load_centers_from_csv(centers_csv_file)
    
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

    def _load_centers_from_csv(self, csv_file):
        """Load province center coordinates from a CSV file."""
        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                province_id = int(row["province_id"])
                center_x = float(row["center_x"])
                center_y = float(row["center_y"])

                province = self.get_province_by_id(province_id)
                if province:
                    province["center"] = (center_x, center_y)
    
    # FAILSAFE SYSTEM FOR PROVINCE CENTERS IN CASE CSV DATA IS MISSING OR INCOMPLETE
    
    def _calculate_centroid(self, polygon):
        """Calculate centroid by averaging polygon vertices."""
        if not polygon:
            return 0.0, 0.0

        x_coords = [p[0] for p in polygon]
        y_coords = [p[1] for p in polygon]
        return sum(x_coords) / len(x_coords), sum(y_coords) / len(y_coords)

    def _calculate_province_center(self, province):
        """Fallback center calculation if CSV data is missing."""
        print(f"WARNING: No precomputed center for province {province['id']}. Calculating centroid as fallback.")
        polygons = province.get("polygons", [])
        if not polygons:
            return 0.0, 0.0

        centroids = [self._calculate_centroid(poly) for poly in polygons]
        avg_x = sum(c[0] for c in centroids) / len(centroids)
        avg_y = sum(c[1] for c in centroids) / len(centroids)
        return avg_x, avg_y
    
    # ------------------------------------------------------------------------------------------------#
    
    def get_province_center(self, province_or_id):
        """Return province center (loaded from CSV when available)."""
        if isinstance(province_or_id, dict):
            province = province_or_id
        else:
            province = self.get_province_by_id(province_or_id)

        if not province:
            return 0.0, 0.0

        center = province.get("center")
        if center is not None:
            return center

        center = self._calculate_province_center(province)
        province["center"] = center
        return center
    
    def get_all_provinces(self):
        """Return a list of all loaded provinces."""
        # Return a copy to prevent callers from accidentally modifying internal state.
        return list(self.provinces)

    def get_province_by_id(self, province_id):
        """Return the province dict with the given id, or None if not found."""
        return self._province_index.get(province_id)

    def get_bbox(self, province=None):
        """Return the bounding box for the given province or the whole map.

        Returns (min_x, min_y, max_x, max_y) or None if there are no coordinates. (FOR ZOOMING PURPOSES)
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

    def get_province_object_by_id(self, province_id):
        """Return the Province object with the given id, or None if not found."""
        return self._province_objects_index.get(province_id)

    def load_population(self, csv_file):
        """Load population values from a CSV file (columns: id, population) into Province objects."""
        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                province_id = int(row["id"])
                population = int(row["population"])
                prov_obj = self._province_objects_index.get(province_id)
                if prov_obj:
                    prov_obj.define_population(population)

    def set_capitals_from_nations(self, nation_manager):
        """Mark province objects as capitals based on each nation's capital_id."""
        for nation in nation_manager.get_all_nations():
            capital_id = nation.return_capital_id_int()
            if capital_id is None:
                continue
            prov_obj = self._province_objects_index.get(capital_id)
            if prov_obj:
                prov_obj.set_capital()

    def initialize_startup_provinces(self):
        """Startup-only province setup that must run before units are loaded."""
        for prov_obj in self.provinceObjects:
            prov_obj.load_extra_data()

    def run_daily_province_simulation(self):
        """Run one daily simulation step for every province object."""
        for prov_obj in self.provinceObjects:
            prov_obj.sim_update()

    def initialize_startup_unit_province_data(self, armies):
        """Startup-only initialization for provinces based on loaded units.

        This should only run during game loading. It:
        - assigns unit ids to Province.units_in_here and Province.units_from_here
        - ensures each used province has at least one army base (building type 5)

        Returns the number of army bases that were added.
        """
        added_count = 0
        checked_ids = set()

        # Rebuild province-unit links from scratch for startup state.
        for prov_obj in self.provinceObjects:
            prov_obj.units_in_here = []
            prov_obj.units_from_here = []

        for army in armies.values():
            for unit in army.units.values():
                location_obj = self.get_province_object_by_id(unit.location)
                if location_obj:
                    location_obj.units_in_here.append(unit.id)

                home_obj = self.get_province_object_by_id(unit.home)
                if home_obj:
                    home_obj.units_from_here.append(unit.id)
                    home_obj.add_soldiers(unit.soldiers)    

                for province_id in (unit.location, unit.home):
                    if province_id in checked_ids:
                        continue
                    checked_ids.add(province_id)

                    prov_obj = self.get_province_object_by_id(province_id)
                    if not prov_obj:
                        continue

                    has_armybase = any(b.building_type == 5 for b in prov_obj.buildings)
                    if has_armybase:
                        continue

                    next_slot = len(prov_obj.buildings)
                    prov_obj.add_building(next_slot, 5)
                    prov_obj.calculate_max_suply()
                    added_count += 1

        return added_count

    def ensure_armybases_for_units(self, armies):
        """Compatibility wrapper. Prefer initialize_startup_unit_province_data during load."""
        return self.initialize_startup_unit_province_data(armies)