import pygame
from pathlib import Path

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
        geojson_path = Path(__file__).resolve().parent.parent / "QgizFiles" / "provinces.geojson"
        self.map.load_provinces(str(geojson_path))

        # Rendering helper
        self.graphics = Graphics(self, self.screen)

    def run(self) -> None:
        clock = pygame.time.Clock()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            self.graphics.draw()
            clock.tick(60)

        pygame.quit()


