import pygame
from typing import Optional, Tuple


class Graphics:
    def __init__(self, game, screen):
        self.game = game
        self.screen = screen

        # Camera state (world -> screen transform)
        self.camera_origin: Tuple[float, float] = (0.0, 0.0)
        self.camera_scale: float = 1.0

    def reset_camera(self) -> None:
        """Reset the camera to fit the entire map."""
        bbox = self.game.map.get_bbox()
        if bbox is None:
            return
        self._set_camera_from_bbox(bbox)

    def _set_camera_from_bbox(self, bbox: Tuple[float, float, float, float]) -> None:
        min_x, min_y, max_x, max_y = bbox
        width = max_x - min_x
        height = max_y - min_y

        screen_w, screen_h = self.screen.get_size()

        if width <= 0 or height <= 0:
            self.camera_scale = 1.0
        else:
            # Leave a bit of padding to avoid clipping to the screen edges.
            padding = 0.85
            self.camera_scale = min(screen_w / width, screen_h / height) * padding

        # Center the camera on the bounding box center
        self.camera_origin = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

    def center_on_province_id(self, province_id: int) -> None:
        """Center the view on the given province ID."""
        province = self.game.map.get_province_by_id(province_id)
        if province is None:
            self.reset_camera()
            return

        bbox = self.game.map.get_bbox(province)
        if bbox is None:
            return

        self._set_camera_from_bbox(bbox)

    def move(self, dx: float, dy: float) -> None:
        """Move (pan) the viewport by (dx, dy) in world coordinates."""
        ox, oy = self.camera_origin
        self.camera_origin = (ox + dx, oy + dy)

    def zoom(self, factor: float) -> None:
        """Zoom the camera by a factor (e.g., 1.1 to zoom in, 0.9 to zoom out)."""
        self.camera_scale *= factor
        # Clamp to reasonable bounds
        self.camera_scale = max(0.1, min(100.0, self.camera_scale))

    def world_to_screen(self, x: float, y: float) -> Tuple[int, int]:
        """Transform a point in world coordinates to screen coordinates."""
        screen_w, screen_h = self.screen.get_size()
        ox, oy = self.camera_origin

        sx = (x - ox) * self.camera_scale + screen_w * 0.5
        sy = screen_h * 0.5 - (y - oy) * self.camera_scale

        return int(sx), int(sy)

    def draw(self):
        # Clear the screen with a background color (e.g., white)
        self.screen.fill((255, 255, 255))

        # Draw provinces transformed into screen space
        for province in self.game.map.get_all_provinces():
            for polygon in province["polygons"]:
                transformed = [self.world_to_screen(x, y) for x, y in polygon]
                pygame.draw.polygon(self.screen, (200, 200, 200), transformed)

        # Update the display
        pygame.display.flip()
