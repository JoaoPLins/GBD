import pygame
from pathlib import Path
from nations import NationManager

from units import load_starting_units
from simulation import Simulation

from gameMap import Map
from gameGraphics import Graphics


class Game:
    def __init__(self, width: int = 800, height: int = 600, title: str = "GBD"):
        pygame.init()

        # Window/screen setup
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption(title)
        print("Game initialized with screen size:", width, "x", height)
        # Load game data
        
        self.map = Map(0, 0)
        print("Map object created.")
        self.running = True
        geojson_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "provinces.geojson"
        nearby_csv_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "nearby_provinces.csv"
        centers_csv_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "province_centers.csv"
        pop_csv_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "pop.csv"
        print("loading provinces")
        self.map.load_provinces(str(geojson_path), str(nearby_csv_path), str(centers_csv_path))
        print("provinces loaded, loading population")
        self.map.load_population(str(pop_csv_path))
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
        added_armybases = self.map.initialize_startup_unit_province_data(self.armies)
        print(f"startup province init complete ({added_armybases} army bases added)")
        

        # Simulation runs in its own thread (independent from render FPS)
        self.simulation = Simulation(
            nation_manager=self.nation_manager,
            game_map=self.map,
            armies=self.armies,
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
        self.province_selected = 0

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
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    mx, my = event.pos
                    wx, wy = self.graphics.screen_to_world(mx, my)
                    # Check for unit clicks first (they're on top)
                    unit = self.graphics.get_unit_at_point(wx, wy)
                    if unit:
                        print(f"Clicked on unit {unit.id} (Army {unit.army}, Nation: {unit.nation})")
                        self.unit_selected = unit.id
                        self.province_selected = unit.location
                    else:
                        # Then check for province clicks
                        province = self.map.get_province_at_point(wx, wy)
                        if province:
                            self.province_selected = province["id"]
                            self.unit_selected = 0  # Deselect unit if clicked on a province
                            print(f"Clicked on province {province['id']}")
                        else:
                            print("Clicked outside any province or unit")
                            self.unit_selected = 0  # Deselect unit if clicked on empty space
                            self.province_selected = 0
                elif event.button == 3:  # Right click
                    if self.unit_selected != 0:
                        mx, my = event.pos
                        wx, wy = self.graphics.screen_to_world(mx, my)
                        province = self.map.get_province_at_point(wx, wy)
                        if province:
                            route = self.simulation.pathing(self.unit_selected, province["id"])
                            if route:
                                print(f"Queued movement for {self.unit_selected}: {route}")
                            else:
                                print("No valid route found.")
                        else:
                            print("Right click on a province to set destination.")
                    else:
                        print("Select a unit first with left click.")
                    
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    self.simulation.set_speed(0.5)
                    print("Simulation speed set to 0.5x")
                elif event.key == pygame.K_2:
                    self.simulation.set_speed(1.0)
                    print("Simulation speed set to 1.0x")
                elif event.key == pygame.K_3:
                    self.simulation.set_speed(2.0)
                    print("Simulation speed set to 2.0x")
                elif event.key == pygame.K_SPACE:
                    paused = self.simulation.toggle_pause()
                    print(f"Simulation {'paused' if paused else 'resumed'}")
        return True
    
    
    def run(self) -> None:
        clock = pygame.time.Clock()
        self.simulation.start()
        

        while self.running:
            self.event_handler()

            self.key_handler()

            self.graphics.draw()
            
            clock.tick(60)

        self.simulation.stop()
        self.simulation.join(timeout=1.0)
        pygame.quit()

    
    

