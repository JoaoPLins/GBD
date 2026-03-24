import pygame
from pathlib import Path
from nations import NationManager

from gameMap import Map
from gameGraphics import Graphics


class Game:
    def __init__(self, width: int = 800, height: int = 600, title: str = "GBD"):
        pygame.init()

        # Window/screen setup
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption(title)

        # Load game data
        self.map = Map(0, 0)
        self.running = True
        geojson_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "provinces.geojson"
        nearby_csv_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "nearby_provinces.csv"
        self.map.load_provinces(str(geojson_path), str(nearby_csv_path))
        self.nation_manager = NationManager()
        nations_json_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "nations.json"
        self.nation_manager.load_from_json(str(nations_json_path))

        # Rendering helper
        art_path = Path(__file__).resolve().parent.parent / "Art"
        self.graphics = Graphics(self, self.screen, str(art_path))

        # Center on Montevideo at startup
        self.graphics.center_on_province_id(1)

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
                    province = self.map.get_province_at_point(wx, wy)
                    if province:
                        print(f"Clicked on province {province['id']}")
                    else:
                        print("Clicked outside any province")
        return True
    
    
    def run(self) -> None:
        clock = pygame.time.Clock()
        

        while self.running:
            self.event_handler()

            self.key_handler()

            self.graphics.draw()
            
            clock.tick(60)

        pygame.quit()

    
    

