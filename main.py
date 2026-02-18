import sys
from pathlib import Path

import pygame


SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FPS = 60
MOVE_SPEED = 220  # pixels per second
ANIM_FPS = 10

# Big world size (in pixels)
WORLD_WIDTH = 4096
WORLD_HEIGHT = 4096

ASSET_DIR = Path(__file__).parent / "assets"
GROUND_PATH = ASSET_DIR / "bg" / "ground1.png"
PLAYER_PATH = ASSET_DIR / "player" / "player.png"


def load_image(path: Path) -> pygame.Surface:
    if not path.exists():
        raise FileNotFoundError(f"Missing asset: {path}")
    return pygame.image.load(path.as_posix()).convert_alpha()


def draw_tiled_world(
    screen: pygame.Surface, tile: pygame.Surface, camera_x: float, camera_y: float
) -> None:
    tw, th = tile.get_size()

    start_col = int(camera_x // tw)
    end_col = int((camera_x + SCREEN_WIDTH) // tw) + 1
    start_row = int(camera_y // th)
    end_row = int((camera_y + SCREEN_HEIGHT) // th) + 1

    for row in range(start_row, end_row + 1):
        for col in range(start_col, end_col + 1):
            world_x = col * tw
            world_y = row * th
            if world_x >= WORLD_WIDTH or world_y >= WORLD_HEIGHT:
                continue
            if world_x + tw <= 0 or world_y + th <= 0:
                continue
            screen_x = int(world_x - camera_x)
            screen_y = int(world_y - camera_y)
            screen.blit(tile, (screen_x, screen_y))


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
    pygame.init()
    pygame.display.set_caption("Pygame Minimal Demo")
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    try:
        ground = load_image(GROUND_PATH)
        player_sheet = load_image(PLAYER_PATH)
    except FileNotFoundError as e:
        print(e)
        print("Put assets at: assets/bg/ground1.png and assets/player/player.png")
        pygame.quit()
        sys.exit(1)

    anim = build_animation(player_sheet)
    direction = "down"
    frame_idx = 0
    anim_timer = 0.0

    x = WORLD_WIDTH * 0.5
    y = WORLD_HEIGHT * 0.5

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

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

        # Keep player inside world bounds.
        x = max(half_w, min(WORLD_WIDTH - half_w, x))
        y = max(half_h, min(WORLD_HEIGHT - half_h, y))

        camera_x = max(0, min(WORLD_WIDTH - SCREEN_WIDTH, x - SCREEN_WIDTH / 2))
        camera_y = max(0, min(WORLD_HEIGHT - SCREEN_HEIGHT, y - SCREEN_HEIGHT / 2))

        screen.fill((0, 0, 0))
        draw_tiled_world(screen, ground, camera_x, camera_y)

        player_rect = current.get_rect(
            center=(int(x - camera_x), int(y - camera_y))
        )
        screen.blit(current, player_rect)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
