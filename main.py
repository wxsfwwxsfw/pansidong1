import json
import math
import os
import sys
import traceback
import webbrowser
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

import pygame


SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FPS = 60
MOVE_SPEED = 220  # pixels per second
ANIM_FPS = 10
MAP_RENDER_SCALE = 1.0
PLAYER_SCALE = 1.15
PLAYER_BRIGHTNESS = 0.8
WEATHER_TINT = (188, 208, 236, 10)  # very light cool air tint
PLAYER_COLLIDER_WIDTH_RATIO = 0.12
PLAYER_COLLIDER_HEIGHT_RATIO = 0.10
PLAYER_COLLIDER_FOOT_OFFSET_RATIO = 0.28
SHOW_TILE_COORDS = False
TILE_COORD_FONT_SIZE = 15
SHOW_PLAYER_STEP_COORD = True
GRID_MOVE_STEP_PIXELS = 20

ASSET_DIR = Path(__file__).parent / "assets"
MAP_DIR = ASSET_DIR / "map"
PLAYER_PATH = ASSET_DIR / "player" / "player.png"
MENU_BG_PATH = ASSET_DIR / "bg" / "登陆背景.png"
MENU_FONT_CANDIDATES = (
    ASSET_DIR / "fonts" / "霞鹜文楷+Bold.ttf",
    ASSET_DIR / "fonts" / "scourceHanserifCN-Bold-2.oft",
    ASSET_DIR / "fonts" / "SourceHanSerifCN-Bold-2.otf",
)
MENU_ITEMS = ("开始游戏", "读取进度", "离开游戏", "加入QQ群")
QQ_GROUP_URL = "https://qm.qq.com/"
MENU_TEXT_X_RATIO = 0.846
MENU_TEXT_Y_RATIOS = (0.5785, 0.6835, 0.7885, 0.8935)
MENU_TEXT_BASELINE_OFFSET = 4

GID_MASK = 0x1FFFFFFF
BLOCKED_PROP_NAMES = {"blocked", "block", "solid", "collide", "collision"}
COLLISION_LAYER_NAMES = {"collision", "collider", "blocked", "obstacle", "碰撞", "阻挡"}
AUTO_BLOCK_TILESET_KEYWORDS = (
    "gutou",   # skull
    "shitou",  # stone
    "dongbi",  # cave wall
    "wall",
    "rock",
    "skull",
)
TORCH_TILESET_KEYWORDS = ("huoba", "torch")


def load_image(path: Path) -> pygame.Surface:
    if not path.exists():
        raise FileNotFoundError(f"Missing asset: {path}")
    return pygame.image.load(path.as_posix()).convert_alpha()


def find_first_map_file() -> Path:
    explicit_tu1 = MAP_DIR / "tu1" / "tu1.json"
    if explicit_tu1.exists():
        return explicit_tu1

    preferred = [
        MAP_DIR / "ine" / "JSON",
        MAP_DIR / "tu1",
        MAP_DIR / "one",
        MAP_DIR,
    ]
    for folder in preferred:
        if not folder.exists():
            continue
        for pattern in ("*.tmj", "*.json"):
            candidates = sorted(folder.glob(pattern))
            if candidates:
                return candidates[0]

    recursive = sorted(
        [*MAP_DIR.rglob("*.tmj"), *MAP_DIR.rglob("*.json")]
    )
    if recursive:
        return recursive[0]

    raise FileNotFoundError(f"No Tiled JSON file found under: {MAP_DIR}")


def resolve_source_path(map_file: Path, source: str) -> Path:
    raw = Path(source)
    candidates = [
        (map_file.parent / raw).resolve(),
        (MAP_DIR / raw).resolve(),
        (map_file.parent / raw.name).resolve(),
        (MAP_DIR / raw.name).resolve(),
    ]
    for c in candidates:
        if c.exists():
            return c

    by_name = next(map_file.parent.rglob(raw.name), None)
    if by_name is not None:
        return by_name
    by_name_global = next(MAP_DIR.rglob(raw.name), None)
    if by_name_global is not None:
        return by_name_global

    raise FileNotFoundError(f"Cannot resolve tileset source '{source}'")


