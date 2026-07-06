import json
import csv
from collections import deque
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
        self.rails = Rails()

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
                "is_coastal": props["is_costal"],
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
                iscoastal=province["is_coastal"],
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

    def load_rails(self, csv_file):
        """Load rail network and project rail presence into Province objects."""
        self.rails.load_rails(csv_file)

        # Reset rail flags before applying loaded data.
        for prov_obj in self.provinceObjects:
            prov_obj.hasRailroad = False
            prov_obj.railid = []

        for rail in self.rails.get_all_rails():
            rail_id = rail["id"]
            for province_id in rail.get("points", []):
                prov_obj = self.get_province_object_by_id(province_id)
                if not prov_obj:
                    continue
                prov_obj.hasRailroad = True
                if rail_id not in prov_obj.railid:
                    prov_obj.railid.append(rail_id)

    def get_all_rails(self):
        return self.rails.get_all_rails()

    def get_rail_by_id(self, rail_id):
        return self.rails.get_rail_by_id(rail_id)

    def get_rails_in_province(self, province_id):
        return self.rails.get_rails_in_province(province_id)

    def get_rail_point_health(self, rail_id):
        return self.rails.get_rail_point_health(rail_id)

    def get_rail_neighbors(self, province_id):
        """Return adjacent provinces reachable by rail from a province."""
        neighbors = set()
        for rail in self.get_rails_in_province(province_id):
            points = rail.get("points", [])
            for idx, pid in enumerate(points):
                if pid != province_id:
                    continue
                if idx > 0:
                    neighbors.add(points[idx - 1])
                if idx + 1 < len(points):
                    neighbors.add(points[idx + 1])
        return list(neighbors)

    def find_rail_path(self, start_province_id, destination_province_id):
        """Find shortest rail-only path between provinces using BFS."""
        if start_province_id == destination_province_id:
            return [start_province_id]

        visited = {start_province_id}
        parent = {}
        queue = deque([start_province_id])

        while queue:
            current = queue.popleft()
            for neighbor in self.get_rail_neighbors(current):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                parent[neighbor] = current
                if neighbor == destination_province_id:
                    path = [destination_province_id]
                    while path[-1] != start_province_id:
                        path.append(parent[path[-1]])
                    path.reverse()
                    return path
                queue.append(neighbor)

        return []
    

class Rails: 
    def __init__(self):
        self.rails = []
        self._rail_index = {}
        self._province_rail_index = {}

    @staticmethod
    def _to_int(value):
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None

    @staticmethod
    def _parse_csv_int_list(value):
        if value is None:
            return []

        out = []
        for raw in str(value).split(","):
            item = raw.strip()
            if not item:
                continue
            try:
                out.append(int(item))
            except ValueError:
                continue
        return out

    def load_rails(self, csv_file):
        """Load rail data from starting_rails-style CSV.

        Expected columns:
        - Rail_ID
        - Rail Junctions
        - P1..Pn (province path points)
        """
        self.rails = []
        self._rail_index = {}
        self._province_rail_index = {}

        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                normalized_row = {str(k).strip(): v for k, v in row.items()}

                # Support both new and legacy naming schemes.
                rail_id = self._to_int(
                    normalized_row.get("Rail_ID")
                    or normalized_row.get("rail_id")
                    or normalized_row.get("id")
                )
                if rail_id is None:
                    continue

                junctions = self._parse_csv_int_list(
                    normalized_row.get("Rail Junctions")
                    or normalized_row.get("Rail Junctions ")
                    or normalized_row.get("rail_junctions")
                    or normalized_row.get("junctions")
                )

                point_columns = []
                for col_name in normalized_row.keys():
                    compact = col_name.strip().lower().replace(" ", "")
                    if not compact.startswith("p"):
                        continue
                    suffix = compact[1:]
                    if suffix.isdigit():
                        point_columns.append((int(suffix), col_name))

                point_columns.sort(key=lambda item: item[0])
                points = []
                for _, col_name in point_columns:
                    province_id = self._to_int(normalized_row.get(col_name))
                    if province_id is not None:
                        points.append(province_id)

                # Legacy fallback: one province per row.
                if not points:
                    single_province = self._to_int(normalized_row.get("province_id"))
                    if single_province is not None:
                        points = [single_province]

                if not points:
                    continue

                rail = {
                    "id": rail_id,
                    "junctions": junctions,
                    "points": points,
                    # Track health per path point (same index as points list).
                    "point_health": [100 for _ in points],
                }

                self.rails.append(rail)
                self._rail_index[rail_id] = rail

                for province_id in points:
                    self._province_rail_index.setdefault(province_id, []).append(rail_id)

    def get_all_rails(self):
        return list(self.rails)

    def get_rail_by_id(self, rail_id):
        """Return the rail dict with the given id, or None if not found."""
        return self._rail_index.get(rail_id)

    def get_rails_in_province(self, province_id):
        """Return a list of rails in the given province."""
        rail_ids = self._province_rail_index.get(province_id, [])
        return [self._rail_index[rail_id] for rail_id in rail_ids if rail_id in self._rail_index]

    def get_rail_point_health(self, rail_id):
        """Return health values for each rail point in a line."""
        rail = self.get_rail_by_id(rail_id)
        if not rail:
            return []
        return list(rail.get("point_health", []))