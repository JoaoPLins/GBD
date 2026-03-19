import pygame


class Graphics:
    def __init__(self, game, screen):
        self.game = game
        self.screen = screen

    def draw(self):
        # Clear the screen with a background color (e.g., white)
        self.screen.fill((255, 255, 255))

        # Draw provinces
        for province in self.game.map.get_all_provinces():
            for polygon in province["polygons"]:
                pygame.draw.polygon(self.screen, (200, 200, 200), polygon)

        # Update the display
        pygame.display.flip()
