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
        self.rbar_image: Optional[pygame.Surface] = None
        _screen_h = screen.get_height()
        _ui_font_size = max(14, min(22, _screen_h // 50))
        self.ui_font: pygame.font.Font = pygame.font.Font(None, _ui_font_size)
        self._unit_portrait_cache: Dict[str, Optional[pygame.Surface]] = {}
        self._unit_icon_cache: Dict[str, Optional[pygame.Surface]] = {}
        self._unit_flag_cache: Dict[str, Optional[pygame.Surface]] = {}
        self.fog_of_war = 1 #0 = off. 1 = on
        self.player_nation_tag = self._get_player_nation_tag()
        self._unit_status_dropdown_open: bool = False
        self._unit_status_combobox_rect: Optional[pygame.Rect] = None
        self._unit_status_dropdown_rects: list[tuple[pygame.Rect, int]] = []
        self._unit_target_size_input_rect: Optional[pygame.Rect] = None
        self._unit_target_size_input_active: bool = False
        self._unit_target_size_input_text: str = ""
        self._unit_screen_rects: Dict[int, pygame.Rect] = {}
        self._unit_draw_order: list[int] = []
        self._unit_stack_hitboxes: list[tuple[pygame.Rect, list[int]]] = []
        self._train_screen_rects: Dict[str, pygame.Rect] = {}
        self._train_draw_order: list[str] = []
        self._province_create_unit_button_rect: Optional[pygame.Rect] = None
        self._province_create_logistics_button_rect: Optional[pygame.Rect] = None
        self._province_logistics_hub_checkbox_rect: Optional[pygame.Rect] = None
        self.people_button_image: Optional[pygame.Surface] = None
        self.people_overlay_bg_image: Optional[pygame.Surface] = None
        self.people_quit_button_image: Optional[pygame.Surface] = None
        self._people_button_rect: Optional[pygame.Rect] = None
        self._people_overlay_open: bool = False
        self._people_overlay_rect: Optional[pygame.Rect] = None
        self._people_overlay_quit_rect: Optional[pygame.Rect] = None
        self._people_overlay_scroll_offset: int = 0
        self._people_overlay_scrollbar_rect: Optional[pygame.Rect] = None
        self._people_overlay_scrollbar_thumb_rect: Optional[pygame.Rect] = None
        self._people_overlay_scrollbar_range: tuple = (0, 0)
        
        # Load base map if available
        self._load_base_map()
        self._load_ui_assets()

    def _get_player_nation_tag(self) -> Optional[str]:
        """Return the player nation tag configured on the game, if any."""
        nation_tag = str(getattr(self.game, "nation", "")).strip()
        return nation_tag or None

    def _get_root_nation_tag(self, nation_tag: Optional[str]) -> Optional[str]:
        """Return the top-level nation tag for a nation or substate."""
        if not nation_tag:
            return nation_tag

        manager = getattr(self.game, "nation_manager", None)
        if manager is None:
            return nation_tag

        current_tag = nation_tag
        visited = set()
        while current_tag and current_tag not in visited:
            visited.add(current_tag)
            nation = manager.get_nation(current_tag)
            if nation is None or not nation.parent:
                return current_tag
            current_tag = nation.parent

        return nation_tag

    def _is_player_side_nation(self, nation_tag: Optional[str]) -> bool:
        """Return True when a nation belongs to the player side or one of its substates."""
        player_root = self._get_root_nation_tag(self._get_player_nation_tag())
        if player_root is None:
            return False

        return self._get_root_nation_tag(nation_tag) == player_root

    def _province_is_player_controlled(self, province: dict) -> bool:
        """Return True when the province is owned or controlled by the player side."""
        for tag_key in ("controler", "owner"):
            if self._is_player_side_nation(province.get(tag_key)):
                return True
        return False

    def _province_has_player_side_unit(self, province: dict) -> bool:
        """Return True when a player-side unit is stationed in the province."""
        province_id = province.get("id")
        if province_id is None:
            return False

        armies = getattr(self.game, "armies", {})
        for army in armies.values():
            for unit in army.get_all_units():
                if getattr(unit, "location", None) == province_id and self._is_player_side_nation(getattr(unit, "nation", None)):
                    return True

        return False

    def _province_is_visible_under_fog(self, province: dict) -> bool:
        """Return True when a province should stay lit under fog of war."""
        if not self.fog_of_war:
            return True

        if self._province_is_player_controlled(province):
            return True

        if self._province_has_player_side_unit(province):
            return True

        for nearby_id in province.get("nearby_provinces", []):
            nearby_province = self.game.map.get_province_by_id(nearby_id)
            if nearby_province and (
                self._province_is_player_controlled(nearby_province)
                or self._province_has_player_side_unit(nearby_province)
            ):
                return True

        return False

    def _is_unit_visible_to_player(self, unit) -> bool:
        """Return True when a unit should be visible to the player under fog of war."""
        if not self.fog_of_war:
            return True

        if self._is_player_side_nation(getattr(unit, "nation", None)):
            return True

        for spotter_id in getattr(unit, "spoted_by", []):
            spotter = self._find_unit_by_id(spotter_id)
            if spotter is not None and self._is_player_side_nation(getattr(spotter, "nation", None)):
                return True

        return False

    @staticmethod
    def _shade_color(color: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
        """Darken a color by multiplying each channel by factor."""
        return tuple(max(0, min(255, int(channel * factor))) for channel in color)

    def _load_ui_assets(self) -> None:
        """Load UI overlays such as Art/UI/RBar.png."""
        screen_h = self.screen.get_height()
        if screen_h >= 1080:
            candidates = [
                self.art_path / "UI" / "RBar1080.png",
                self.art_path / "ui" / "RBar1080.png",
                self.art_path / "UI" / "RBar.png",
                self.art_path / "ui" / "RBar.png",
            ]
        else:
            candidates = [
                self.art_path / "UI" / "RBar.png",
                self.art_path / "ui" / "RBar.png",
            ]

        for ui_path in candidates:
            if ui_path.exists():
                try:
                    self.rbar_image = pygame.image.load(str(ui_path)).convert_alpha()
                    print(f"Loaded UI bar: {ui_path}")
                    break
                except Exception as e:
                    print(f"Failed to load UI bar {ui_path}: {e}")

        if self.rbar_image is None:
            print("UI bar not found (expected Art/UI/RBar.png or Art/ui/RBar.png)")

        people_btn_candidates = [
            self.art_path / "UI" / "peopleBtn.PNG",
            self.art_path / "ui" / "peopleBtn.PNG",
            self.art_path / "UI" / "peopleBtn.png",
            self.art_path / "ui" / "peopleBtn.png",
        ]
        for btn_path in people_btn_candidates:
            if btn_path.exists():
                try:
                    self.people_button_image = pygame.image.load(str(btn_path)).convert_alpha()
                    break
                except Exception as e:
                    print(f"Failed to load People button {btn_path}: {e}")

        people_bg_candidates = [
            self.art_path / "UI" / "BackgroundUI.png",
            self.art_path / "ui" / "BackgroundUI.png",
        ]
        for bg_path in people_bg_candidates:
            if bg_path.exists():
                try:
                    self.people_overlay_bg_image = pygame.image.load(str(bg_path)).convert_alpha()
                    break
                except Exception as e:
                    print(f"Failed to load people overlay background {bg_path}: {e}")

        quit_btn_candidates = [
            self.art_path / "UI" / "QuitBtn.PNG",
            self.art_path / "ui" / "QuitBtn.PNG",
            self.art_path / "UI" / "quitbtn.png",
            self.art_path / "ui" / "quitbtn.png",
        ]
        for quit_path in quit_btn_candidates:
            if quit_path.exists():
                try:
                    self.people_quit_button_image = pygame.image.load(str(quit_path)).convert_alpha()
                    break
                except Exception as e:
                    print(f"Failed to load people quit button {quit_path}: {e}")

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
        center = self.game.map.get_province_center(province)
        if center is not None:
            return center

        # Legacy in-graphics center calculation kept for reference.
        # if not province["polygons"]:
        #     return 0.0, 0.0
        #
        # centroids = [self._calculate_centroid(poly) for poly in province["polygons"]]
        # avg_x = sum(c[0] for c in centroids) / len(centroids)
        # avg_y = sum(c[1] for c in centroids) / len(centroids)
        #
        # return avg_x, avg_y

        return 0.0, 0.0

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

    def draw_rails(self, color: Tuple[int, int, int] = (205, 205, 205), width: int = 3) -> None:
        """Draw rail lines by connecting the centers of provinces in each rail path."""
        rails = getattr(self.game.map, "get_all_rails", lambda: [])()
        if not rails:
            return

        underlay = (100, 100, 100)
        cap_radius = max(2, width // 2)

        for rail in rails:
            points = rail.get("points", [])
            if len(points) < 2:
                continue

            for idx in range(len(points) - 1):
                start_province = self.game.map.get_province_by_id(points[idx])
                end_province = self.game.map.get_province_by_id(points[idx + 1])
                if not start_province or not end_province:
                    continue

                start_center = self._get_province_center(start_province)
                end_center = self._get_province_center(end_province)
                start_screen = self.world_to_screen(start_center[0], start_center[1])
                end_screen = self.world_to_screen(end_center[0], end_center[1])
                # Outline + light core keeps rails visible on mixed map colors.
                pygame.draw.line(self.screen, underlay, start_screen, end_screen, width + 2)
                pygame.draw.line(self.screen, color, start_screen, end_screen, width)
                pygame.draw.circle(self.screen, underlay, start_screen, cap_radius + 1)
                pygame.draw.circle(self.screen, color, start_screen, cap_radius)
                pygame.draw.circle(self.screen, underlay, end_screen, cap_radius + 1)
                pygame.draw.circle(self.screen, color, end_screen, cap_radius)

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

    def _get_train_color(self, train) -> Tuple[int, int, int]:
        """Get train color based on nation color."""
        manager = getattr(self.game, "nation_manager", None)
        if manager is None:
            return (170, 170, 170)

        nation = manager.get_nation(getattr(train, "nation", None))
        if nation is None:
            return (170, 170, 170)

        rgb = self._parse_rgb_color(nation.extra.get("color"))
        return rgb if rgb is not None else (170, 170, 170)

    def _draw_single_train(self, train, cx: int, cy: int, size: int) -> None:
        """Draw one train marker and register click rect."""
        rect = pygame.Rect(cx - size // 2, cy - size // 2, size, size)
        train_id = str(getattr(train, "id", ""))
        self._train_screen_rects[train_id] = rect
        self._train_draw_order.append(train_id)

        fill = self._shade_color(self._get_train_color(train), 0.85)
        border = (20, 20, 20)
        if str(getattr(self.game, "train_selected", "")) == train_id:
            border = (255, 220, 110)

        pygame.draw.rect(self.screen, fill, rect, border_radius=5)
        pygame.draw.rect(self.screen, border, rect, 2, border_radius=5)

        label_font = pygame.font.Font(None, max(12, size // 2))
        label = label_font.render("T", True, (15, 15, 15))
        self.screen.blit(label, label.get_rect(center=rect.center))

    def draw_trains(self) -> None:
        """Draw trains on map with unit-like markers."""
        trains = getattr(self.game, "trains", {})
        if not trains:
            self._train_screen_rects = {}
            self._train_draw_order = []
            return

        self._train_screen_rects = {}
        self._train_draw_order = []

        marker_size = max(12, int(self._get_unit_draw_size() * 0.52))
        for train in trains.values():
            province = self.game.map.get_province_by_id(getattr(train, "location", None))
            if province is None:
                continue

            # Keep same visibility logic spirit as units under fog.
            if self.fog_of_war and not self._province_is_visible_under_fog(province):
                if not self._is_player_side_nation(getattr(train, "nation", None)):
                    continue

            center = self._get_province_center(province)
            cx, cy = self.world_to_screen(center[0], center[1])
            self._draw_single_train(train, cx, cy, marker_size)

    def get_train_at_point(self, wx: float, wy: float):
        """Return top-most clicked train from cached train rects."""
        sx, sy = self.world_to_screen(wx, wy)
        for train_id in reversed(self._train_draw_order):
            rect = self._train_screen_rects.get(train_id)
            if rect is None or not rect.collidepoint(sx, sy):
                continue
            return getattr(self.game, "trains", {}).get(str(train_id))
        return None
    
    def _get_unit_screen_position(self, unit):
        """Get the screen position of a unit based on its location (province ID)."""
        province = self.game.map.get_province_by_id(unit.location)
        if province is None:
            return None
        
        center = self._get_province_center(province)
        screen_pos = self.world_to_screen(center[0], center[1])
        return screen_pos

    def _get_unit_draw_size(self) -> int:
        """Scale unit marker with zoom; keep small size only when very zoomed out."""
        # At very low zoom, keep marker compact. Otherwise ramp quickly to larger sizes.
        if self.camera_scale <= 0.35:
            return 20

        zoom_factor = min(1.0, self.camera_scale / 4.0)
        return int(20 + (65 * zoom_factor))

    def _get_unit_type_key(self, unit) -> str:
        type_aliases = {
            1: "infantry",
            2: "cav",
            3: "arty",
            4: "logi",
            5: "hq",
            6: "militia",
            7: "engineer",
            8: "mountaineer",
        }

        raw_type = getattr(unit, "type", None)
        if raw_type is not None:
            try:
                type_id = int(raw_type)
                if type_id in type_aliases:
                    return type_aliases[type_id]
            except (TypeError, ValueError):
                type_str = str(raw_type).strip().lower()
                if type_str:
                    return type_str.replace("-", "_").replace(" ", "_")

        raw_name = str(getattr(unit, "name", "")).strip().lower()
        if raw_name:
            return raw_name.replace("-", "_").replace(" ", "_")

        return "unit"

    def _get_unit_icon(self, unit, size: int) -> Optional[pygame.Surface]:
        unit_key = self._get_unit_type_key(unit)
        cache_key = f"{unit_key}:{size}"
        if cache_key in self._unit_icon_cache:
            return self._unit_icon_cache[cache_key]

        base_key = unit_key.split("_")[0]
        candidates = [
            f"ui/{unit_key}.png",
            f"ui/{unit_key}.jpg",
            f"ui/{base_key}.png",
            f"ui/{base_key}.jpg",
            "ui/unit.png",
            "ui/default_unit.png",
        ]

        for image_path in candidates:
            image = self.load_image(image_path)
            if image is not None:
                src_w, src_h = image.get_size()
                if src_w <= 0 or src_h <= 0:
                    continue

                ratio = min(size / src_w, size / src_h)
                target_w = max(1, int(src_w * ratio))
                target_h = max(1, int(src_h * ratio))
                scaled = pygame.transform.smoothscale(image, (target_w, target_h))
                self._unit_icon_cache[cache_key] = scaled
                return scaled

        self._unit_icon_cache[cache_key] = None
        return None

    def _get_unit_flag(self, unit, max_width: int, max_height: int) -> Optional[pygame.Surface]:
        """Return scaled nation flag image for a unit, if available."""
        nation_tag = str(getattr(unit, "nation", "")).strip().upper()
        if not nation_tag:
            return None

        root_tag = self._get_root_nation_tag(nation_tag)
        candidate_tags = [nation_tag]
        if root_tag:
            candidate_tags.append(str(root_tag).strip().upper())

        for tag in candidate_tags:
            cache_key = f"{tag}:{max_width}x{max_height}"
            if cache_key in self._unit_flag_cache:
                return self._unit_flag_cache[cache_key]

            for image_path in (f"flags/{tag}.png", f"flags/{tag}.jpg"):
                image = self.load_image(image_path)
                if image is None:
                    continue

                try:
                    scaled = self._get_scaled_surface_to_fit(image, max_width, max_height)
                except Exception:
                    scaled = None
                self._unit_flag_cache[cache_key] = scaled
                return scaled

            self._unit_flag_cache[cache_key] = None

        return None

    def _get_scaled_surface_to_fit(
        self,
        surface: pygame.Surface,
        max_width: int,
        max_height: int,
    ) -> Optional[pygame.Surface]:
        """Scale a surface to fit inside bounds while preserving aspect ratio."""
        src_w, src_h = surface.get_size()
        if src_w <= 0 or src_h <= 0 or max_width <= 0 or max_height <= 0:
            return None

        ratio = min(max_width / src_w, max_height / src_h)
        target_w = max(1, int(src_w * ratio))
        target_h = max(1, int(src_h * ratio))

        # Some image formats (palette/indexed) are not compatible with smoothscale.
        # Convert first and fallback to regular scale if smoothscale still fails.
        try:
            return pygame.transform.smoothscale(surface, (target_w, target_h))
        except Exception:
            try:
                converted = surface.convert_alpha()
                return pygame.transform.smoothscale(converted, (target_w, target_h))
            except Exception:
                try:
                    converted = surface.convert()
                    return pygame.transform.scale(converted, (target_w, target_h))
                except Exception:
                    try:
                        return pygame.transform.scale(surface, (target_w, target_h))
                    except Exception:
                        return None

    def _get_unit_stat_line(self, unit) -> str:
        """Return compact attack/defense string shown inside large unit boxes."""
        attack = getattr(unit, "attack", None)
        defense = getattr(unit, "defense", None)
        if attack is None or defense is None:
            return ""
        return f"{attack}|{defense}"

    def _get_unit_status_text(self, unit) -> str:
        """Return human-readable unit status for marker overlay text."""
        status_fn = getattr(unit, "return_status", None)
        if callable(status_fn):
            return str(status_fn())

        return str(getattr(unit, "status", ""))

    @staticmethod
    def _get_status_label(status_code: int) -> str:
        labels = {
            0: "Reserve",
            1: "Deployed",
            2: "Quartered",
            3: "Moving",
            4: "Resting",
            5: "Defending",
            6: "Improving Defenses",
            7: "Securing Province",
            8: "Disorganized",
            9: "Guerrilla/Recon",
            10: "Attacking",
            11: "Mobilizing",
            12: "Strategic Redeployment",
            13: "Forming Up",
        }
        return labels.get(status_code, f"Status {status_code}")

    @staticmethod
    def _get_train_status_label(status_code: int) -> str:
        labels = {
            0: "Idle",
            1: "Moving",
            2: "Stopped",
            3: "Loading",
            4: "Unloading",
            5: "Maintenance",
            6: "Damaged",
            7: "Disabled",
            8: "Loading/Unloading Troops",
        }
        return labels.get(status_code, f"Status {status_code}")

    def _get_unit_status_options(self, unit) -> list[tuple[int, str, bool]]:
        """Return available unit status options as (code, label, is_current)."""
        possible_status_fn = getattr(unit, "possible_status", None)
        if not callable(possible_status_fn):
            return []

        current_status = getattr(unit, "status", None)
        seen_statuses = set()
        options: list[tuple[int, str, bool]] = []
        for status_code in possible_status_fn():
            if status_code in seen_statuses:
                continue
            seen_statuses.add(status_code)
            options.append((status_code, self._get_status_label(status_code), status_code == current_status))

        return options

    def _get_train_status_options(self, train) -> list[tuple[int, str, bool]]:
        """Return available train status options as (code, label, is_current)."""
        possible_status_fn = getattr(train, "return_possible_status", None)
        if not callable(possible_status_fn):
            return []

        current_status = getattr(train, "status", None)
        seen_statuses = set()
        options: list[tuple[int, str, bool]] = []
        for status_code in possible_status_fn():
            if status_code in seen_statuses:
                continue
            seen_statuses.add(status_code)
            options.append((status_code, self._get_train_status_label(status_code), status_code == current_status))

        return options

    def can_edit_train_status(self, train) -> bool:
        """Return True when status controls should be shown for a train."""
        return train is not None and self._is_player_side_nation(getattr(train, "nation", None))

    def _draw_train_status_panel(self, train, panel_x: int, start_y: int, content_w: int) -> int:
        """Draw combo box dropdown for train status selection."""
        self._unit_status_dropdown_rects = []
        self._unit_status_combobox_rect = None

        options = self._get_train_status_options(train)
        if not options:
            return start_y

        base = self.ui_font.size("A")[1]
        title_font = pygame.font.Font(None, max(18, base + 6))
        item_font = pygame.font.Font(None, max(14, base + 2))
        heading = title_font.render("Train Status", True, (240, 240, 240))
        self.screen.blit(heading, (panel_x, start_y))

        combobox_top = start_y + max(22, base + 8)
        combobox_height = max(26, base + 14)
        combobox_rect = pygame.Rect(panel_x, combobox_top, content_w, combobox_height)
        self._unit_status_combobox_rect = combobox_rect

        current_status = getattr(train, "status", None)
        current_label = self._get_train_status_label(current_status)

        pygame.draw.rect(self.screen, (42, 48, 56), combobox_rect, border_radius=4)
        pygame.draw.rect(self.screen, (120, 120, 120), combobox_rect, 1, border_radius=4)

        text = self._fit_text(current_label, content_w - 20)
        text_surface = item_font.render(text, True, (245, 245, 245))
        text_rect = text_surface.get_rect(midleft=(panel_x + 8, combobox_rect.centery))
        self.screen.blit(text_surface, text_rect)

        if self._unit_status_dropdown_open:
            dropdown_top = combobox_top + combobox_height + 2
            item_height = max(22, base + 10)
            for index, (status_code, label, is_current) in enumerate(options):
                item_rect = pygame.Rect(panel_x, dropdown_top + (index * item_height), content_w, item_height)
                fill_color = (70, 110, 150) if is_current else (55, 60, 70)
                pygame.draw.rect(self.screen, fill_color, item_rect)
                pygame.draw.rect(self.screen, (100, 100, 100), item_rect, 1)

                item_text = self._fit_text(label, content_w - 16)
                item_surface = item_font.render(item_text, True, (240, 240, 240))
                item_text_rect = item_surface.get_rect(midleft=(panel_x + 8, item_rect.centery))
                self.screen.blit(item_surface, item_text_rect)

                self._unit_status_dropdown_rects.append((item_rect, status_code))

            return dropdown_top + (len(options) * item_height)

        return combobox_top + combobox_height

    def begin_unit_target_size_input(self, unit) -> None:
        """Focus target-size input and prefill with current value."""
        current_target = int(getattr(unit, "targetsize", getattr(unit, "soldiers", 0)))
        self._unit_target_size_input_text = str(current_target)
        self._unit_target_size_input_active = True

    def end_unit_target_size_input(self) -> None:
        """Unfocus target-size input."""
        self._unit_target_size_input_active = False

    def append_unit_target_size_digit(self, digit: str) -> None:
        """Append one numeric digit to target-size input."""
        if digit.isdigit() and len(self._unit_target_size_input_text) < 9:
            self._unit_target_size_input_text += digit

    def backspace_unit_target_size_input(self) -> None:
        """Remove one character from target-size input."""
        self._unit_target_size_input_text = self._unit_target_size_input_text[:-1]

    def commit_unit_target_size_input(self, unit) -> tuple[bool, str]:
        """Apply typed target-size value with reserve-only downsizing rule."""
        raw = self._unit_target_size_input_text.strip()
        if not raw:
            return False, "Type a target size first."

        try:
            new_target = int(raw)
        except ValueError:
            return False, "Target size must be a number."

        if new_target <= 0:
            return False, "Target size must be greater than 0."

        current_target = int(getattr(unit, "targetsize", getattr(unit, "soldiers", 0)))
        if new_target < current_target and getattr(unit, "status", None) != 0:
            return False, "Can't reduce target size unless unit is in Reserve."

        set_target_fn = getattr(unit, "set_target_size", None)
        if callable(set_target_fn):
            set_target_fn(new_target)
        elif getattr(unit, "home", None) == getattr(unit, "location", None):
            unit.targetsize = new_target

        if int(getattr(unit, "targetsize", current_target)) != new_target:
            return False, "unit can't change it's size because its not at home,"

        self._unit_target_size_input_text = str(new_target)
        self._unit_target_size_input_active = False
        return True, f"Set unit {unit.id} target size to {new_target}"

    def get_unit_by_id(self, unit_id):
        """Return a unit by id from any army."""
        return self._find_unit_by_id(unit_id)

    def can_edit_unit_status(self, unit) -> bool:
        """Return True when status controls should be shown for the unit."""
        return unit is not None and self._is_player_side_nation(getattr(unit, "nation", None))

    def get_unit_status_option_at_point(self, sx: int, sy: int) -> Optional[int]:
        """Return the status code for a clicked dropdown item, if any."""
        for rect, status_code in self._unit_status_dropdown_rects:
            if rect.collidepoint(sx, sy):
                return status_code
        return None

    def is_unit_status_panel_point(self, sx: int, sy: int) -> bool:
        """Return True when the screen point falls inside the combo box or dropdown."""
        if self._unit_status_combobox_rect and self._unit_status_combobox_rect.collidepoint(sx, sy):
            return True
        return any(rect.collidepoint(sx, sy) for rect, _ in self._unit_status_dropdown_rects)

    def is_unit_target_size_panel_point(self, sx: int, sy: int) -> bool:
        """Return True when the point falls inside target-size input box."""
        return self._unit_target_size_input_rect is not None and self._unit_target_size_input_rect.collidepoint(sx, sy)

    def toggle_unit_status_dropdown(self) -> None:
        """Toggle the unit status dropdown open/closed."""
        self._unit_status_dropdown_open = not self._unit_status_dropdown_open

    def is_unit_target_size_input_active(self) -> bool:
        """Return True when target-size input has focus."""
        return self._unit_target_size_input_active

    def can_create_unit_in_selected_province(self, province: dict, province_obj) -> bool:
        """Return True when the selected province can spawn a new unit."""
        if province is None or province_obj is None:
            return False

        if not self._province_is_player_controlled(province):
            return False

        return getattr(province_obj, "province_recruits", 0) > 0

    def can_toggle_logistic_hub_in_selected_province(self, province: dict, province_obj) -> bool:
        """Return True when player-side ownership/control allows editing hub state."""
        if province is None or province_obj is None:
            return False

        return self._province_is_player_controlled(province)

    def is_province_create_unit_panel_point(self, sx: int, sy: int) -> bool:
        """Return True when a click lands on the province recruit button."""
        return self._province_create_unit_button_rect is not None and self._province_create_unit_button_rect.collidepoint(sx, sy)

    def is_province_create_logistics_panel_point(self, sx: int, sy: int) -> bool:
        """Return True when a click lands on the province logistics recruit button."""
        return self._province_create_logistics_button_rect is not None and self._province_create_logistics_button_rect.collidepoint(sx, sy)

    def is_province_logistics_hub_checkbox_point(self, sx: int, sy: int) -> bool:
        """Return True when a click lands on the province logistics hub checkbox."""
        return self._province_logistics_hub_checkbox_rect is not None and self._province_logistics_hub_checkbox_rect.collidepoint(sx, sy)

    def _draw_unit_status_panel(self, unit, panel_x: int, start_y: int, content_w: int, screen_h: int) -> int:
        """Draw a combo box dropdown for unit status selection."""
        self._unit_status_dropdown_rects = []
        self._unit_status_combobox_rect = None

        options = self._get_unit_status_options(unit)
        if not options:
            return start_y

        base = self.ui_font.size("A")[1]
        title_font = pygame.font.Font(None, max(18, base + 6))
        item_font = pygame.font.Font(None, max(14, base + 2))
        heading = title_font.render("Status", True, (240, 240, 240))
        self.screen.blit(heading, (panel_x, start_y))

        combobox_top = start_y + max(22, base + 8)
        combobox_height = max(26, base + 14)
        combobox_rect = pygame.Rect(panel_x, combobox_top, content_w, combobox_height)
        self._unit_status_combobox_rect = combobox_rect

        current_status = getattr(unit, "status", None)
        current_label = self._get_status_label(current_status)

        pygame.draw.rect(self.screen, (42, 48, 56), combobox_rect, border_radius=4)
        pygame.draw.rect(self.screen, (120, 120, 120), combobox_rect, 1, border_radius=4)

        text = self._fit_text(current_label, content_w - 20)
        text_surface = item_font.render(text, True, (245, 245, 245))
        text_rect = text_surface.get_rect(midleft=(panel_x + 8, combobox_rect.centery))
        self.screen.blit(text_surface, text_rect)

        if self._unit_status_dropdown_open:
            dropdown_top = combobox_top + combobox_height + 2
            item_height = max(22, base + 10)
            for index, (status_code, label, is_current) in enumerate(options):
                item_rect = pygame.Rect(panel_x, dropdown_top + (index * item_height), content_w, item_height)
                fill_color = (70, 110, 150) if is_current else (55, 60, 70)
                pygame.draw.rect(self.screen, fill_color, item_rect)
                pygame.draw.rect(self.screen, (100, 100, 100), item_rect, 1)

                item_text = self._fit_text(label, content_w - 16)
                item_surface = item_font.render(item_text, True, (240, 240, 240))
                item_text_rect = item_surface.get_rect(midleft=(panel_x + 8, item_rect.centery))
                self.screen.blit(item_surface, item_text_rect)

                self._unit_status_dropdown_rects.append((item_rect, status_code))

            dropdown_bottom = dropdown_top + (len(options) * item_height)
            return dropdown_bottom
        else:
            return combobox_top + combobox_height

    def _draw_unit_target_size_panel(self, unit, panel_x: int, start_y: int, content_w: int) -> int:
        """Draw target-size text input when at home; otherwise show explanation text."""
        self._unit_target_size_input_rect = None

        if getattr(unit, "location", None) != getattr(unit, "home", None):
            self._unit_target_size_input_active = False
            message_font = pygame.font.Font(None, max(14, self.ui_font.size("A")[1] + 1))
            msg = "unit can't change it's size because its not at home,"
            fitted = self._fit_text(msg, content_w)
            if fitted:
                self.screen.blit(message_font.render(fitted, True, (230, 200, 200)), (panel_x, start_y))
            return start_y + (message_font.get_linesize() + 6)

        base = self.ui_font.size("A")[1]
        title_font = pygame.font.Font(None, max(18, base + 6))
        item_font = pygame.font.Font(None, max(14, base + 2))
        heading = title_font.render("Target Size", True, (240, 240, 240))
        self.screen.blit(heading, (panel_x, start_y))

        input_top = start_y + max(22, base + 8)
        input_h = max(26, base + 14)
        input_rect = pygame.Rect(panel_x, input_top, content_w, input_h)
        self._unit_target_size_input_rect = input_rect

        if not self._unit_target_size_input_active:
            self._unit_target_size_input_text = str(int(getattr(unit, "targetsize", getattr(unit, "soldiers", 0))))

        current_target = int(getattr(unit, "targetsize", getattr(unit, "soldiers", 0)))
        fill = (50, 56, 64) if self._unit_target_size_input_active else (42, 48, 56)
        border = (160, 190, 230) if self._unit_target_size_input_active else (120, 120, 120)
        pygame.draw.rect(self.screen, fill, input_rect, border_radius=4)
        pygame.draw.rect(self.screen, border, input_rect, 1, border_radius=4)

        if self._unit_target_size_input_active:
            # Keep empty text visible while editing and show a blinking cursor.
            cursor = "|" if (pygame.time.get_ticks() // 450) % 2 == 0 else ""
            show_text = f"{self._unit_target_size_input_text}{cursor}"
        else:
            show_text = str(current_target)

        text = self._fit_text(show_text, content_w - 20)
        text_surface = item_font.render(text, True, (245, 245, 245))
        text_rect = text_surface.get_rect(midleft=(panel_x + 8, input_rect.centery))
        self.screen.blit(text_surface, text_rect)
        hint = self._fit_text("Type number and press Enter", content_w)
        if hint:
            self.screen.blit(item_font.render(hint, True, (205, 205, 205)), (panel_x, input_rect.bottom + 3))
        return input_rect.bottom + item_font.get_linesize() + 3
    
    def _draw_single_unit(self, unit, cx: int, cy: int, unit_size: int, draw_icon: bool, show_stats: bool, text_font: "pygame.font.Font") -> None:
        """Render one unit box centred on (cx, cy) and cache its screen rect."""
        half = unit_size // 2
        rect = pygame.Rect(cx - half, cy - half, unit_size, unit_size)
        self._unit_screen_rects[unit.id] = rect
        self._unit_draw_order.append(unit.id)

        color = self._get_unit_color(unit)
        card_fill = self._shade_color(color, 0.90)
        card_stroke = (30, 30, 30)
        selected_ids = set(getattr(self.game, "unit_multi_selected", []))
        if getattr(self.game, "unit_selected", 0) == unit.id:
            card_stroke = (248, 224, 114)
        elif unit.id in selected_ids:
            card_stroke = (198, 214, 246)

        shadow = rect.move(2, 2)
        pygame.draw.rect(self.screen, (0, 0, 0, 70), shadow, border_radius=4)
        pygame.draw.rect(self.screen, card_fill, rect, border_radius=4)
        pygame.draw.rect(self.screen, card_stroke, rect, 2, border_radius=4)

        if draw_icon:
            raw_icon = self._get_unit_icon(unit, 128)
            if raw_icon is not None:
                icon = self._get_scaled_surface_to_fit(raw_icon, unit_size - 10, int(unit_size * 0.44))
                if icon is not None:
                    self.screen.blit(icon, icon.get_rect(midtop=(rect.centerx, rect.top + 4)))

        flag = self._get_unit_flag(unit, max(12, unit_size // 4), max(8, unit_size // 6))
        if flag is not None:
            flag_rect = flag.get_rect()
            flag_rect.topright = (rect.right - 4, rect.top + 4)
            self.screen.blit(flag, flag_rect)

        if show_stats:
            fh = text_font.get_linesize()
            max_tw = unit_size - 8

            def _fit(txt: str) -> str:
                if text_font.size(txt)[0] <= max_tw:
                    return txt
                while txt and text_font.size(txt + "…")[0] > max_tw:
                    txt = txt[:-1]
                return txt + "…" if txt else ""

            bottom = rect.bottom - 2
            stat_line = _fit(self._get_unit_stat_line(unit))
            if stat_line:
                s = text_font.render(stat_line, True, (18, 18, 18))
                self.screen.blit(s, s.get_rect(midbottom=(rect.centerx, bottom)))
                bottom -= fh
            status_text = _fit(self._get_unit_status_text(unit))
            if status_text:
                s = text_font.render(status_text, True, (18, 18, 18))
                self.screen.blit(s, s.get_rect(midbottom=(rect.centerx, bottom)))
                bottom -= fh
            name_text = _fit(str(getattr(unit, "name", "")))
            if name_text:
                s = text_font.render(name_text, True, (18, 18, 18))
                self.screen.blit(s, s.get_rect(midbottom=(rect.centerx, bottom)))

    def draw_units(self) -> None:
        """Draw all visible units as overlapped card stacks per province."""
        unit_size = self._get_unit_draw_size()
        draw_icon = unit_size >= 40
        show_stats = unit_size >= 55
        text_font = pygame.font.Font(None, max(14, unit_size // 5))
        stack_dx = max(3, unit_size // 9)
        stack_dy = max(4, unit_size // 7)

        def _unit_sort_key(unit) -> tuple[int, int, str]:
            raw_id = getattr(unit, "id", "")
            as_text = str(raw_id)

            # Keep numeric IDs ordered numerically when possible.
            try:
                return (0, int(raw_id), as_text)
            except (TypeError, ValueError):
                pass

            # Fallback for IDs like "unit1": extract digits and sort naturally.
            digits = "".join(ch for ch in as_text if ch.isdigit())
            if digits:
                return (1, int(digits), as_text)

            # Final fallback: lexical order for non-numeric IDs.
            return (2, 0, as_text)

        armies = getattr(self.game, "armies", {})
        if not armies:
            return

        self._unit_screen_rects = {}
        self._unit_draw_order = []
        self._unit_stack_hitboxes = []

        # Group visible units by province.
        province_groups: Dict[int, list] = {}
        for army in armies.values():
            for unit in army.get_all_units():
                if not self._is_unit_visible_to_player(unit):
                    continue
                loc = getattr(unit, "location", None)
                if loc is None:
                    continue
                if loc not in province_groups:
                    province_groups[loc] = []
                province_groups[loc].append(unit)

        for province_id, units in province_groups.items():
            province = self.game.map.get_province_by_id(province_id)
            if province is None:
                continue

            units.sort(key=_unit_sort_key)
            selected_id = getattr(self.game, "unit_selected", 0)
            if selected_id:
                units.sort(key=lambda u: getattr(u, "id", None) == selected_id)

            center = self._get_province_center(province)
            cx, cy = self.world_to_screen(center[0], center[1])
            count = len(units)
            half = unit_size // 2

            base_cx = cx - ((count - 1) * stack_dx) // 2
            base_cy = cy - ((count - 1) * stack_dy) // 2

            stack_unit_ids: list[int] = []

            for idx, unit in enumerate(units):
                unit_cx = base_cx + idx * stack_dx
                unit_cy = base_cy + idx * stack_dy
                self._draw_single_unit(unit, unit_cx, unit_cy, unit_size, draw_icon, show_stats, text_font)
                stack_unit_ids.append(unit.id)

            if stack_unit_ids:
                last_cx = base_cx + (count - 1) * stack_dx
                last_cy = base_cy + (count - 1) * stack_dy
                left = min(base_cx, last_cx) - half
                top = min(base_cy, last_cy) - half
                right = max(base_cx, last_cx) + half
                bottom = max(base_cy, last_cy) + half
                stack_rect = pygame.Rect(left, top, max(1, right - left), max(1, bottom - top))
                stack_rect.inflate_ip(max(6, unit_size // 6), max(6, unit_size // 6))
                self._unit_stack_hitboxes.append((stack_rect, stack_unit_ids))
    
    def get_unit_at_point(self, wx: float, wy: float):
        """Get the unit at a given world position using cached screen rects."""
        test_sx, test_sy = self.world_to_screen(wx, wy)

        # Prefer stack-level hitboxes so clicking anywhere on a grouped stack picks its top unit.
        for stack_rect, stack_unit_ids in reversed(self._unit_stack_hitboxes):
            if not stack_rect.collidepoint(test_sx, test_sy):
                continue

            top_to_bottom = list(reversed(stack_unit_ids))
            return self._find_unit_by_id(top_to_bottom[0])

        hit_unit_ids: list[int] = []
        for unit_id in self._unit_draw_order:
            rect = self._unit_screen_rects.get(unit_id)
            if rect is not None and rect.collidepoint(test_sx, test_sy):
                hit_unit_ids.append(unit_id)

        if not hit_unit_ids:
            return None

        # Draw order is bottom -> top, so reverse for click priority.
        top_to_bottom = list(reversed(hit_unit_ids))
        return self._find_unit_by_id(top_to_bottom[0])

    def get_next_visible_unit_in_province(self, unit_id):
        """Return next visible unit in the same province, cycling by stable id order."""
        current = self._find_unit_by_id(unit_id)
        if current is None:
            return None

        province_id = getattr(current, "location", None)
        if province_id is None:
            return current

        same_province_units = []
        armies = getattr(self.game, "armies", {})
        for army in armies.values():
            for unit in army.get_all_units():
                if getattr(unit, "location", None) != province_id:
                    continue
                if not self._is_unit_visible_to_player(unit):
                    continue
                same_province_units.append(unit)

        if len(same_province_units) <= 1:
            return current

        def _unit_sort_key(unit) -> tuple[int, int, str]:
            raw_id = getattr(unit, "id", "")
            as_text = str(raw_id)
            try:
                return (0, int(raw_id), as_text)
            except (TypeError, ValueError):
                digits = "".join(ch for ch in as_text if ch.isdigit())
                if digits:
                    return (1, int(digits), as_text)
                return (2, 0, as_text)

        same_province_units.sort(key=_unit_sort_key)
        for idx, unit in enumerate(same_province_units):
            if getattr(unit, "id", None) == unit_id:
                return same_province_units[(idx + 1) % len(same_province_units)]

        return same_province_units[0]

    def get_units_in_screen_rect(self, selection_rect: pygame.Rect):
        """Return visible units whose markers intersect the given screen-space rectangle."""
        if selection_rect.width <= 0 or selection_rect.height <= 0:
            return []

        found_units = []
        found_ids = set()
        for unit_id in reversed(self._unit_draw_order):
            unit_rect = self._unit_screen_rects.get(unit_id)
            if unit_rect is None or not unit_rect.colliderect(selection_rect):
                continue

            unit = self._find_unit_by_id(unit_id)
            if unit is None or unit_id in found_ids:
                continue

            found_units.append(unit)
            found_ids.add(unit_id)

        return found_units

    def _find_unit_by_id(self, unit_id):
        armies = getattr(self.game, "armies", {})
        for army in armies.values():
            unit = army.get_unit(unit_id)
            if unit is not None:
                return unit
        return None

    def _fit_text(self, text: str, max_width: int) -> str:
        """Trim text with ellipsis so it fits within max_width pixels."""
        if max_width <= 0:
            return ""

        if self.ui_font.size(text)[0] <= max_width:
            return text

        ellipsis = "..."
        if self.ui_font.size(ellipsis)[0] > max_width:
            return ""

        trimmed = text
        while trimmed and self.ui_font.size(f"{trimmed}{ellipsis}")[0] > max_width:
            trimmed = trimmed[:-1]

        return f"{trimmed}{ellipsis}"

    def close_people_overlay(self) -> None:
        self._people_overlay_open = False

    def _get_people_for_selected_province(self, province_id: int):
        simulation = getattr(self.game, "simulation", None)
        if simulation is None:
            return []

        manager = getattr(simulation, "people_manager", None)
        if manager is None:
            return []

        province_people = manager.get_people_in_province(province_id)
        return [p for p in province_people if self._is_player_side_nation(getattr(p, "nation", None))]

    def handle_people_ui_click(self, sx: int, sy: int) -> bool:
        """Handle people button/overlay clicks. Returns True when click is consumed."""
        if self._people_overlay_open:
            if self._people_overlay_quit_rect and self._people_overlay_quit_rect.collidepoint(sx, sy):
                self._people_overlay_open = False
            elif self._people_overlay_scrollbar_rect and self._people_overlay_scrollbar_rect.collidepoint(sx, sy):
                # Click on scrollbar: calculate new scroll position
                total_items, max_rows = self._people_overlay_scrollbar_range
                if total_items > max_rows:
                    scrollbar_rect = self._people_overlay_scrollbar_rect
                    relative_y = sy - scrollbar_rect.top
                    scrollbar_fraction = max(0.0, min(1.0, relative_y / scrollbar_rect.height))
                    max_scroll = total_items - max_rows
                    self._people_overlay_scroll_offset = int(scrollbar_fraction * max_scroll)
            return True

        if self._people_button_rect and self._people_button_rect.collidepoint(sx, sy):
            self._people_overlay_open = True
            self._people_overlay_scroll_offset = 0
            return True

        return False

    def scroll_people_overlay(self, delta: int) -> None:
        """Scroll people list by delta rows (negative = up, positive = down)."""
        if not self._people_overlay_open:
            return
        self._people_overlay_scroll_offset = max(0, self._people_overlay_scroll_offset + delta)

    def _draw_people_overlay(self) -> None:
        if not self._people_overlay_open:
            self._people_overlay_rect = None
            self._people_overlay_quit_rect = None
            return

        selected_province_id = getattr(self.game, "province_selected", 0)
        if not selected_province_id:
            self._people_overlay_open = False
            self._people_overlay_rect = None
            self._people_overlay_quit_rect = None
            return

        screen_w, screen_h = self.screen.get_size()
        overlay_w = int(screen_w * 0.78)
        overlay_h = int(screen_h * 0.72)
        overlay_w = max(540, min(1200, overlay_w))
        overlay_h = max(360, min(900, overlay_h))

        overlay_x = (screen_w - overlay_w) // 2
        overlay_y = (screen_h - overlay_h) // 2
        overlay_rect = pygame.Rect(overlay_x, overlay_y, overlay_w, overlay_h)
        self._people_overlay_rect = overlay_rect

        dim = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 130))
        self.screen.blit(dim, (0, 0))

        if self.people_overlay_bg_image is not None:
            bg = pygame.transform.smoothscale(self.people_overlay_bg_image, (overlay_w, overlay_h))
            self.screen.blit(bg, overlay_rect.topleft)
        else:
            pygame.draw.rect(self.screen, (35, 40, 48), overlay_rect, border_radius=8)
            pygame.draw.rect(self.screen, (110, 120, 135), overlay_rect, 2, border_radius=8)

        title_font = pygame.font.Font(None, max(26, self.ui_font.get_linesize() + 10))
        row_font = pygame.font.Font(None, max(18, self.ui_font.get_linesize() + 2))

        province = self.game.map.get_province_by_id(selected_province_id)
        province_name = str(province.get("name")) if province else f"Province {selected_province_id}"
        title = title_font.render(f"People in {province_name}", True, (245, 245, 245))
        self.screen.blit(title, (overlay_x + 24, overlay_y + 16))

        quit_size = max(30, min(50, overlay_h // 10))
        quit_x = overlay_x + overlay_w - quit_size - 14
        quit_y = overlay_y + 14
        quit_rect = pygame.Rect(quit_x, quit_y, quit_size, quit_size)
        self._people_overlay_quit_rect = quit_rect

        if self.people_quit_button_image is not None:
            quit_img = pygame.transform.smoothscale(self.people_quit_button_image, (quit_size, quit_size))
            self.screen.blit(quit_img, quit_rect.topleft)
        else:
            pygame.draw.rect(self.screen, (130, 40, 40), quit_rect, border_radius=4)
            x_font = pygame.font.Font(None, max(24, quit_size - 6))
            x_text = x_font.render("X", True, (245, 245, 245))
            self.screen.blit(x_text, x_text.get_rect(center=quit_rect.center))

        list_x = overlay_x + 24
        list_y = overlay_y + 66
        list_w = overlay_w - 48
        list_h = overlay_h - 90
        list_rect = pygame.Rect(list_x, list_y, list_w, list_h)
        pygame.draw.rect(self.screen, (38, 38, 38), list_rect, border_radius=6)
        pygame.draw.rect(self.screen, (72, 72, 72), list_rect, 1, border_radius=6)

        headers = ["Name", "Age", "Job", "Home"]
        col_offsets = [16, int(list_w * 0.50), int(list_w * 0.64), int(list_w * 0.80)]
        header_y = list_y + 10
        for header, offset in zip(headers, col_offsets):
            header_surface = row_font.render(header, True, (250, 250, 250))
            self.screen.blit(header_surface, (list_x + offset, header_y))

        pygame.draw.line(self.screen, (115, 115, 115), (list_x + 10, header_y + 24), (list_x + list_w - 10, header_y + 24), 1)

        people_list = self._get_people_for_selected_province(selected_province_id)

        row_height = max(20, row_font.get_linesize() + 3)
        max_rows = max(1, (list_h - 42) // row_height)
        
        start_idx = min(self._people_overlay_scroll_offset, max(0, len(people_list) - max_rows))
        visible_people = people_list[start_idx : start_idx + max_rows]

        for idx, person in enumerate(visible_people):
            row_y = header_y + 30 + (idx * row_height)
            row_rect = pygame.Rect(list_x + 8, row_y - 1, list_w - 16, row_height)
            row_color = (58, 58, 58) if (start_idx + idx) % 2 == 0 else (46, 46, 46)
            pygame.draw.rect(self.screen, row_color, row_rect)

            age = person.get_age() if hasattr(person, "get_age") else max(0, int(getattr(person, "age", 0)))
            full_name = f"{person.name} {person.familyName}".strip()
            job_label = person.get_job_label() if hasattr(person, "get_job_label") else str(getattr(person, "job", "None"))

            values = [full_name, str(age), job_label, str(getattr(person, "home", "-"))]
            widths = [col_offsets[1] - col_offsets[0] - 8, col_offsets[2] - col_offsets[1] - 8, col_offsets[3] - col_offsets[2] - 8, list_w - col_offsets[3] - 20]

            for value, offset, max_w in zip(values, col_offsets, widths):
                text = self._fit_text(value, max(20, max_w))
                text_surface = row_font.render(text, True, (245, 245, 245))
                self.screen.blit(text_surface, (list_x + offset, row_y))

        if not people_list:
            empty_text = row_font.render("No visible people in this province.", True, (235, 235, 235))
            self.screen.blit(empty_text, (list_x + 16, header_y + 36))

        if len(people_list) > max_rows:
            scrollbar_x = list_x + list_w - 12
            scrollbar_top = header_y + 30
            scrollbar_h = max_rows * row_height
            scrollbar_w = 8

            self._people_overlay_scrollbar_rect = pygame.Rect(scrollbar_x, scrollbar_top, scrollbar_w, scrollbar_h)
            pygame.draw.rect(self.screen, (50, 50, 50), self._people_overlay_scrollbar_rect)

            thumb_h = max(10, int((max_rows / len(people_list)) * scrollbar_h))
            thumb_pos = int((start_idx / max(1, len(people_list) - max_rows)) * (scrollbar_h - thumb_h))
            self._people_overlay_scrollbar_thumb_rect = pygame.Rect(scrollbar_x, scrollbar_top + thumb_pos, scrollbar_w, thumb_h)
            pygame.draw.rect(self.screen, (110, 110, 110), self._people_overlay_scrollbar_thumb_rect)
            self._people_overlay_scrollbar_range = (len(people_list), max_rows)
        else:
            self._people_overlay_scrollbar_rect = None
            self._people_overlay_scrollbar_thumb_rect = None
            self._people_overlay_scrollbar_range = (0, 0)

    def _get_unit_portrait(self, unit, size: int = 85) -> Optional[pygame.Surface]:
        unit_type = str(getattr(unit, "name", "")).strip().lower()
        if not unit_type:
            return None

        cache_key = f"{unit_type}:{size}.jpg"
        if cache_key in self._unit_portrait_cache:
            return self._unit_portrait_cache[cache_key]

        image = self.load_image(f"picture/{unit_type}.jpg")
        if image is None:
            self._unit_portrait_cache[cache_key] = None
            return None

        scaled = pygame.transform.smoothscale(image, (size, size))
        self._unit_portrait_cache[cache_key] = scaled
        return scaled

    def _draw_ui_overlay(self) -> None:
        """Draw top UI bar and simulation time text above map layers."""
        screen_w, _ = self.screen.get_size()
        bar_w = 170
        bar_x = 0
        if self.rbar_image is not None:
            bar_w = self.rbar_image.get_width()
            bar_x = max(0, screen_w - bar_w)
            self.screen.blit(self.rbar_image, (bar_x, 0))

        panel_padding = 10
        content_x = bar_x + panel_padding
        content_w = max(80, bar_w - (panel_padding * 2))

        def blit_fitted_text(text: str, y: int) -> None:
            fitted = self._fit_text(text, content_w)
            if fitted:
                self.screen.blit(self.ui_font.render(fitted, True, text_color), (content_x, y))

        sim = getattr(self.game, "simulation", None)
        if sim is None:
            return

        state = sim.get_state_snapshot()
        year = state.get("current_year", 0)
        month = state.get("current_month", 0)
        day = state.get("current_day", 0)
        hour = state.get("current_hour", 0)
        speed = state.get("speed_multiplier", 1.0)
        paused = state.get("paused", False)
        status = "PAUSED" if paused else "RUNNING"

        status_text = f"Status: {status}"
        time_text = f"Time: {year:04d}/{month:02d}/{day:02d}-{hour:02d}:00"
        speed_text = f"Speed: x{speed:.1f}"

        text_color = (245, 245, 245)
        line_h = self.ui_font.get_linesize()
        top_y = max(4, line_h // 4)
        blit_fitted_text(status_text, top_y)
        blit_fitted_text(time_text, top_y + line_h)
        blit_fitted_text(speed_text, top_y + line_h * 2)

        selected_id = getattr(self.game, "unit_selected", 0)
        selected_train_id = getattr(self.game, "train_selected", None)
        selected_province_id = getattr(self.game, "province_selected", 0)
        panel_x = content_x
        panel_y = top_y + line_h * 3 + 12
        preview_size = max(90, min(160, content_w))
        line_h = self.ui_font.get_linesize()

        if selected_train_id is not None:
            train = getattr(self.game, "trains", {}).get(str(selected_train_id))
            if train is not None:
                preview_rect = pygame.Rect(panel_x, panel_y, preview_size, preview_size)
                fill = self._shade_color(self._get_train_color(train), 0.8)
                pygame.draw.rect(self.screen, fill, preview_rect, border_radius=8)
                pygame.draw.rect(self.screen, (30, 30, 30), preview_rect, 2, border_radius=8)

                title_font = pygame.font.Font(None, max(28, preview_size // 3))
                self.screen.blit(title_font.render("TRAIN", True, (20, 20, 20)), (panel_x + 8, panel_y + 8))

                train_status = self._get_train_status_label(getattr(train, "status", 0))
                route = list(getattr(train, "route", []))
                loaded_units = list(getattr(train, "loaded_units", []))

                data_y = panel_y + preview_size + 6
                blit_fitted_text(f"Train: {getattr(train, 'id', '?')}", data_y)
                blit_fitted_text(f"Nation: {getattr(train, 'nation', '-')}", data_y + line_h)
                blit_fitted_text(f"Prov: {getattr(train, 'location', '-')}", data_y + (line_h * 2))
                blit_fitted_text(f"Status: {train_status}", data_y + (line_h * 3))
                blit_fitted_text(f"Health: {getattr(train, 'health', 0)}", data_y + (line_h * 4))
                blit_fitted_text(f"Speed: {getattr(train, 'speed', 0)}", data_y + (line_h * 5))
                blit_fitted_text(f"Suply: {getattr(train, 'suply', 0)}", data_y + (line_h * 6))
                blit_fitted_text(f"Ammo: {getattr(train, 'ammo', 0)}", data_y + (line_h * 7))
                blit_fitted_text(f"Lvl: {getattr(train, 'lvl', 1)}", data_y + (line_h * 8))
                blit_fitted_text(f"Loaded Units: {len(loaded_units)}", data_y + (line_h * 9))
                next_stop = route[0] if route else "-"
                blit_fitted_text(f"Next Stop: {next_stop}", data_y + (line_h * 10))

                if self.can_edit_train_status(train):
                    self._draw_train_status_panel(train, panel_x, data_y + (line_h * 11) + 8, content_w)
                else:
                    self._unit_status_dropdown_rects = []
                    self._unit_status_combobox_rect = None
                    self._unit_status_dropdown_open = False
                self._unit_target_size_input_rect = None
                self._unit_target_size_input_active = False
                self._people_button_rect = None
                return

        unit = self._find_unit_by_id(selected_id) if selected_id else None
        if unit is not None:
            portrait = self._get_unit_portrait(unit, size=preview_size)
            if portrait is not None:
                self.screen.blit(portrait, (panel_x, panel_y))

            blit_fitted_text(f"{unit.name}", panel_y - 12)

            data_y = panel_y + preview_size + 6
            blit_fitted_text(f"Unit: {unit.id}", data_y)
            blit_fitted_text(f"Leader ID: {getattr(unit, 'leader_id', 0)}", data_y + line_h)
            blit_fitted_text(f"Nation: {unit.nation}", data_y + (line_h * 2))
            blit_fitted_text(f"Prov: {unit.location}", data_y + (line_h * 3))
            blit_fitted_text(f"Home: {getattr(unit, 'home', '-')}", data_y + (line_h * 4))
            blit_fitted_text(f"Soldiers: {getattr(unit, 'soldiers', 0)}", data_y + (line_h * 5))
            blit_fitted_text(f"Target Size: {getattr(unit, 'targetsize', getattr(unit, 'soldiers', 0))}", data_y + (line_h * 6))
            blit_fitted_text(f"Status: {self._get_status_label(getattr(unit, 'status', 1))}", data_y + (line_h * 7))
            blit_fitted_text(f"Morale: {getattr(unit, 'morale', 100)}", data_y + (line_h * 8))
            blit_fitted_text(f"Org: {getattr(unit, 'organization', 100)}", data_y + (line_h * 9))
            blit_fitted_text(f"Supply: {getattr(unit, 'suply', 0)}", data_y + (line_h * 10))
            blit_fitted_text(f"Ammo: {getattr(unit, 'ammo', 0)}", data_y + (line_h * 11))
            blit_fitted_text(f"Fuel: {getattr(unit, 'fuel', 0)}", data_y + (line_h * 12))
            blit_fitted_text(f"Sup Rate: {getattr(unit, 'suply_consumption', 0)}", data_y + (line_h * 13))
            blit_fitted_text(f"Ammo Rate: {getattr(unit, 'ammo_consumption', 0)}", data_y + (line_h * 14))
            blit_fitted_text(f"Fuel Rate: {getattr(unit, 'suply_fuel_consumption', 0)}", data_y + (line_h * 15))
            blit_fitted_text(f"Vehicles: {getattr(unit, 'transport_V', 0)}", data_y + (line_h * 16))
            blit_fitted_text(f"Horse Wagons: {getattr(unit, 'transport_H', 0)}", data_y + (line_h * 17))
            blit_fitted_text(f"Logistic value: {getattr(unit, 'logistics_value', 0)}", data_y + (line_h * 18))
            if self.can_edit_unit_status(unit):
                next_y = self._draw_unit_target_size_panel(unit, panel_x, data_y + (line_h * 19) + 6, content_w)
                self._draw_unit_status_panel(unit, panel_x, next_y + 8, content_w, self.screen.get_height())
            else:
                self._unit_status_dropdown_rects = []
                self._unit_status_combobox_rect = None
                self._unit_status_dropdown_open = False
                self._unit_target_size_input_rect = None
                self._unit_target_size_input_active = False
            return

        self._unit_status_dropdown_rects = []
        self._unit_status_combobox_rect = None
        self._unit_status_dropdown_open = False
        self._unit_target_size_input_rect = None
        self._unit_target_size_input_active = False
        self._province_create_unit_button_rect = None
        self._province_create_logistics_button_rect = None
        self._province_logistics_hub_checkbox_rect = None

        if not selected_province_id:
            self._people_button_rect = None
            self._province_create_unit_button_rect = None
            self._province_create_logistics_button_rect = None
            self._province_logistics_hub_checkbox_rect = None
            return

        province = self.game.map.get_province_by_id(selected_province_id)
        if province is None:
            self._province_create_unit_button_rect = None
            self._province_create_logistics_button_rect = None
            self._province_logistics_hub_checkbox_rect = None
            return

        preview_rect = pygame.Rect(panel_x, panel_y, preview_size, preview_size)
        pygame.draw.rect(self.screen, (28, 32, 36), preview_rect)
        pygame.draw.rect(self.screen, (90, 90, 90), preview_rect, 1)
        placeholder = self.ui_font.render("No image", True, (190, 190, 190))
        placeholder_rect = placeholder.get_rect(center=preview_rect.center)
        self.screen.blit(placeholder, placeholder_rect)

        province_name = str(province.get("name") or f"Province {province.get('id', '?')}")
        blit_fitted_text(province_name, panel_y - 12)

        data_y = panel_y + preview_size + 6
        owner = province.get("owner", "-")
        controler = province.get("controler", "-")
        terrain = province.get("terrain", "-")
        province_obj = self.game.map.get_province_object_by_id(selected_province_id)

        blit_fitted_text(f"Owner: {owner}", data_y)
        blit_fitted_text(f"Ctrl: {controler}", data_y + line_h)
        blit_fitted_text(f"Terrain: {terrain}", data_y + (line_h * 2))
        blit_fitted_text(f"Nearby: {len(province.get('nearby_provinces', []))}", data_y + (line_h * 3))

        if province_obj is None:
            self._province_create_unit_button_rect = None
            self._province_create_logistics_button_rect = None
            self._province_logistics_hub_checkbox_rect = None
            return

        blit_fitted_text(f"Pop: {province_obj.population}", data_y + (line_h * 4))
        blit_fitted_text(f"Current Recruits: {province_obj.province_recruits}", data_y + (line_h * 5))
        blit_fitted_text(f"Max Recruits: {province_obj.province_recrutable}", data_y + (line_h * 6))

        blit_fitted_text(f"Soldiers: {province_obj.province_soldiers}", data_y + (line_h * 10))
        blit_fitted_text(f"Buildings: {len(province_obj.buildings)}", data_y + (line_h * 11))
        blit_fitted_text(
            f"U Here/Home: {len(province_obj.units_in_here)}/{len(province_obj.units_from_here)}",
            data_y + (line_h * 12),
        )
        blit_fitted_text(
            f"Sup/Food/Fuel: {province_obj.suply}/{province_obj.food}/{province_obj.fuel}",
            data_y + (line_h * 13),
        )
        blit_fitted_text(f"Ammo: {province_obj.ammo}", data_y + (line_h * 14))

        can_toggle_hub = self.can_toggle_logistic_hub_in_selected_province(province, province_obj)
        hub_checked = bool(getattr(province_obj, "logistic_hub", False))
        checkbox_size = max(14, min(20, line_h + 2))
        checkbox_y = data_y + (line_h * 15) + 2

        if can_toggle_hub:
            self._province_logistics_hub_checkbox_rect = pygame.Rect(panel_x, checkbox_y, checkbox_size, checkbox_size)

            checkbox_fill = (70, 115, 70) if hub_checked else (58, 58, 58)
            checkbox_border = (145, 175, 145)
            pygame.draw.rect(self.screen, checkbox_fill, self._province_logistics_hub_checkbox_rect, border_radius=3)
            pygame.draw.rect(self.screen, checkbox_border, self._province_logistics_hub_checkbox_rect, 1, border_radius=3)

            if hub_checked:
                x0 = self._province_logistics_hub_checkbox_rect.left + 3
                y0 = self._province_logistics_hub_checkbox_rect.centery
                x1 = self._province_logistics_hub_checkbox_rect.left + 7
                y1 = self._province_logistics_hub_checkbox_rect.bottom - 4
                x2 = self._province_logistics_hub_checkbox_rect.right - 3
                y2 = self._province_logistics_hub_checkbox_rect.top + 4
                pygame.draw.lines(self.screen, (230, 245, 230), False, [(x0, y0), (x1, y1), (x2, y2)], 2)

            hub_label_surface = self.ui_font.render("Logistics Hub", True, (240, 240, 240))
            self.screen.blit(
                hub_label_surface,
                (self._province_logistics_hub_checkbox_rect.right + 6, checkbox_y + max(0, (checkbox_size - hub_label_surface.get_height()) // 2)),
            )
            btn_y = checkbox_y + checkbox_size + 10
        else:
            self._province_logistics_hub_checkbox_rect = None
            btn_y = data_y + (line_h * 15) + 10

        btn_w = max(80, min(130, content_w))
        btn_h = max(24, min(36, line_h * 2))
        btn_x = panel_x

        can_create = self.can_create_unit_in_selected_province(province, province_obj)

        self._province_create_unit_button_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        unit_fill = (70, 110, 75) if can_create else (80, 80, 80)
        unit_border = (145, 170, 145) if can_create else (120, 120, 120)
        pygame.draw.rect(self.screen, unit_fill, self._province_create_unit_button_rect, border_radius=4)
        pygame.draw.rect(self.screen, unit_border, self._province_create_unit_button_rect, 1, border_radius=4)
        create_label = self.ui_font.render("Create Unit", True, (245, 245, 245))
        self.screen.blit(create_label, create_label.get_rect(center=self._province_create_unit_button_rect.center))
        btn_y += btn_h + 6

        self._province_create_logistics_button_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        logi_fill = (110, 95, 60) if can_create else (80, 80, 80)
        logi_border = (175, 160, 125) if can_create else (120, 120, 120)
        pygame.draw.rect(self.screen, logi_fill, self._province_create_logistics_button_rect, border_radius=4)
        pygame.draw.rect(self.screen, logi_border, self._province_create_logistics_button_rect, 1, border_radius=4)
        logi_label = self.ui_font.render("Create Logi", True, (245, 245, 245))
        self.screen.blit(logi_label, logi_label.get_rect(center=self._province_create_logistics_button_rect.center))
        btn_y += btn_h + 6

        self._people_button_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

        if self.people_button_image is not None:
            btn_img = pygame.transform.smoothscale(self.people_button_image, (btn_w, btn_h))
            self.screen.blit(btn_img, (btn_x, btn_y))
        else:
            pygame.draw.rect(self.screen, (70, 95, 125), self._people_button_rect, border_radius=4)
            pygame.draw.rect(self.screen, (130, 145, 165), self._people_button_rect, 1, border_radius=4)
            label = self.ui_font.render("People", True, (245, 245, 245))
            self.screen.blit(label, label.get_rect(center=self._people_button_rect.center))

    def draw(self, debug_draw_connections: bool = True):
        # Clear the screen with a background color (e.g., white)
        self.screen.fill((255, 255, 255))

        # Draw base map if loaded
        self._draw_base_map()

        # Draw provinces transformed into screen space
        province_overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for province in self.game.map.get_all_provinces():
            fill_r, fill_g, fill_b = self._get_province_color(province)
            province_visible = self._province_is_visible_under_fog(province)
            border_color = (60, 60, 60) if province_visible else (30, 30, 30)
            fill_alpha = 90 if province_visible else 150
            if self.fog_of_war and not province_visible:
                fill_r, fill_g, fill_b = self._shade_color((fill_r, fill_g, fill_b), 0.35)

            for polygon in province["polygons"]:
                transformed = [self.world_to_screen(x, y) for x, y in polygon]
                pygame.draw.polygon(province_overlay, (fill_r, fill_g, fill_b, fill_alpha), transformed)
                pygame.draw.polygon(self.screen, border_color, transformed, 1)
        self.screen.blit(province_overlay, (0, 0))

        # Draw nearby province connections on top if enabled
        if debug_draw_connections:
            self.draw_nearby_connections()

        # Draw rails above debug nearby lines so they remain visible.
        self.draw_rails()

        # Draw trains as separate markers.
        self.draw_trains()

        # Draw units on top of everything
        self.draw_units()

        # Draw UI on top of all world elements
        self._draw_ui_overlay()
        self._draw_people_overlay()

        if getattr(self.game, "_drag_select_active", False):
            start = getattr(self.game, "_drag_select_start", None)
            current = getattr(self.game, "_drag_select_current", None)
            moved = getattr(self.game, "_drag_select_moved", False)
            if start is not None and current is not None and moved:
                left = min(start[0], current[0])
                top = min(start[1], current[1])
                width = abs(current[0] - start[0])
                height = abs(current[1] - start[1])
                rect = pygame.Rect(left, top, width, height)
                if rect.width > 0 and rect.height > 0:
                    fill = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                    fill.fill((120, 175, 255, 45))
                    self.screen.blit(fill, rect.topleft)
                    pygame.draw.rect(self.screen, (120, 175, 255), rect, 1)

        # Update the display
        pygame.display.flip()
