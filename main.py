import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

import pygame


SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FPS = 60
MOVE_SPEED = 220  # pixels per second
ANIM_FPS = 10
MAP_RENDER_SCALE = 0.8  # 100x100 tiles render as 80x80.

ASSET_DIR = Path(__file__).parent / "assets"
MAP_DIR = ASSET_DIR / "map"
PLAYER_PATH = ASSET_DIR / "player" / "player.png"

GID_MASK = 0x1FFFFFFF


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
        for layer in content.get("layers", []):
            if layer.get("type") != "tilelayer":
                continue
            self.layers.append(
                TileLayer(
                    data=list(layer.get("data", [])),
                    width=int(layer.get("width", self.map_width)),
                    height=int(layer.get("height", self.map_height)),
                    visible=bool(layer.get("visible", True)),
                )
            )

        self.tiles: dict[int, pygame.Surface] = {}
        self.scaled_tiles_cache: dict[float, dict[int, pygame.Surface]] = {}
        self._load_tilesets(content.get("tilesets", []))

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
                continue

            image_source = ts.get("image")
            if not image_source:
                continue

            tile_w = int(ts.get("tilewidth", self.tile_width))
            tile_h = int(ts.get("tileheight", self.tile_height))
            tile_count = int(ts.get("tilecount", "1"))
            columns = int(ts.get("columns", "1"))
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

        start_col = max(0, int(camera_x // self.tile_width))
        end_col = min(
            self.map_width - 1,
            int((camera_x + surface.get_width()) // self.tile_width) + 1,
        )
        start_row = max(0, int(camera_y // self.tile_height))
        end_row = min(
            self.map_height - 1,
            int((camera_y + surface.get_height()) // self.tile_height) + 1,
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


def main() -> None:
    # Force centered, windowed launch (not fullscreen).
    os.environ["SDL_VIDEO_CENTERED"] = "1"
    pygame.init()
    pygame.display.set_caption("Pygame Tiled Map Demo")
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), flags=0)
    clock = pygame.time.Clock()

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
    direction = "down"
    frame_idx = 0
    anim_timer = 0.0

    x = tiled_map.pixel_width * 0.5
    y = tiled_map.pixel_height * 0.5

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        view_width, view_height = screen.get_size()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        keys = pygame.key.get_pressed()
        dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (
            keys[pygame.K_a] or keys[pygame.K_LEFT]
        )
        dy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (
            keys[pygame.K_w] or keys[pygame.K_UP]
        )

        moving = dx != 0 or dy != 0
        if moving:
            vec = pygame.Vector2(dx, dy)
            vec = vec.normalize() * MOVE_SPEED * dt
            x += vec.x
            y += vec.y

            if abs(dy) > abs(dx):
                direction = "down" if dy > 0 else "up"
            else:
                direction = "right" if dx > 0 else "left"

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

        player_center_x = round((x - camera_x) * MAP_RENDER_SCALE + offset_x)
        player_center_y = round((y - camera_y) * MAP_RENDER_SCALE + offset_y)
        player_rect = current.get_rect(
            center=(player_center_x, player_center_y)
        )
        screen.blit(current, player_rect)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    print("[BOOT] main.py is running")
    try:
        main()
    except Exception:
        traceback.print_exc()
        input("Press Enter to exit...")
