import pygame
from pathlib import Path
from nations import NationManager

from units import create_logistics_unit, create_unit, load_starting_trains, load_starting_units
from simulation import Simulation

from gameMap import Map
from gameGraphics import Graphics


class Game:
    def __init__(self, width: int = 800, height: int = 600, nation: str = "URU") -> None:
        pygame.init()

        # Window/screen setup
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("GBD")
        print("Game initialized with screen size:", width, "x", height)
        # Load game data
        
        self.map = Map(0, 0)
        print("Map object created.")
        self.running = True
        self.nation = nation
        geojson_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "provinces.geojson"
        nearby_csv_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "nearby_provinces.csv"
        centers_csv_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "province_centers.csv"
        pop_csv_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "pop.csv"
        rails_csv_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "starting_rails.csv"
        print("loading provinces")
        self.map.load_provinces(str(geojson_path), str(nearby_csv_path), str(centers_csv_path))
        print("provinces loaded, loading population")
        self.map.load_population(str(pop_csv_path))
        if rails_csv_path.exists():
            self.map.load_rails(str(rails_csv_path))
            print(f"rails loaded: {len(self.map.get_all_rails())}")
        else:
            print(f"WARNING: rails file not found at {rails_csv_path}")
        print("population loaded, loading nations")
        self.nation_manager = NationManager()
        nations_json_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "nations.json"
        self.nation_manager.load_from_json(str(nations_json_path))
        print("setting capitals from nations")
        self.map.set_capitals_from_nations(self.nation_manager)
        print("initializing startup province data (pre-units)")
        self.map.initialize_startup_provinces()
        

        # Load units and armies
        print("loading starting units")
        self.armies = load_starting_units()
        self.trains = load_starting_trains()
        print(f"starting trains loaded: {len(self.trains)}")
        added_armybases = self.map.initialize_startup_unit_province_data(self.armies)
        print(f"startup province init complete ({added_armybases} army bases added)")
        

        # Simulation runs in its own thread (independent from render FPS)
        self.simulation = Simulation(
            nation_manager=self.nation_manager,
            game_map=self.map,
            armies=self.armies,
            trains=self.trains,
            tick_seconds=1.0,
            speed_multiplier=1.0,
        )
        self.simulation.pause()

        # Rendering helper
        art_path = Path(__file__).resolve().parent.parent / "Art"
        self.graphics = Graphics(self, self.screen, str(art_path))

        # Center on Montevideo at startup
        self.graphics.center_on_province_id(1)
        self.unit_selected = 0
        self.unit_multi_selected = []
        self.train_selected = None
        self.province_selected = 0
        self._drag_select_active = False
        self._drag_select_moved = False
        self._drag_select_start = (0, 0)
        self._drag_select_current = (0, 0)

    @staticmethod
    def _make_screen_rect(start: tuple[int, int], end: tuple[int, int]) -> pygame.Rect:
        left = min(start[0], end[0])
        top = min(start[1], end[1])
        width = abs(end[0] - start[0])
        height = abs(end[1] - start[1])
        return pygame.Rect(left, top, width, height)

    def _find_train_by_id(self, train_id):
        if train_id is None:
            return None
        return self.trains.get(str(train_id))

    def _get_next_army_id(self):
        highest_id = 0
        for army_id in self.armies.keys():
            try:
                numeric_id = int(army_id)
            except (TypeError, ValueError):
                continue
            if numeric_id > highest_id:
                highest_id = numeric_id
        return highest_id + 1

    def _get_player_army_id(self):
        for army_id, army in self.armies.items():
            if getattr(army, "nation", None) == self.nation:
                return army_id

        for army_id, army in self.armies.items():
            if self.graphics._is_player_side_nation(getattr(army, "nation", None)):
                return army_id

        return self._get_next_army_id()

    def create_unit_from_selected_province(self):
        """Create a new infantry unit from the selected province recruits."""
        if not self.province_selected:
            return None, "Select a province first."

        province = self.map.get_province_by_id(self.province_selected)
        province_obj = self.map.get_province_object_by_id(self.province_selected)
        if province is None or province_obj is None:
            return None, "Selected province is unavailable."

        if not self.graphics.can_create_unit_in_selected_province(province, province_obj):
            return None, "This province cannot create a unit right now."

        recruit_count = min(100, int(getattr(province_obj, "province_recruits", 0)))
        if recruit_count <= 0:
            return None, "No recruits available in this province."

        army_id = self._get_player_army_id()
        unit = self.create_unit(
            name=f"Recruit Unit {self.province_selected}",
            nation=self.nation,
            location=self.province_selected,
            home=self.province_selected,
            army=army_id,
            soldiers=recruit_count,
            type_of_unit=1,
            leader_id=0,
            reserve=0,
            logistics=0,
            suply=10,
            status=1,
        )

        province_obj.add_soldiers(recruit_count)
        if unit.id not in province_obj.units_in_here:
            province_obj.units_in_here.append(unit.id)
        if unit.id not in province_obj.units_from_here:
            province_obj.units_from_here.append(unit.id)

        self.unit_selected = unit.id
        self.unit_multi_selected = [unit.id]
        self.train_selected = None
        return unit, f"Created unit {unit.id}."

    def create_logistics_unit_from_selected_province(self):
        """Create a new logistics unit from the selected province recruits."""
        if not self.province_selected:
            return None, "Select a province first."

        province = self.map.get_province_by_id(self.province_selected)
        province_obj = self.map.get_province_object_by_id(self.province_selected)
        if province is None or province_obj is None:
            return None, "Selected province is unavailable."

        if not self.graphics.can_create_unit_in_selected_province(province, province_obj):
            return None, "This province cannot create a unit right now."

        recruit_count = min(100, int(getattr(province_obj, "province_recruits", 0)))
        if recruit_count <= 0:
            return None, "No recruits available in this province."

        army_id = self._get_player_army_id()
        unit = self.create_logistics_unit(
            nation=self.nation,
            location=self.province_selected,
            home=self.province_selected,
            army=army_id,
            name=f"Logistics Unit {self.province_selected}",
            soldiers=recruit_count,
            leader_id=0,
            reserve=0,
            logistics=max(50, recruit_count // 2),
            suply=10,
            status=1,
        )

        province_obj.add_soldiers(recruit_count)
        if unit.id not in province_obj.units_in_here:
            province_obj.units_in_here.append(unit.id)
        if unit.id not in province_obj.units_from_here:
            province_obj.units_from_here.append(unit.id)

        self.unit_selected = unit.id
        self.unit_multi_selected = [unit.id]
        self.train_selected = None
        return unit, f"Created logistics unit {unit.id}."

    def create_unit(
        self,
        *,
        name,
        nation,
        location,
        home,
        army,
        soldiers,
        type_of_unit,
        leader_id,
        reserve,
        logistics,
        suply,
        status=1,
        unit_id=None,
    ):
        """Create a new unit and store it in the selected army."""
        return create_unit(
            self.armies,
            name=name,
            nation=nation,
            location=location,
            home=home,
            army=army,
            soldiers=soldiers,
            type_of_unit=type_of_unit,
            leader_id=leader_id,
            reserve=reserve,
            logistics=logistics,
            suply=suply,
            status=status,
            unit_id=unit_id,
        )

    def create_logistics_unit(
        self,
        *,
        nation,
        location,
        home,
        army,
        name="Logistics Unit",
        soldiers=0,
        leader_id=0,
        reserve=0,
        logistics=10,
        suply=0,
        status=1,
        unit_id=None,
    ):
        """Create a logistics unit using the normal unit storage flow."""
        return create_logistics_unit(
            self.armies,
            nation=nation,
            location=location,
            home=home,
            army=army,
            name=name,
            soldiers=soldiers,
            leader_id=leader_id,
            reserve=reserve,
            logistics=logistics,
            suply=suply,
            status=status,
            unit_id=unit_id,
        )

    def toggle_selected_province_logistics_hub(self):
        """Toggle logistics hub state for selected province when player-side controlled."""
        if not self.province_selected:
            return False, "Select a province first."

        province = self.map.get_province_by_id(self.province_selected)
        province_obj = self.map.get_province_object_by_id(self.province_selected)
        if province is None or province_obj is None:
            return False, "Selected province is unavailable."

        if not self.graphics.can_toggle_logistic_hub_in_selected_province(province, province_obj):
            return False, "Only player-side provinces can change logistic hub state."

        is_hub = bool(getattr(province_obj, "logistic_hub", False))
        new_state = not is_hub
        province_obj.set_logistic_hub(new_state)

        if hasattr(self, "simulation") and self.simulation is not None:
            province_nation = getattr(province_obj, "controller", None) or getattr(province_obj, "owner", None) or self.nation
            self.simulation.set_logistics_hub(province_nation, self.province_selected, new_state)

        state = "enabled" if province_obj.is_logistic_hub() else "disabled"
        return True, f"Logistics hub {state} for province {self.province_selected}."

    def key_handler(self) -> None:
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            self.graphics.move(-20 / max(self.graphics.camera_scale, 0.0001), 0)
        if keys[pygame.K_RIGHT]:
            self.graphics.move(20 / max(self.graphics.camera_scale, 0.0001), 0)
        if keys[pygame.K_UP]:
            self.graphics.move(0, 20 / max(self.graphics.camera_scale, 0.0001))
        if keys[pygame.K_DOWN]:
            self.graphics.move(0, -20 / max(self.graphics.camera_scale, 0.0001))
        if keys[pygame.K_EQUALS] or keys[pygame.K_PLUS]:
            self.graphics.zoom(1.1)
        if keys[pygame.K_MINUS]:
            self.graphics.zoom(0.9)

    def event_handler(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEMOTION:
                if self._drag_select_active and event.buttons and event.buttons[0]:
                    self._drag_select_current = event.pos
                    dx = self._drag_select_current[0] - self._drag_select_start[0]
                    dy = self._drag_select_current[1] - self._drag_select_start[1]
                    if (dx * dx + dy * dy) >= 64:
                        self._drag_select_moved = True
            elif event.type == pygame.MOUSEWHEEL:
                if event.y != 0:
                    self.graphics.scroll_people_overlay(event.y * -3)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    mx, my = event.pos
                    self._drag_select_active = True
                    self._drag_select_moved = False
                    self._drag_select_start = (mx, my)
                    self._drag_select_current = (mx, my)

                    if self.graphics.handle_people_ui_click(mx, my):
                        self._drag_select_active = False
                        continue

                    if self.graphics.is_province_logistics_hub_checkbox_point(mx, my):
                        changed, message = self.toggle_selected_province_logistics_hub()
                        print(message)
                        self._drag_select_active = False
                        continue

                    if self.graphics.is_province_create_unit_panel_point(mx, my):
                        created_unit, message = self.create_unit_from_selected_province()
                        print(message)
                        self._drag_select_active = False
                        continue

                    if self.graphics.is_province_create_logistics_panel_point(mx, my):
                        created_unit, message = self.create_logistics_unit_from_selected_province()
                        print(message)
                        self._drag_select_active = False
                        continue

                    if self.train_selected is not None:
                        selected_train = self._find_train_by_id(self.train_selected)
                        can_edit_train_status = self.graphics.can_edit_train_status(selected_train)
                        if can_edit_train_status:
                            status_code = self.graphics.get_unit_status_option_at_point(mx, my)
                            if status_code is not None:
                                possible_status_fn = getattr(selected_train, "return_possible_status", None)
                                if (
                                    selected_train is not None
                                    and callable(possible_status_fn)
                                    and status_code in possible_status_fn()
                                ):
                                    selected_train.update_status(status_code)
                                    self.graphics._unit_status_dropdown_open = False
                                    status_getter = getattr(selected_train, "get_status", None)
                                    applied_status = status_getter() if callable(status_getter) else getattr(selected_train, "status", status_code)
                                    print(f"Set train {selected_train.id} status to {applied_status}")
                                self._drag_select_active = False
                                continue

                            if self.graphics._unit_status_combobox_rect and self.graphics._unit_status_combobox_rect.collidepoint(mx, my):
                                self._drag_select_active = False
                                self.graphics.toggle_unit_status_dropdown()
                                continue

                            if self.graphics.is_unit_status_panel_point(mx, my):
                                self._drag_select_active = False
                                continue
                        else:
                            self.graphics._unit_status_dropdown_open = False

                    if self.unit_selected != 0:
                        selected_unit = self.graphics.get_unit_by_id(self.unit_selected)
                        can_edit_status = self.graphics.can_edit_unit_status(selected_unit)
                        if can_edit_status:
                            can_edit_target_size = (
                                selected_unit is not None
                                and getattr(selected_unit, "location", None) == getattr(selected_unit, "home", None)
                            )
                            if can_edit_target_size:
                                if self.graphics.is_unit_target_size_panel_point(mx, my):
                                    self._drag_select_active = False
                                    self.graphics.begin_unit_target_size_input(selected_unit)
                                    continue
                                else:
                                    self.graphics.end_unit_target_size_input()
                            else:
                                self.graphics.end_unit_target_size_input()

                            if self.graphics.is_unit_target_size_panel_point(mx, my):
                                self._drag_select_active = False
                                continue

                            status_code = self.graphics.get_unit_status_option_at_point(mx, my)
                            if status_code is not None:
                                if selected_unit is not None and status_code in selected_unit.possible_status():
                                    selected_unit.update_status(status_code)
                                    self.graphics._unit_status_dropdown_open = False
                                    print(f"Set unit {selected_unit.id} status to {selected_unit.return_status()}")
                                self._drag_select_active = False
                                continue

                            if self.graphics._unit_status_combobox_rect and self.graphics._unit_status_combobox_rect.collidepoint(mx, my):
                                self._drag_select_active = False
                                self.graphics.toggle_unit_status_dropdown()
                                continue

                            if self.graphics.is_unit_status_panel_point(mx, my):
                                self._drag_select_active = False
                                continue
                        else:
                            self.graphics._unit_status_dropdown_open = False
                            self.graphics.end_unit_target_size_input()

                    wx, wy = self.graphics.screen_to_world(mx, my)

                    # Check train clicks first.
                    train = self.graphics.get_train_at_point(wx, wy)
                    if train is not None:
                        self.train_selected = str(train.id)
                        self.unit_selected = 0
                        self.unit_multi_selected = []
                        self.province_selected = getattr(train, "location", 0)
                        self.graphics.close_people_overlay()
                        self.graphics._unit_status_dropdown_open = False
                        self.graphics.end_unit_target_size_input()
                        print(f"Clicked on train {train.id} (Nation: {train.nation})")
                        continue

                    # Check for unit clicks first (they're on top)
                    unit = self.graphics.get_unit_at_point(wx, wy)
                    if unit:
                        if unit.id == self.unit_selected:
                            cycled = self.graphics.get_next_visible_unit_in_province(unit.id)
                            if cycled is not None:
                                unit = cycled

                        print(f"Clicked on unit {unit.id} (Army {unit.army}, Nation: {unit.nation})")
                        self.train_selected = None
                        self.unit_selected = unit.id
                        self.unit_multi_selected = [unit.id]
                        self.province_selected = unit.location
                        self.graphics.close_people_overlay()
                        self.graphics._unit_status_dropdown_open = False
                        self.graphics.end_unit_target_size_input()
                    else:
                        # Then check for province clicks
                        province = self.map.get_province_at_point(wx, wy)
                        if province:
                            self.province_selected = province["id"]
                            self.train_selected = None
                            self.unit_selected = 0  # Deselect unit if clicked on a province
                            self.unit_multi_selected = []
                            self.graphics.close_people_overlay()
                            self.graphics._unit_status_dropdown_open = False
                            self.graphics.end_unit_target_size_input()
                            print(f"Clicked on province {province['id']}")
                        else:
                            print("Clicked outside any province or unit")
                            self.train_selected = None
                            self.unit_selected = 0  # Deselect unit if clicked on empty space
                            self.unit_multi_selected = []
                            self.province_selected = 0
                            self.graphics.close_people_overlay()
                            self.graphics._unit_status_dropdown_open = False
                            self.graphics.end_unit_target_size_input()
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1 and self._drag_select_active:
                    self._drag_select_current = event.pos
                    if self._drag_select_moved:
                        selection_rect = self._make_screen_rect(self._drag_select_start, self._drag_select_current)
                        selected_units = self.graphics.get_units_in_screen_rect(selection_rect)

                        if selected_units:
                            selected_ids = [unit.id for unit in selected_units]
                            self.train_selected = None
                            self.unit_multi_selected = selected_ids
                            self.unit_selected = selected_ids[0]
                            self.province_selected = getattr(selected_units[0], "location", 0)
                            self.graphics.close_people_overlay()
                            self.graphics._unit_status_dropdown_open = False
                            self.graphics.end_unit_target_size_input()
                            print(f"Drag-selected {len(selected_ids)} units")
                        else:
                            self.train_selected = None
                            self.unit_multi_selected = []
                            self.unit_selected = 0

                    self._drag_select_active = False
                    self._drag_select_moved = False
                elif event.button == 3:  # Right click
                    if self.train_selected is not None:
                        train = self._find_train_by_id(self.train_selected)
                        if train is None:
                            print("Selected train was not found.")
                            continue

                        mx, my = event.pos
                        wx, wy = self.graphics.screen_to_world(mx, my)
                        province = self.map.get_province_at_point(wx, wy)
                        if province is None:
                            print("Right click on a province to set train destination.")
                            continue

                        path = self.simulation.train_pathing(train.id, province["id"])
                        if path:
                            print(f"Queued train {train.id} movement via rail path: {path}")
                        else:
                            print("No rail path to destination.")
                        continue

                    if self.unit_selected != 0:
                        mx, my = event.pos
                        wx, wy = self.graphics.screen_to_world(mx, my)
                        province = self.map.get_province_at_point(wx, wy)
                        if province:
                            selected_ids = list(getattr(self, "unit_multi_selected", []))
                            if not selected_ids:
                                selected_ids = [self.unit_selected]

                            queued_count = 0
                            blocked_ids = []
                            failed_ids = []

                            for unit_id in selected_ids:
                                unit = self.graphics.get_unit_by_id(unit_id)
                                if unit is None:
                                    failed_ids.append(unit_id)
                                    continue

                                if unit.status in (0, 11, 13):
                                    blocked_ids.append(unit.id)
                                    continue

                                route = self.simulation.pathing(unit.id, province["id"])
                                if route:
                                    queued_count += 1
                                else:
                                    failed_ids.append(unit.id)

                            if queued_count > 0:
                                print(f"Queued movement for {queued_count} unit(s) to province {province['id']}.")
                            if blocked_ids:
                                print(f"Blocked (status): {blocked_ids}")
                            if failed_ids and queued_count == 0:
                                print("No valid route found for selected units.")
                            elif failed_ids:
                                print(f"No route for: {failed_ids}")
                        else:
                            print("Right click on a province to set destination.")
                    else:
                        print("Select a unit first with left click.")
                    
            elif event.type == pygame.KEYDOWN:
                selected_unit = self.graphics.get_unit_by_id(self.unit_selected) if self.unit_selected else None
                if (
                    selected_unit is not None
                    and self.graphics.can_edit_unit_status(selected_unit)
                    and self.graphics.is_unit_target_size_input_active()
                ):
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        ok, message = self.graphics.commit_unit_target_size_input(selected_unit)
                        print(message)
                        if ok:
                            self.graphics.end_unit_target_size_input()
                        continue
                    if event.key == pygame.K_BACKSPACE:
                        self.graphics.backspace_unit_target_size_input()
                        continue
                    if event.key == pygame.K_ESCAPE:
                        self.graphics.end_unit_target_size_input()
                        continue
                    if event.unicode and event.unicode.isdigit():
                        self.graphics.append_unit_target_size_digit(event.unicode)
                        continue

                if event.key == pygame.K_0:
                    self.simulation.set_speed(0.0)
                    print("Simulation speed set to 0.0x")
                elif event.key == pygame.K_1:
                    self.simulation.set_speed(1.0)
                    print("Simulation speed set to 1.0x")
                elif event.key == pygame.K_2:
                    self.simulation.set_speed(2.0)
                    print("Simulation speed set to 2.0x")
                elif event.key == pygame.K_3:
                    self.simulation.set_speed(3.0)
                    print("Simulation speed set to 3.0x")
                elif event.key == pygame.K_4:
                    self.simulation.set_speed(5.0)
                    print("Simulation speed set to 5.0x")
                elif event.key == pygame.K_SPACE:
                    paused = self.simulation.toggle_pause()
                    print(f"Simulation {'paused' if paused else 'resumed'}")
        return True
    
    
    def run(self) -> None:
        clock = pygame.time.Clock()
        self.simulation.start()

        try:
            while self.running:
                self.event_handler()

                self.key_handler()

                self.graphics.draw()

                clock.tick(60)
        finally:
            self.simulation.stop()
            self.simulation.join(timeout=1.0)
            pygame.quit()

    
    