def resolve_image_path(base_dir: Path, image_source: str) -> Path:
    raw = Path(image_source)
    candidates = [
        (base_dir / raw).resolve(),
        (base_dir / raw.name).resolve(),
        (base_dir / "tiles" / raw.name).resolve(),
        (ASSET_DIR / raw.name).resolve(),
        (ASSET_DIR / "bg" / raw.name).resolve(),
        (ASSET_DIR / "map" / raw.name).resolve(),
        (ASSET_DIR / "map" / "one" / raw.name).resolve(),
        (ASSET_DIR / "map" / "tu1" / raw.name).resolve(),
    ]

    for c in candidates:
        if c.exists():
            return c

    by_name = next(base_dir.rglob(raw.name), None)
    if by_name is not None:
        return by_name
    by_name_global = next(MAP_DIR.rglob(raw.name), None)
    if by_name_global is not None:
        return by_name_global

    raise FileNotFoundError(
        f"Cannot resolve local tileset image '{image_source}' from '{base_dir}'"
    )


@dataclass
class TileLayer:
    data: list[int]
    width: int
    height: int
    visible: bool


class TiledMap:
    def __init__(self, map_path: Path):
        self.map_path = map_path
        with map_path.open("r", encoding="utf-8") as f:
            content = json.load(f)

        self.map_width = int(content["width"])
        self.map_height = int(content["height"])
        self.tile_width = int(content["tilewidth"])
        self.tile_height = int(content["tileheight"])
        self.pixel_width = self.map_width * self.tile_width
        self.pixel_height = self.map_height * self.tile_height

        self.layers: list[TileLayer] = []
        self.collision_layers: list[TileLayer] = []
        for layer in content.get("layers", []):
            if layer.get("type") != "tilelayer":
                continue
            tile_layer = TileLayer(
                data=list(layer.get("data", [])),
                width=int(layer.get("width", self.map_width)),
                height=int(layer.get("height", self.map_height)),
                visible=bool(layer.get("visible", True)),
            )
            self.layers.append(tile_layer)
            layer_name = str(layer.get("name", "")).strip().lower()
            if layer_name in COLLISION_LAYER_NAMES:
                self.collision_layers.append(tile_layer)

        self.tiles: dict[int, pygame.Surface] = {}
        self.scaled_tiles_cache: dict[float, dict[int, pygame.Surface]] = {}
        self.blocked_gids: set[int] = set()
        self.blocked_sprite_rects: list[pygame.Rect] = []
        self.coord_text_cache: dict[str, pygame.Surface] = {}
        self.torch_gids: set[int] = set()
        self._load_tilesets(content.get("tilesets", []))
        self._build_blocked_sprite_rects()

    def _load_tilesets(self, tilesets: list[dict]) -> None:
        for ts in tilesets:
            first_gid = int(ts["firstgid"])
            source = ts.get("source")
            if source:
                tsx_path = resolve_source_path(self.map_path, source)
                tree = ET.parse(tsx_path)
                root = tree.getroot()

                tile_w = int(root.attrib.get("tilewidth", self.tile_width))
                tile_h = int(root.attrib.get("tileheight", self.tile_height))
                tile_count = int(root.attrib.get("tilecount", "1"))
                columns = int(root.attrib.get("columns", "1"))
                ts_name = root.attrib.get("name", "")

                image_node = root.find("image")
                if image_node is None:
                    continue
                image_source = image_node.attrib["source"]
                image_path = resolve_image_path(tsx_path.parent, image_source)
                sheet = load_image(image_path)

                for local_id in range(tile_count):
                    col = local_id % columns
                    row = local_id // columns
                    rect = pygame.Rect(col * tile_w, row * tile_h, tile_w, tile_h)
                    if (
                        rect.right > sheet.get_width()
                        or rect.bottom > sheet.get_height()
                    ):
                        continue
                    self.tiles[first_gid + local_id] = sheet.subsurface(rect).copy()
                self._collect_blocked_from_tsx(root, first_gid)
                self._collect_blocked_by_tileset_name(first_gid, tile_count, ts_name)
                self._collect_torch_by_tileset_name(first_gid, tile_count, ts_name)
                continue

            image_source = ts.get("image")
            if not image_source:
                continue

            tile_w = int(ts.get("tilewidth", self.tile_width))
            tile_h = int(ts.get("tileheight", self.tile_height))
            tile_count = int(ts.get("tilecount", "1"))
            columns = int(ts.get("columns", "1"))
            ts_name = str(ts.get("name", ""))
            if columns <= 0:
                columns = 1

            image_path = resolve_image_path(self.map_path.parent, image_source)
            sheet = load_image(image_path)

            for local_id in range(tile_count):
                col = local_id % columns
                row = local_id // columns
                rect = pygame.Rect(col * tile_w, row * tile_h, tile_w, tile_h)
                if rect.right > sheet.get_width() or rect.bottom > sheet.get_height():
                    continue
                self.tiles[first_gid + local_id] = sheet.subsurface(rect).copy()
            self._collect_blocked_from_json_tileset(ts, first_gid)
            self._collect_blocked_by_tileset_name(first_gid, tile_count, ts_name)
            self._collect_torch_by_tileset_name(first_gid, tile_count, ts_name)

    def _collect_blocked_by_tileset_name(
        self,
        first_gid: int,
        tile_count: int,
        tileset_name: str,
    ) -> None:
        name = tileset_name.strip().lower()
        if not name:
            return
        if any(keyword in name for keyword in AUTO_BLOCK_TILESET_KEYWORDS):
            for local_id in range(tile_count):
                self.blocked_gids.add(first_gid + local_id)

    def _collect_torch_by_tileset_name(
        self,
        first_gid: int,
        tile_count: int,
        tileset_name: str,
    ) -> None:
        name = tileset_name.strip().lower()
        if not name:
            return
        if any(keyword in name for keyword in TORCH_TILESET_KEYWORDS):
            for local_id in range(tile_count):
                self.torch_gids.add(first_gid + local_id)

    def _collect_blocked_from_json_tileset(self, ts: dict, first_gid: int) -> None:
        for tile_info in ts.get("tiles", []):
            local_id = int(tile_info.get("id", -1))
            if local_id < 0:
                continue
            if self._has_blocked_property(tile_info.get("properties", [])):
                self.blocked_gids.add(first_gid + local_id)

    def _collect_blocked_from_tsx(self, root: ET.Element, first_gid: int) -> None:
        for tile_node in root.findall("tile"):
            local_id = int(tile_node.attrib.get("id", "-1"))
            if local_id < 0:
                continue
            properties = tile_node.find("properties")
            if properties is None:
                continue
            prop_nodes = properties.findall("property")
            if self._has_blocked_property_xml(prop_nodes):
                self.blocked_gids.add(first_gid + local_id)

    @staticmethod
    def _property_value_truthy(value: str) -> bool:
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def _has_blocked_property(self, properties: list[dict]) -> bool:
        for prop in properties:
            name = str(prop.get("name", "")).strip().lower()
            if name not in BLOCKED_PROP_NAMES:
                continue
            if "value" not in prop:
                return True
            value = prop.get("value")
            if isinstance(value, bool):
                return value
            return self._property_value_truthy(str(value))
        return False

    def _has_blocked_property_xml(self, properties: list[ET.Element]) -> bool:
        for prop in properties:
            name = prop.attrib.get("name", "").strip().lower()
            if name not in BLOCKED_PROP_NAMES:
                continue
            if "value" not in prop.attrib:
                return True
            return self._property_value_truthy(prop.attrib["value"])
        return False

    def is_blocked_cell(self, col: int, row: int) -> bool:
        if col < 0 or row < 0 or col >= self.map_width or row >= self.map_height:
            return True
        for layer in self.collision_layers:
            idx = row * layer.width + col
            if 0 <= idx < len(layer.data) and (layer.data[idx] & GID_MASK) != 0:
                return True
        for layer in self.layers:
            idx = row * layer.width + col
            if idx < 0 or idx >= len(layer.data):
                continue
            gid = layer.data[idx] & GID_MASK
            if gid in self.blocked_gids:
                return True
        return False

    def _build_blocked_sprite_rects(self) -> None:
        rects: list[pygame.Rect] = []
        for layer in self.layers:
            if not layer.visible:
                continue
            for row in range(layer.height):
                for col in range(layer.width):
                    idx = row * layer.width + col
                    if idx < 0 or idx >= len(layer.data):
                        continue
                    gid = layer.data[idx] & GID_MASK
                    if gid == 0 or gid not in self.blocked_gids:
                        continue
                    tile = self.tiles.get(gid)
                    tile_w = tile.get_width() if tile is not None else self.tile_width
                    tile_h = tile.get_height() if tile is not None else self.tile_height
                    x = col * self.tile_width
                    y = (row + 1) * self.tile_height - tile_h
                    rects.append(pygame.Rect(x, y, tile_w, tile_h))
        self.blocked_sprite_rects = rects

    def is_blocked_point(self, x: float, y: float) -> bool:
        col = int(x // self.tile_width)
        row = int(y // self.tile_height)
        if self.is_blocked_cell(col, row):
            return True
        px = round(x)
        py = round(y)
        for rect in self.blocked_sprite_rects:
            if rect.collidepoint(px, py):
                return True
        return False

    def can_move_to(self, x: float, y: float, half_w: int, half_h: int) -> bool:
        sample_points = [
            (x - half_w, y - half_h),
            (x + half_w, y - half_h),
            (x - half_w, y + half_h),
            (x + half_w, y + half_h),
        ]
        for px, py in sample_points:
            if self.is_blocked_point(px, py):
                return False
        return True

    def _get_coord_label(self, font: pygame.font.Font, text: str) -> pygame.Surface:
        cached = self.coord_text_cache.get(text)
        if cached is not None:
            return cached
        label = font.render(text, True, (220, 245, 255))
        self.coord_text_cache[text] = label
        return label

    def draw_tile_coordinates(
        self,
        surface: pygame.Surface,
        camera_x: float,
        camera_y: float,
        font: pygame.font.Font,
        scale: float = 1.0,
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> None:
        draw_tile_w = max(1, round(self.tile_width * scale))
        draw_tile_h = max(1, round(self.tile_height * scale))
        world_view_w = surface.get_width() / scale
        world_view_h = surface.get_height() / scale
        start_col = max(0, int(camera_x // self.tile_width))
        end_col = min(
            self.map_width - 1,
            int((camera_x + world_view_w) // self.tile_width) + 1,
        )
        start_row = max(0, int(camera_y // self.tile_height))
        end_row = min(
            self.map_height - 1,
            int((camera_y + world_view_h) // self.tile_height) + 1,
        )
        for row in range(start_row, end_row + 1):
            for col in range(start_col, end_col + 1):
                x = round((col * self.tile_width - camera_x) * scale + offset_x)
                y = round((row * self.tile_height - camera_y) * scale + offset_y)
                rect = pygame.Rect(x, y, draw_tile_w, draw_tile_h)
                pygame.draw.rect(surface, (80, 125, 170), rect, width=1)
                label = self._get_coord_label(font, f"{col},{row}")
                label_rect = label.get_rect(center=rect.center)
                shadow_rect = label_rect.move(1, 1)
                surface.blit(font.render(f"{col},{row}", True, (18, 24, 28)), shadow_rect)
                surface.blit(label, label_rect)

    def _get_scaled_tiles(self, scale: float) -> dict[int, pygame.Surface]:
        key = round(scale, 4)
        cached = self.scaled_tiles_cache.get(key)
        if cached is not None:
            return cached

        scaled: dict[int, pygame.Surface] = {}
        for gid, tile in self.tiles.items():
            target_w = max(1, round(tile.get_width() * scale))
            target_h = max(1, round(tile.get_height() * scale))
            if tile.get_width() == target_w and tile.get_height() == target_h:
                scaled[gid] = tile
            else:
                scaled[gid] = pygame.transform.smoothscale(tile, (target_w, target_h))

        self.scaled_tiles_cache[key] = scaled
        return scaled

    def draw(
        self,
        surface: pygame.Surface,
        camera_x: float,
        camera_y: float,
        scale: float = 1.0,
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> None:
        draw_tile_w = max(1, round(self.tile_width * scale))
        draw_tile_h = max(1, round(self.tile_height * scale))
        tiles_for_draw = self.tiles if scale == 1.0 else self._get_scaled_tiles(scale)
        world_view_w = surface.get_width() / scale
        world_view_h = surface.get_height() / scale

        start_col = max(0, int(camera_x // self.tile_width))
        end_col = min(
            self.map_width - 1,
            int((camera_x + world_view_w) // self.tile_width) + 1,
        )
        start_row = max(0, int(camera_y // self.tile_height))
        end_row = min(
            self.map_height - 1,
            int((camera_y + world_view_h) // self.tile_height) + 1,
        )

        for layer in self.layers:
            if not layer.visible:
                continue
            for row in range(start_row, end_row + 1):
                for col in range(start_col, end_col + 1):
                    idx = row * layer.width + col
                    if idx < 0 or idx >= len(layer.data):
                        continue
                    gid_raw = layer.data[idx]
                    if gid_raw == 0:
                        continue
                    gid = gid_raw & GID_MASK
                    tile = tiles_for_draw.get(gid)
                    if tile is None:
                        continue
                    # Match Tiled rule: tile bottom aligns to grid cell bottom.
                    x = round((col * self.tile_width - camera_x) * scale + offset_x)
                    y = round(
                        ((row + 1) * self.tile_height - camera_y) * scale
                        - tile.get_height()
                        + offset_y
                    )
                    surface.blit(tile, (x, y))

    def draw_torch_glow(
        self,
        surface: pygame.Surface,
        camera_x: float,
        camera_y: float,
        scale: float = 1.0,
        offset_x: int = 0,
        offset_y: int = 0,
        time_seconds: float = 0.0,
    ) -> None:
        if not self.torch_gids:
            return
        world_view_w = surface.get_width() / scale
        world_view_h = surface.get_height() / scale
        start_col = max(0, int(camera_x // self.tile_width))
        end_col = min(
            self.map_width - 1,
            int((camera_x + world_view_w) // self.tile_width) + 1,
        )
        start_row = max(0, int(camera_y // self.tile_height))
        end_row = min(
            self.map_height - 1,
            int((camera_y + world_view_h) // self.tile_height) + 1,
        )
        glow_layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pulse = 0.94 + 0.06 * (1 + math.sin(time_seconds * 7.3)) * 0.5
        base_radius = round(36 * scale * pulse)
        inner_radius = max(8, round(base_radius * 0.45))
        for layer in self.layers:
            if not layer.visible:
                continue
            for row in range(start_row, end_row + 1):
                for col in range(start_col, end_col + 1):
                    idx = row * layer.width + col
                    if idx < 0 or idx >= len(layer.data):
                        continue
                    gid = layer.data[idx] & GID_MASK
                    if gid not in self.torch_gids:
                        continue
                    # Align glow center to the red flame core on the wall torch sprite.
                    fx = round((col * self.tile_width - camera_x) * scale + offset_x + 34 * scale)
                    fy = round((row * self.tile_height - camera_y) * scale + offset_y + 44 * scale)
                    pygame.draw.circle(glow_layer, (255, 140, 50, 12), (fx, fy), base_radius)
                    pygame.draw.circle(glow_layer, (255, 190, 110, 22), (fx, fy), inner_radius)
        surface.blit(glow_layer, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)


def get_map_offset(
    map_pixel_width: int,
    map_pixel_height: int,
    view_width: int,
    view_height: int,
    map_scale: float = 1.0,
) -> tuple[int, int]:
    draw_w = round(map_pixel_width * map_scale)
    draw_h = round(map_pixel_height * map_scale)
    offset_x = max(0, (view_width - draw_w) // 2)
    offset_y = max(0, (view_height - draw_h) // 2)
    return offset_x, offset_y


def build_animation(sheet: pygame.Surface) -> dict[str, list[pygame.Surface]]:
    cols = 8
    rows = 8
    frame_w = sheet.get_width() // cols
    frame_h = sheet.get_height() // rows

    grid: list[list[pygame.Surface]] = []
    for r in range(rows):
        row_frames: list[pygame.Surface] = []
        for c in range(cols):
            rect = pygame.Rect(c * frame_w, r * frame_h, frame_w, frame_h)
            row_frames.append(sheet.subsurface(rect).copy())
        grid.append(row_frames)

    # Common RPG spritesheet layout fallback:
    # down: row 0, left: row 1, right: row 2, up: row 3
    mapping = {
        "down": grid[0],
        "left": grid[1],
        "right": grid[2],
        "up": grid[3],
    }
    return mapping


def apply_player_tone(
    anim: dict[str, list[pygame.Surface]],
    brightness: float,
) -> dict[str, list[pygame.Surface]]:
    mul = max(0, min(255, round(255 * brightness)))
    toned: dict[str, list[pygame.Surface]] = {}
    for direction, frames in anim.items():
        toned_frames: list[pygame.Surface] = []
        for frame in frames:
            toned_frame = frame.copy()
            toned_frame.fill((mul, mul, mul, 255), special_flags=pygame.BLEND_RGBA_MULT)
            toned_frames.append(toned_frame)
        toned[direction] = toned_frames
    return toned


def scale_animation(
    anim: dict[str, list[pygame.Surface]],
    scale: float,
) -> dict[str, list[pygame.Surface]]:
    if abs(scale - 1.0) < 1e-4:
        return anim
    scaled_anim: dict[str, list[pygame.Surface]] = {}
    for direction, frames in anim.items():
        out_frames: list[pygame.Surface] = []
        for frame in frames:
            w = max(1, round(frame.get_width() * scale))
            h = max(1, round(frame.get_height() * scale))
            out_frames.append(pygame.transform.scale(frame, (w, h)))
        scaled_anim[direction] = out_frames
    return scaled_anim


def draw_weather_effects(
    surface: pygame.Surface,
    time_seconds: float,
) -> None:
    # Very light atmospheric layer: moving mist bands and dust motes.
    w, h = surface.get_size()
    weather = pygame.Surface((w, h), pygame.SRCALPHA)
    weather.fill(WEATHER_TINT)

    # Wide fog bands drifting left/right.
    for i in range(4):
        y = round(h * (0.2 + i * 0.19))
        drift = math.sin(time_seconds * (0.18 + i * 0.07) + i * 1.7)
        x = round(w * (0.5 + drift * 0.12))
        band_w = round(w * (0.9 - i * 0.12))
        band_h = round(h * 0.12)
        rect = pygame.Rect(0, 0, band_w, band_h)
        rect.center = (x, y)
        pygame.draw.ellipse(weather, (205, 220, 242, 10), rect)

    # Subtle floating dust particles.
    particles = 44
    for i in range(particles):
        phase = time_seconds * (0.11 + (i % 7) * 0.013) + i * 0.91
        px = round((i * 137) % w + math.sin(phase * 1.7) * 18) % w
        py = round(((i * 89) % h + phase * 11) % h)
        r = 1 + (i % 2)
        a = 10 if i % 3 else 14
        pygame.draw.circle(weather, (220, 232, 252, a), (px, py), r)

    surface.blit(weather, (0, 0))


def draw_player_step_coordinate(
    surface: pygame.Surface,
    font: pygame.font.Font,
    world_x: float,
    world_y: float,
) -> None:
    coord_x = int(world_x // GRID_MOVE_STEP_PIXELS) + 1
    coord_y = int(world_y // GRID_MOVE_STEP_PIXELS) + 1
    coord_x = max(1, coord_x)
    coord_y = max(1, coord_y)
    text = f"坐标: {coord_x}.{coord_y}"
    shadow = font.render(text, True, (18, 22, 26))
    label = font.render(text, True, (238, 248, 255))
    shadow_rect = shadow.get_rect(topleft=(16, 16))
    label_rect = label.get_rect(topleft=(15, 15))
    surface.blit(shadow, shadow_rect)
    surface.blit(label, label_rect)


def find_spawn_position_bottom_right(
    tiled_map: TiledMap,
    half_w: int,
    half_h: int,
    foot_offset: int,
) -> tuple[float, float]:
    for row in range(tiled_map.map_height - 1, -1, -1):
        for col in range(tiled_map.map_width - 1, -1, -1):
            x = col * tiled_map.tile_width + tiled_map.tile_width * 0.5
            y = row * tiled_map.tile_height + tiled_map.tile_height * 0.5
            if tiled_map.can_move_to(x, y + foot_offset, half_w, half_h):
                return x, y
    fallback_x = tiled_map.pixel_width - max(half_w + 1, tiled_map.tile_width * 0.5)
    fallback_y = tiled_map.pixel_height - max(half_h + 1, tiled_map.tile_height * 0.5)
    return fallback_x, fallback_y


def load_menu_font(size: int) -> pygame.font.Font:
    for font_path in MENU_FONT_CANDIDATES:
        if font_path.exists():
            return pygame.font.Font(font_path.as_posix(), size)
    return pygame.font.Font(None, size)


def draw_menu_background(screen: pygame.Surface) -> pygame.Rect:
    view_w, view_h = screen.get_size()
    screen.fill((0, 0, 0))
    if MENU_BG_PATH.exists():
        raw = pygame.image.load(MENU_BG_PATH.as_posix()).convert()
        scale = min(view_w / raw.get_width(), view_h / raw.get_height())
        draw_w = max(1, round(raw.get_width() * scale))
        draw_h = max(1, round(raw.get_height() * scale))
        bg = pygame.transform.smoothscale(raw, (draw_w, draw_h))
        x = (view_w - draw_w) // 2
        y = (view_h - draw_h) // 2
        screen.blit(bg, (x, y))
        return pygame.Rect(x, y, draw_w, draw_h)

    screen.fill((18, 12, 10))
    return screen.get_rect()


def draw_menu_button(
    surface: pygame.Surface,
    text: str,
    center: tuple[int, int],
    hovered: bool,
    base_font: pygame.font.Font,
    hover_font: pygame.font.Font,
    button_size: tuple[int, int] = (520, 112),
    draw_panel: bool = True,
) -> pygame.Rect:
    button_w, button_h = button_size
    rect = pygame.Rect(0, 0, button_w, button_h)
    rect.center = center

    if draw_panel:
        panel = pygame.Surface((button_w, button_h), pygame.SRCALPHA)
        fill_color = (92, 44, 16, 220) if hovered else (70, 34, 12, 210)
        edge_color = (201, 140, 70, 240) if hovered else (154, 97, 44, 220)
        glow_color = (250, 184, 92, 70) if hovered else (180, 120, 50, 40)
        pygame.draw.rect(panel, fill_color, panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, edge_color, panel.get_rect(), width=4, border_radius=18)
        pygame.draw.rect(panel, glow_color, panel.get_rect().inflate(-12, -12), width=2, border_radius=14)
        surface.blit(panel, rect.topleft)

    font = hover_font if hovered else base_font
    text_surface = font.render(text, True, (246, 222, 180))
    text_shadow = font.render(text, True, (28, 15, 6))
    text_rect = text_surface.get_rect(center=(rect.centerx, rect.centery + MENU_TEXT_BASELINE_OFFSET))
    shadow_rect = text_rect.move(2, 2)
    surface.blit(text_shadow, shadow_rect)
    surface.blit(text_surface, text_rect)
    return rect


def run_login_menu(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
) -> str:
    base_font = load_menu_font(46)
    hover_font = load_menu_font(52)
    hint_font = load_menu_font(30)
    spacing = 146

    while True:
        clock.tick(FPS)
        bg_rect = draw_menu_background(screen)
        mouse_pos = pygame.mouse.get_pos()
        hovered_idx = -1
        view_w, view_h = screen.get_size()
        has_custom_bg = MENU_BG_PATH.exists()
        if has_custom_bg:
            center_x = bg_rect.left + round(bg_rect.width * MENU_TEXT_X_RATIO)
            y_positions = [
                bg_rect.top + round(bg_rect.height * ratio)
                for ratio in MENU_TEXT_Y_RATIOS
            ]
            button_w = max(220, round(bg_rect.width * 0.25))
            button_h = max(60, round(bg_rect.height * 0.09))
        else:
            spacing = 146
            total_h = (len(MENU_ITEMS) - 1) * spacing
            start_y = view_h // 2 - total_h // 2
            center_x = view_w // 2
            y_positions = [start_y + i * spacing for i in range(len(MENU_ITEMS))]
            button_w = 520
            button_h = 112
        button_centers = [(center_x, y) for y in y_positions]
        button_rects = []
        for center in button_centers:
            rect = pygame.Rect(0, 0, button_w, button_h)
            rect.center = center
            button_rects.append(rect)
        for i, rect in enumerate(button_rects):
            if rect.collidepoint(mouse_pos):
                hovered_idx = i

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "quit"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, rect in enumerate(button_rects):
                    if rect.collidepoint(event.pos):
                        label = MENU_ITEMS[i]
                        if label == "开始游戏":
                            return "start"
                        if label == "离开游戏":
                            return "quit"
                        if label == "加入QQ群":
                            webbrowser.open(QQ_GROUP_URL)
                        break

        for i, text in enumerate(MENU_ITEMS):
            draw_menu_button(
                screen,
                text,
                button_centers[i],
                hovered=(i == hovered_idx),
                base_font=base_font,
                hover_font=hover_font,
                button_size=(button_w, button_h),
                draw_panel=not has_custom_bg,
            )

        if hovered_idx >= 0:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
        else:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        if hovered_idx == MENU_ITEMS.index("读取进度"):
            hint = hint_font.render("读取进度功能待接入", True, (250, 228, 190))
            hint_rect = hint.get_rect(center=(view_w // 2, view_h - 70))
            screen.blit(hint, hint_rect)

        pygame.display.flip()


def main() -> None:
    # Force centered, windowed launch (not fullscreen).
    os.environ["SDL_VIDEO_CENTERED"] = "1"
    pygame.init()
    pygame.display.set_caption("Pygame Tiled Map Demo")
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), flags=0)
    clock = pygame.time.Clock()

    menu_action = run_login_menu(screen, clock)
    if menu_action != "start":
        pygame.quit()
        return

    try:
        map_file = find_first_map_file()
        tiled_map = TiledMap(map_file)
        player_sheet = load_image(PLAYER_PATH)
    except (FileNotFoundError, ET.ParseError, json.JSONDecodeError) as e:
        print(e)
        print("Check Tiled map/json/tsx/image paths under assets/map")
        pygame.quit()
        sys.exit(1)

    anim = build_animation(player_sheet)
    anim = scale_animation(anim, PLAYER_SCALE)
    anim = apply_player_tone(anim, PLAYER_BRIGHTNESS)
    coord_font = pygame.font.Font(None, TILE_COORD_FONT_SIZE)
    direction = "down"
    frame_idx = 0
    anim_timer = 0.0
    collision_half_w = max(6, round(anim["down"][0].get_width() * PLAYER_COLLIDER_WIDTH_RATIO))
    collision_half_h = max(6, round(anim["down"][0].get_height() * PLAYER_COLLIDER_HEIGHT_RATIO))
    collision_foot_offset = round(anim["down"][0].get_height() * PLAYER_COLLIDER_FOOT_OFFSET_RATIO)
    shadow_w = max(18, round(anim["down"][0].get_width() * 0.46))
    shadow_h = max(10, round(anim["down"][0].get_height() * 0.2))
    player_shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
    pygame.draw.ellipse(player_shadow, (0, 0, 0, 90), player_shadow.get_rect())

    x, y = find_spawn_position_bottom_right(
        tiled_map,
        collision_half_w,
        collision_half_h,
        collision_foot_offset,
    )
    x = round(x / GRID_MOVE_STEP_PIXELS) * GRID_MOVE_STEP_PIXELS
    y = round(y / GRID_MOVE_STEP_PIXELS) * GRID_MOVE_STEP_PIXELS

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        view_width, view_height = screen.get_size()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        keys = pygame.key.get_pressed()
        move_dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (
            keys[pygame.K_a] or keys[pygame.K_LEFT]
        )
        move_dy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (
            keys[pygame.K_w] or keys[pygame.K_UP]
        )
        moving = move_dx != 0 or move_dy != 0
        if moving:
            vec = pygame.Vector2(move_dx, move_dy)
            vec = vec.normalize() * MOVE_SPEED * dt
            target_x = x + vec.x
            collision_y = y + collision_foot_offset
            if tiled_map.can_move_to(target_x, collision_y, collision_half_w, collision_half_h):
                x = target_x
            target_y = y + vec.y
            if tiled_map.can_move_to(x, target_y + collision_foot_offset, collision_half_w, collision_half_h):
                y = target_y

            if abs(move_dy) > abs(move_dx):
                direction = "down" if move_dy > 0 else "up"
            else:
                direction = "right" if move_dx > 0 else "left"

            anim_timer += dt
            if anim_timer >= 1.0 / ANIM_FPS:
                anim_timer = 0.0
                frame_idx = (frame_idx + 1) % len(anim[direction])
        else:
            frame_idx = 0
            anim_timer = 0.0

        current = anim[direction][frame_idx]
        half_w = current.get_width() // 2
        half_h = current.get_height() // 2

        # Keep player inside map bounds.
        x = max(half_w, min(tiled_map.pixel_width - half_w, x))
        y = max(half_h, min(tiled_map.pixel_height - half_h, y))

        world_view_w = view_width / MAP_RENDER_SCALE
        world_view_h = view_height / MAP_RENDER_SCALE
        camera_x = max(0, min(max(0, tiled_map.pixel_width - world_view_w), x - world_view_w / 2))
        camera_y = max(0, min(max(0, tiled_map.pixel_height - world_view_h), y - world_view_h / 2))
        offset_x, offset_y = get_map_offset(
            tiled_map.pixel_width,
            tiled_map.pixel_height,
            view_width,
            view_height,
            MAP_RENDER_SCALE,
        )

        screen.fill((0, 0, 0))
        tiled_map.draw(screen, camera_x, camera_y, MAP_RENDER_SCALE, offset_x, offset_y)
        if SHOW_TILE_COORDS:
            tiled_map.draw_tile_coordinates(
                screen,
                camera_x,
                camera_y,
                coord_font,
                MAP_RENDER_SCALE,
                offset_x,
                offset_y,
            )
        if SHOW_PLAYER_STEP_COORD:
            draw_player_step_coordinate(
                screen,
                coord_font,
                x,
                y + collision_foot_offset,
            )

        player_center_x = round((x - camera_x) * MAP_RENDER_SCALE + offset_x)
        player_center_y = round((y - camera_y) * MAP_RENDER_SCALE + offset_y)
        shadow_rect = player_shadow.get_rect(
            center=(player_center_x, player_center_y + max(8, current.get_height() // 3))
        )
        screen.blit(player_shadow, shadow_rect)
        player_rect = current.get_rect(
            center=(player_center_x, player_center_y)
        )
        screen.blit(current, player_rect)
        draw_weather_effects(
            screen,
            pygame.time.get_ticks() / 1000.0,
        )

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    print("[BOOT] main.py is running")
    try:
        main()
    except Exception:
        traceback.print_exc()
        input("Press Enter to exit...")
