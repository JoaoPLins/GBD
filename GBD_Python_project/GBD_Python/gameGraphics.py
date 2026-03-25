import pygame
from typing import Optional, Tuple, Dict
from pathlib import Path


class Graphics:
    def __init__(self, game, screen, art_path: str = "Art"):
        self.game = game
        self.screen = screen
        self.art_path = Path(art_path)

        # Camera state (world -> screen transform)
        self.camera_origin: Tuple[float, float] = (0.0, 0.0)
        self.camera_scale: float = 1.0
        
        # Image cache
        self.images: Dict[str, pygame.Surface] = {}
        self.base_map_image: Optional[pygame.Surface] = None
        self.base_map_world_origin: Tuple[float, float] = (0.0, 0.0)
        self.base_map_pixels_per_unit: float = 1.0
        self._base_map_screen_cache: Optional[pygame.Surface] = None
        self._base_map_cache_key: Optional[Tuple[float, float, float, int, int]] = None
        
        # Load base map if available
        self._load_base_map()

    def _load_base_map(self) -> None:
        """Load the base map image from Art/baseMap/provincemapbase.png"""
        print(f"Art path: {self.art_path}")
        print(f"Art path exists: {self.art_path.exists()}")
        
        base_map_path = self.art_path / "baseMap" / "provincemapbase.png"
        
        print(f"Looking for base map at: {base_map_path}")
        print(f"Full path: {base_map_path.resolve()}")
        
        if base_map_path.exists():
            try:
                self.base_map_image = pygame.image.load(str(base_map_path))
                print(f"✓ Loaded base map: {base_map_path}")
                print(f"  Base map size: {self.base_map_image.get_size()}")
                print(f"  Screen size: {self.screen.get_size()}")
                print("  Base map world mapping: ix=x, iy=-y")
            except Exception as e:
                print(f"✗ Failed to load base map: {e}")
        else:
            print(f"✗ Base map not found at: {base_map_path}")
            # List what's in the Art directory
            if self.art_path.exists():
                print(f"Contents of {self.art_path}:")
                for item in self.art_path.iterdir():
                    print(f"  - {item.name}")

    def _draw_base_map(self) -> None:
        """Draw only the visible world-aligned crop of the base map."""
        if self.base_map_image is None:
            return

        screen_w, screen_h = self.screen.get_size()
        ox, oy = self.camera_origin
        cache_key = (round(ox, 3), round(oy, 3), round(self.camera_scale, 5), screen_w, screen_h)

        if self._base_map_screen_cache is not None and self._base_map_cache_key == cache_key:
            self.screen.blit(self._base_map_screen_cache, (0, 0))
            return

        bx, by = self.base_map_world_origin
        ppu = self.base_map_pixels_per_unit
        if ppu <= 0:
            return

        # Visible world rectangle.
        w_left, w_top = self.screen_to_world(0, 0)
        w_right, w_bottom = self.screen_to_world(screen_w, screen_h)

        min_wx = min(w_left, w_right)
        max_wx = max(w_left, w_right)
        min_wy = min(w_top, w_bottom)
        max_wy = max(w_top, w_bottom)

        # World -> image mapping: ix = (x - bx) * ppu, iy = (by - y) * ppu
        ix0 = int((min_wx - bx) * ppu)
        ix1 = int((max_wx - bx) * ppu)
        iy0 = int((by - max_wy) * ppu)
        iy1 = int((by - min_wy) * ppu)

        img_w, img_h = self.base_map_image.get_size()
        crop_left = max(0, min(ix0, ix1))
        crop_top = max(0, min(iy0, iy1))
        crop_right = min(img_w, max(ix0, ix1))
        crop_bottom = min(img_h, max(iy0, iy1))

        if crop_right <= crop_left or crop_bottom <= crop_top:
            return

        crop_rect = pygame.Rect(crop_left, crop_top, crop_right - crop_left, crop_bottom - crop_top)
        crop_surface = self.base_map_image.subsurface(crop_rect)

        # Convert crop bounds back to world to place the image correctly on screen.
        world_left = bx + crop_left / ppu
        world_right = bx + crop_right / ppu
        world_top = by - crop_top / ppu
        world_bottom = by - crop_bottom / ppu

        s_left, s_top = self.world_to_screen(world_left, world_top)
        s_right, s_bottom = self.world_to_screen(world_right, world_bottom)

        dest_x = min(s_left, s_right)
        dest_y = min(s_top, s_bottom)
        dest_w = abs(s_right - s_left)
        dest_h = abs(s_bottom - s_top)
        if dest_w <= 0 or dest_h <= 0:
            return

        scaled = pygame.transform.scale(crop_surface, (dest_w, dest_h))
        cached_surface = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        cached_surface.blit(scaled, (dest_x, dest_y))

        self._base_map_screen_cache = cached_surface
        self._base_map_cache_key = cache_key
        self.screen.blit(cached_surface, (0, 0))
    
    def load_image(self, image_path: str) -> Optional[pygame.Surface]:
        """Load an image from the art directory and cache it."""
        if image_path in self.images:
            return self.images[image_path]
        
        full_path = self.art_path / image_path
        
        if not full_path.exists():
            print(f"Image not found: {full_path}")
            return None
        
        try:
            image = pygame.image.load(str(full_path))
            self.images[image_path] = image
            return image
        except Exception as e:
            print(f"Failed to load image {full_path}: {e}")
            return None

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
        self._base_map_cache_key = None

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
        self._base_map_cache_key = None

    def zoom(self, factor: float) -> None:
        """Zoom the camera by a factor (e.g., 1.1 to zoom in, 0.9 to zoom out)."""
        self.camera_scale *= factor
        # Clamp to reasonable bounds
        self.camera_scale = max(0.1, min(100.0, self.camera_scale))
        self._base_map_cache_key = None

    def world_to_screen(self, x: float, y: float) -> Tuple[int, int]:
        """Transform a point in world coordinates to screen coordinates."""
        screen_w, screen_h = self.screen.get_size()
        ox, oy = self.camera_origin

        sx = (x - ox) * self.camera_scale + screen_w * 0.5
        sy = screen_h * 0.5 - (y - oy) * self.camera_scale

        return int(sx), int(sy)

    def screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
        """Transform a point in screen coordinates to world coordinates."""
        screen_w, screen_h = self.screen.get_size()
        ox, oy = self.camera_origin

        x = (sx - screen_w * 0.5) / self.camera_scale + ox
        y = (screen_h * 0.5 - sy) / self.camera_scale + oy

        return x, y

    def _calculate_centroid(self, polygon: list) -> Tuple[float, float]:
        """Calculate the centroid (center point) of a polygon."""
        if not polygon:
            return 0.0, 0.0
        
        x_coords = [p[0] for p in polygon]
        y_coords = [p[1] for p in polygon]
        
        return sum(x_coords) / len(x_coords), sum(y_coords) / len(y_coords)

    def _parse_rgb_color(self, value) -> Optional[Tuple[int, int, int]]:
        """Parse a color in the form '(r, g, b)' into an RGB tuple."""
        if not isinstance(value, str):
            return None

        s = value.strip()
        if len(s) < 5 or not s.startswith("(") or not s.endswith(")"):
            return None

        parts = [p.strip() for p in s[1:-1].split(",")]
        if len(parts) != 3:
            return None

        try:
            r, g, b = (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None

        return (
            max(0, min(255, r)),
            max(0, min(255, g)),
            max(0, min(255, b)),
        )

    def _get_province_color(self, province: dict) -> Tuple[int, int, int]:
        """Resolve province draw color from owner/controller nation color data."""
        manager = getattr(self.game, "nation_manager", None)
        if manager is None:
            return (200, 200, 200)

        for tag_key in ("controler", "owner"):
            nation_tag = province.get(tag_key)
            if not nation_tag:
                continue

            nation = manager.get_nation(nation_tag)
            if nation is None:
                continue

            rgb = self._parse_rgb_color(nation.extra.get("color"))
            if rgb is not None:
                return rgb

        return (200, 200, 200)

    def _get_province_center(self, province: dict) -> Tuple[float, float]:
        """Get the center point of a province by averaging all polygon centroids."""
        if not province["polygons"]:
            return 0.0, 0.0
        
        centroids = [self._calculate_centroid(poly) for poly in province["polygons"]]
        avg_x = sum(c[0] for c in centroids) / len(centroids)
        avg_y = sum(c[1] for c in centroids) / len(centroids)
        
        return avg_x, avg_y

    def draw_nearby_connections(self, color: Tuple[int, int, int] = (255, 0, 0), width: int = 2) -> None:
        """Draw lines connecting nearby provinces."""
        #print(">>> DRAW_NEARBY_CONNECTIONS CALLED")
        lines_drawn = 0
        for province in self.game.map.get_all_provinces():
            if not province.get("nearby_provinces"):
                continue
            
            center = self._get_province_center(province)
            center_screen = self.world_to_screen(center[0], center[1])
            
            for nearby_id in province["nearby_provinces"]:
                nearby_province = self.game.map.get_province_by_id(nearby_id)
                if nearby_province:
                    nearby_center = self._get_province_center(nearby_province)
                    nearby_center_screen = self.world_to_screen(nearby_center[0], nearby_center[1])
                    
                    # Draw line between the two centers
                    pygame.draw.line(self.screen, color, center_screen, nearby_center_screen, width)
                    lines_drawn += 1
        
        if lines_drawn == 0:
            print("WARNING: No nearby province lines drawn - check if nearby_provinces data is loaded")

    def _get_unit_color(self, unit) -> Tuple[int, int, int]:
        """Get the color of a unit based on its nation."""
        manager = getattr(self.game, "nation_manager", None)
        if manager is None:
            return (100, 100, 100)
        
        nation = manager.get_nation(unit.nation)
        if nation is None:
            return (100, 100, 100)
        
        rgb = self._parse_rgb_color(nation.extra.get("color"))
        if rgb is not None:
            return rgb
        
        return (100, 100, 100)
    
    def _get_unit_screen_position(self, unit):
        """Get the screen position of a unit based on its location (province ID)."""
        province = self.game.map.get_province_by_id(unit.location)
        if province is None:
            return None
        
        center = self._get_province_center(province)
        screen_pos = self.world_to_screen(center[0], center[1])
        return screen_pos
    
    def draw_units(self) -> None:
        """Draw all units on the map as 20x20 colored squares."""
        unit_size = 20
        half_size = unit_size // 2
        
        armies = getattr(self.game, "armies", {})
        if not armies:
            return
        
        for army in armies.values():
            for unit in army.get_all_units():
                pos = self._get_unit_screen_position(unit)
                if pos is None:
                    continue
                
                sx, sy = pos
                color = self._get_unit_color(unit)
                
                rect = pygame.Rect(sx - half_size, sy - half_size, unit_size, unit_size)
                pygame.draw.rect(self.screen, color, rect)
                pygame.draw.rect(self.screen, (0, 0, 0), rect, 2)
    
    def get_unit_at_point(self, wx: float, wy: float):
        """Get the unit at a given world position, if any."""
        unit_size = 20
        half_size = unit_size // 2
        test_sx, test_sy = self.world_to_screen(wx, wy)
        
        armies = getattr(self.game, "armies", {})
        if not armies:
            return None
        
        for army in armies.values():
            for unit in army.get_all_units():
                pos = self._get_unit_screen_position(unit)
                if pos is None:
                    continue
                
                sx, sy = pos
                rect = pygame.Rect(sx - half_size, sy - half_size, unit_size, unit_size)
                if rect.collidepoint(test_sx, test_sy):
                    return unit
        
        return None

    def draw(self, debug_draw_connections: bool = True):
        # Clear the screen with a background color (e.g., white)
        self.screen.fill((255, 255, 255))

        # Draw base map if loaded
        self._draw_base_map()

        # Draw provinces transformed into screen space
        province_overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for province in self.game.map.get_all_provinces():
            fill_r, fill_g, fill_b = self._get_province_color(province)
            for polygon in province["polygons"]:
                transformed = [self.world_to_screen(x, y) for x, y in polygon]
                pygame.draw.polygon(province_overlay, (fill_r, fill_g, fill_b, 90), transformed)
                pygame.draw.polygon(self.screen, (60, 60, 60), transformed, 1)
        self.screen.blit(province_overlay, (0, 0))

        # Draw nearby province connections on top if enabled
        if debug_draw_connections:
            self.draw_nearby_connections()

        # Draw units on top of everything
        self.draw_units()

        # Update the display
        pygame.display.flip()
