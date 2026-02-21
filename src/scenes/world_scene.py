from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pygame

from src.constants import ENEMY_IMAGE_CANDIDATES, FONT_CANDIDATES
from src.scenes.battle_scene import BattleScene




def _load_ui_font(size: int) -> pygame.font.Font:
    for path in FONT_CANDIDATES:
        if path.exists():
            return pygame.font.Font(path.as_posix(), size)
    return pygame.font.Font(None, size)

def _load_monster_image() -> pygame.Surface:
    for path in ENEMY_IMAGE_CANDIDATES:
        if path.exists():
            image = pygame.image.load(path.as_posix()).convert_alpha()
            return image
    raise FileNotFoundError("Missing enemy image: 蛛蜘女孩.png/蜘蛛女孩.png")


def _load_teleports(map_file: Path) -> list[dict[str, Any]]:
    with map_file.open("r", encoding="utf-8") as f:
        content = json.load(f)

    teleports: list[dict[str, Any]] = []
    for layer in content.get("layers", []):
        if str(layer.get("type", "")).strip().lower() != "objectgroup":
            continue
        for obj in layer.get("objects", []):
            properties: dict[str, Any] = {}
            for prop in obj.get("properties", []):
                name = str(prop.get("name", "")).strip()
                if not name:
                    continue
                properties[name] = prop.get("value")

            obj_type = str(obj.get("type") or properties.get("type") or "").strip().lower()
            if obj_type != "teleport":
                continue

            target_map = str(properties.get("target_map") or "").strip()
            if not target_map:
                continue

            raw_x = float(obj.get("x", 0.0))
            raw_y = float(obj.get("y", 0.0))
            raw_w = float(obj.get("width", 0.0))
            raw_h = float(obj.get("height", 0.0))
            width = max(1, round(raw_w))
            height = max(1, round(raw_h))
            rect = pygame.Rect(round(raw_x), round(raw_y), width, height)

            teleports.append(
                {
                    "rect": rect,
                    "target_map": target_map,
                    "spawn_x": properties.get("spawn_x"),
                    "spawn_y": properties.get("spawn_y"),
                }
            )

    return teleports


def _resolve_target_map_file(current_map_file: Path, target_map: str, map_dir: Path | None) -> Path:
    raw = Path(target_map)
    candidates = [
        (current_map_file.parent / raw).resolve(),
        (current_map_file.parent / raw.name).resolve(),
    ]
    if map_dir is not None:
        candidates.extend(
            [
                (map_dir / raw).resolve(),
                (map_dir / raw.name).resolve(),
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate

    if map_dir is not None:
        by_name = next(map_dir.rglob(raw.name), None)
        if by_name is not None:
            return by_name

    raise FileNotFoundError(f"Cannot resolve target map '{target_map}' from '{current_map_file}'")


def _pick_spawn_position(
    tiled_map: Any,
    teleport: dict[str, Any],
    collision_half_w: int,
    collision_half_h: int,
    collision_foot_offset: int,
    core: dict[str, Any],
) -> tuple[float, float]:
    raw_x = teleport.get("spawn_x")
    raw_y = teleport.get("spawn_y")
    try:
        if raw_x is not None and raw_y is not None:
            spawn_x = float(raw_x)
            spawn_y = float(raw_y) - collision_foot_offset
            if tiled_map.can_move_to(
                spawn_x,
                spawn_y + collision_foot_offset,
                collision_half_w,
                collision_half_h,
            ):
                return spawn_x, spawn_y
    except (TypeError, ValueError):
        pass

    return core["find_spawn_position_top"](
        tiled_map,
        collision_half_w,
        collision_half_h,
        collision_foot_offset,
    )


def _show_battle_result_prompt(screen: pygame.Surface, clock: pygame.time.Clock, title: str) -> str:
    title_font = _load_ui_font(92)
    hint_font = _load_ui_font(38)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                return "continue"

        w, h = screen.get_size()
        screen.fill((0, 0, 0))

        title_shadow = title_font.render(title, True, (16, 16, 16))
        title_label = title_font.render(title, True, (238, 238, 238))
        title_rect = title_label.get_rect(center=(w // 2, h // 2 - 36))
        screen.blit(title_shadow, title_rect.move(3, 3))
        screen.blit(title_label, title_rect)

        hint = hint_font.render("按回车继续", True, (190, 190, 190))
        hint_rect = hint.get_rect(center=(w // 2, h // 2 + 64))
        screen.blit(hint, hint_rect)

        pygame.display.flip()
        clock.tick(60)


def _draw_keycap(surface: pygame.Surface, rect: pygame.Rect, label: str, font: pygame.font.Font) -> None:
    pygame.draw.rect(surface, (26, 30, 40), rect, border_radius=8)
    pygame.draw.rect(surface, (188, 196, 214), rect, width=2, border_radius=8)
    text = font.render(label, True, (236, 240, 248))
    surface.blit(text, text.get_rect(center=rect.center))


def _show_world_tutorial_prompt(screen: pygame.Surface, clock: pygame.time.Clock) -> str:
    title_font = _load_ui_font(64)
    body_font = _load_ui_font(34)
    key_font = _load_ui_font(28)
    hint_font = _load_ui_font(28)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                return "continue"

        w, h = screen.get_size()
        screen.fill((0, 0, 0))

        panel = pygame.Rect(0, 0, min(1120, max(760, w - 120)), min(620, max(460, h - 120)))
        panel.center = (w // 2, h // 2)
        overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
        overlay.fill((8, 12, 18, 228))
        screen.blit(overlay, panel)
        pygame.draw.rect(screen, (188, 196, 214), panel, width=2, border_radius=16)

        title = title_font.render("基础操作教学", True, (240, 236, 214))
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 70)))

        arrow_box = pygame.Rect(panel.left + 60, panel.top + 140, panel.width // 2 - 90, panel.height - 220)
        pygame.draw.rect(screen, (16, 20, 28), arrow_box, border_radius=14)
        pygame.draw.rect(screen, (122, 134, 154), arrow_box, width=2, border_radius=14)

        key_w = 86
        key_h = 56
        key_gap = 14
        center_x = arrow_box.centerx
        center_y = arrow_box.centery + 24
        up = pygame.Rect(0, 0, key_w, key_h)
        left = pygame.Rect(0, 0, key_w, key_h)
        down = pygame.Rect(0, 0, key_w, key_h)
        right = pygame.Rect(0, 0, key_w, key_h)
        up.center = (center_x, center_y - key_h - key_gap)
        left.center = (center_x - key_w - key_gap, center_y)
        down.center = (center_x, center_y)
        right.center = (center_x + key_w + key_gap, center_y)
        _draw_keycap(screen, up, "W / ↑", key_font)
        _draw_keycap(screen, left, "A / ←", key_font)
        _draw_keycap(screen, down, "S / ↓", key_font)
        _draw_keycap(screen, right, "D / →", key_font)

        move_text = body_font.render("行走移动", True, (226, 232, 244))
        screen.blit(move_text, move_text.get_rect(center=(arrow_box.centerx, arrow_box.top + 42)))

        right_box = pygame.Rect(panel.centerx + 16, panel.top + 140, panel.width // 2 - 76, panel.height - 220)
        pygame.draw.rect(screen, (16, 20, 28), right_box, border_radius=14)
        pygame.draw.rect(screen, (122, 134, 154), right_box, width=2, border_radius=14)

        esc_key = pygame.Rect(right_box.left + 48, right_box.top + 72, 120, 58)
        _draw_keycap(screen, esc_key, "ESC", key_font)
        esc_text = body_font.render("打开功能菜单", True, (226, 232, 244))
        screen.blit(esc_text, esc_text.get_rect(midleft=(esc_key.right + 22, esc_key.centery)))

        tip_text = body_font.render("建议先熟悉移动，再探索地图", True, (214, 222, 236))
        screen.blit(tip_text, tip_text.get_rect(midleft=(right_box.left + 48, right_box.top + 188)))

        hint = hint_font.render("按任意键或点击鼠标继续", True, (198, 206, 220))
        screen.blit(hint, hint.get_rect(center=(panel.centerx, panel.bottom - 36)))

        pygame.display.flip()
        clock.tick(60)


def _draw_dialogue_overlay(
    surface: pygame.Surface,
    title: str,
    text: str,
    show_hint: bool = True,
    position: str = "top",
    speaker_x: float | None = None,
) -> None:
    view_w, view_h = surface.get_size()
    title_font = _load_ui_font(24)
    body_font = _load_ui_font(34)
    hint_font = _load_ui_font(18)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        lines = [text.strip() or "..."]
    lines = lines[:3]

    title_surface = title_font.render(title, True, (222, 214, 192)) if title.strip() else None
    line_surfaces = [body_font.render(line, True, (244, 244, 244)) for line in lines]
    line_shadows = [body_font.render(line, True, (14, 14, 14)) for line in lines]
    hint_surface = hint_font.render("按任意键继续", True, (198, 198, 198)) if show_hint else None

    content_w = 0
    if title_surface is not None:
        content_w = max(content_w, title_surface.get_width())
    if line_surfaces:
        content_w = max(content_w, max(s.get_width() for s in line_surfaces))
    if hint_surface is not None:
        content_w = max(content_w, hint_surface.get_width())

    pad_x = 18
    panel_w = content_w + pad_x * 2
    panel_w = max(380, min(panel_w, view_w - 120))

    top_pad = 14
    gap_after_title = 8 if title_surface is not None else 0
    line_h = body_font.get_height()
    text_h = len(line_surfaces) * line_h + max(0, len(line_surfaces) - 1) * 8
    hint_h = hint_surface.get_height() + 8 if hint_surface is not None else 0
    panel_h = top_pad + (title_surface.get_height() if title_surface is not None else 0) + gap_after_title + text_h + hint_h + 14

    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.centerx = view_w // 2
    if position == "bottom":
        panel.bottom = view_h - 26
    else:
        panel.top = 40

    overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
    overlay.fill((8, 8, 10, 186))
    surface.blit(overlay, panel.topleft)
    pygame.draw.rect(surface, (206, 206, 206), panel, width=2, border_radius=10)

    if speaker_x is not None:
        tip_x = max(panel.left + 28, min(panel.right - 28, round(speaker_x)))
        tail_half_w = 14
        tail_h = 12
        if position == "bottom":
            tail_points = [
                (tip_x - tail_half_w, panel.top + 1),
                (tip_x + tail_half_w, panel.top + 1),
                (tip_x, panel.top - tail_h),
            ]
        else:
            tail_points = [
                (tip_x - tail_half_w, panel.bottom - 1),
                (tip_x + tail_half_w, panel.bottom - 1),
                (tip_x, panel.bottom + tail_h),
            ]
        pygame.draw.polygon(surface, (8, 8, 10), tail_points)
        pygame.draw.polygon(surface, (206, 206, 206), tail_points, width=2)

    cursor_y = panel.top + top_pad
    text_x = panel.left + pad_x
    if title_surface is not None:
        surface.blit(title_surface, (text_x, cursor_y))
        cursor_y += title_surface.get_height() + gap_after_title

    for idx, label in enumerate(line_surfaces):
        pos = (text_x, cursor_y)
        shadow = line_shadows[idx]
        surface.blit(shadow, (pos[0] + 1, pos[1] + 1))
        surface.blit(label, pos)
        cursor_y += line_h + 8

    if hint_surface is not None:
        hint_rect = hint_surface.get_rect(bottomright=(panel.right - pad_x, panel.bottom - 10))
        surface.blit(hint_surface, hint_rect)


def _find_object_anchor(map_file: Path) -> tuple[float, float] | None:
    try:
        with map_file.open("r", encoding="utf-8") as f:
            content = json.load(f)
    except Exception:
        return None

    for layer in content.get("layers", []):
        if str(layer.get("type", "")).strip().lower() != "objectgroup":
            continue
        for obj in layer.get("objects", []):
            gid_raw = int(obj.get("gid", 0))
            if gid_raw == 0:
                continue
            x = float(obj.get("x", 0.0))
            y = float(obj.get("y", 0.0))
            width = float(obj.get("width", 0.0))
            return x + max(0.0, width) * 0.5, y
    return None


def _load_dialogue_rows(csv_path: Path, player_name: str) -> list[dict[str, Any]]:
    if not csv_path.exists():
        return []

    for encoding in ("utf-8-sig", "utf-8", "gbk", "cp936"):
        try:
            rows: list[dict[str, Any]] = []
            with csv_path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                for raw in reader:
                    text = str(raw.get("text", "")).strip()
                    if not text:
                        continue

                    speaker_key = str(raw.get("speaker", "")).strip().lower()
                    if speaker_key in {"", "player", "玩家"}:
                        speaker = player_name
                        speaker_target = "player"
                    else:
                        speaker = str(raw.get("speaker", "")).strip()
                        speaker_target = "npc"

                    raw_position = str(raw.get("position", "")).strip().lower()
                    if raw_position in {"bottom", "down", "下"}:
                        position = "bottom"
                    elif raw_position in {"top", "up", "上"}:
                        position = "top"
                    else:
                        position = "bottom" if speaker_target == "player" else "top"

                    raw_target = str(raw.get("speaker_target", "")).strip().lower()
                    if raw_target in {"player", "玩家"}:
                        speaker_target = "player"
                    elif raw_target in {"npc", "enemy", "对方"}:
                        speaker_target = "npc"

                    raw_auto_walk = str(raw.get("auto_walk_after", "")).strip().lower()
                    auto_walk_after = raw_auto_walk in {"1", "true", "yes", "y", "是"}
                    voice_file = str(raw.get("voice_file", "")).strip()

                    rows.append(
                        {
                            "speaker": speaker,
                            "text": text,
                            "position": position,
                            "speaker_target": speaker_target,
                            "auto_walk_after": auto_walk_after,
                            "voice_file": voice_file,
                        }
                    )
            return rows
        except UnicodeDecodeError:
            continue
        except Exception:
            return []
    return []


def run_world_scene(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    display_settings: Any,
    player_name: str,
    core: dict[str, Any],
    callbacks: dict[str, Any],
) -> tuple[str, pygame.Surface, Any]:
    monster_image: pygame.Surface | None = None
    map_dir = core.get("MAP_DIR")
    try:
        current_map_file = core["find_first_map_file"]()
        tiled_map = core["TiledMap"](current_map_file)
        teleports = _load_teleports(current_map_file)
        run_sheet = core["load_image"](core["PLAYER_RUN_PATH"])
        stand_sheet = core["load_image"](core["PLAYER_STAND_PATH"])
        try:
            monster_image = _load_monster_image()
        except Exception:
            monster_image = None
    except Exception as exc:
        print(exc)
        print("Check map/assets paths")
        return "quit", screen, display_settings

    if _show_world_tutorial_prompt(screen, clock) == "quit":
        return "quit", screen, display_settings
    assets_dir = map_dir.parent if map_dir is not None else current_map_file.parent.parent
    sound_dir = assets_dir / "sound"

    run_anim = core["build_animation"](run_sheet, core["PLAYER_RUN_ATLAS_PATH"])
    run_anim = core["scale_animation"](run_anim, core["PLAYER_SCALE"])
    run_anim = core["apply_player_tone"](run_anim, core["PLAYER_BRIGHTNESS"])
    stand_anim = core["build_animation"](stand_sheet, core["PLAYER_STAND_ATLAS_PATH"])
    stand_anim = core["scale_animation"](stand_anim, core["PLAYER_SCALE"])
    stand_anim = core["apply_player_tone"](stand_anim, core["PLAYER_BRIGHTNESS"])

    active_anim = stand_anim
    active_anim_name = "stand"
    coord_font = _load_ui_font(core["TILE_COORD_FONT_SIZE"])
    ui_font = _load_ui_font(36)
    direction = "down"
    frame_idx = 0
    anim_timer = 0.0

    collision_half_w = max(6, round(run_anim["down"][0].get_width() * core["PLAYER_COLLIDER_WIDTH_RATIO"]))
    collision_half_h = max(6, round(run_anim["down"][0].get_height() * core["PLAYER_COLLIDER_HEIGHT_RATIO"]))
    collision_foot_offset = round(run_anim["down"][0].get_height() * core["PLAYER_COLLIDER_FOOT_OFFSET_RATIO"])
    shadow_w = max(18, round(run_anim["down"][0].get_width() * 0.46))
    shadow_h = max(10, round(run_anim["down"][0].get_height() * 0.2))
    player_shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
    pygame.draw.ellipse(player_shadow, (0, 0, 0, 90), player_shadow.get_rect())

    spawn_coord_x = 29
    spawn_coord_y = 38
    grid_step = core["GRID_MOVE_STEP_PIXELS"]
    x = (spawn_coord_x - 0.5) * grid_step
    y = (spawn_coord_y - 0.5) * grid_step - collision_foot_offset
    x = round(x / grid_step) * grid_step
    y = round(y / grid_step) * grid_step

    player_hp = 20
    player_max_hp = 20
    teleport_cooldown = 0.0

    monster_world_x = tiled_map.pixel_width * 0.54
    monster_world_y = tiled_map.pixel_height * 0.32
    monster_alive = False

    cutscene_played_on_second_map = False
    cutscene_state = ""
    cutscene_target = pygame.Vector2(
        monster_world_x,
        monster_world_y + max(108.0, run_anim["down"][0].get_height() * 0.95),
    )
    cutscene_npc_world_x = monster_world_x
    cutscene_walk_timeout = 4.2
    dialogue_rows: list[dict[str, Any]] = []
    dialogue_index = 0
    dialogue_typewriter_state = ""
    dialogue_shown_chars = 0.0
    dialogue_char_speed = 22.0
    dialogue_voice_cache: dict[str, pygame.mixer.Sound] = {}
    dialogue_voice_key_played = ""
    dialogue_voice_channel: pygame.mixer.Channel | None = None
    trigger_battle_after_cutscene = False

    while True:
        dt = clock.tick(core["FPS"]) / 1000.0
        if teleport_cooldown > 0.0:
            teleport_cooldown = max(0.0, teleport_cooldown - dt)
        view_width, view_height = screen.get_size()
        open_pause_menu = False
        trigger_battle = False

        world_view_w = view_width / core["MAP_RENDER_SCALE"]
        world_view_h = view_height / core["MAP_RENDER_SCALE"]
        camera_x = max(0, min(max(0, tiled_map.pixel_width - world_view_w), x - world_view_w / 2))
        camera_y = max(0, min(max(0, tiled_map.pixel_height - world_view_h), y - world_view_h / 2))
        offset_x, offset_y = core["get_map_offset"](
            tiled_map.pixel_width,
            tiled_map.pixel_height,
            view_width,
            view_height,
            core["MAP_RENDER_SCALE"],
        )

        in_second_map = current_map_file.name.lower() == "map2.json"

        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                return "quit", screen, display_settings
            if (
                cutscene_state == ""
                and event.type == pygame.KEYDOWN
                and event.key == pygame.K_ESCAPE
            ):
                open_pause_menu = True

        if open_pause_menu:
            action, screen, display_settings = callbacks["run_pause_menu"](screen, clock, display_settings)
            if action == "quit":
                return "quit", screen, display_settings
            if action == "main_menu":
                return "main_menu", screen, display_settings
            continue

        if cutscene_state == "" and monster_alive and monster_image is not None:
            # Enter battle by proximity/collision instead of mouse click.
            trigger_radius = max(monster_image.get_width(), monster_image.get_height()) * 0.42
            trigger_battle = pygame.Vector2(x, y).distance_to((monster_world_x, monster_world_y)) <= trigger_radius
        if cutscene_state == "" and monster_alive and trigger_battle_after_cutscene:
            trigger_battle = True
            trigger_battle_after_cutscene = False

        if cutscene_state == "" and trigger_battle and monster_alive:
            battle = BattleScene(screen, clock, player_hp, player_max_hp, player_name)
            result = battle.run()
            if result.get("quit"):
                return "quit", screen, display_settings

            player_hp = int(result.get("player_hp", player_hp))
            outcome = str(result.get("outcome") or "")

            if outcome in {"victory", "spared"}:
                if _show_battle_result_prompt(screen, clock, "战斗胜利") == "quit":
                    return "quit", screen, display_settings
                monster_alive = False
            elif outcome == "defeat" or player_hp <= 0:
                if _show_battle_result_prompt(screen, clock, "大侠请重新来过") == "quit":
                    return "quit", screen, display_settings
                return "main_menu", screen, display_settings

            continue


        moving = False
        move_dx = 0.0
        move_dy = 0.0
        dialogue_title = ""
        dialogue_text = ""
        show_dialogue_hint = False
        dialogue_position = "top"
        dialogue_text_to_draw = ""
        dialogue_fully_revealed = False
        dialogue_speaker_x: float | None = None

        if cutscene_state == "line_wait":
            if dialogue_index < 0 or dialogue_index >= len(dialogue_rows):
                cutscene_state = ""
            else:
                line = dialogue_rows[dialogue_index]
                dialogue_title = str(line["speaker"])
                dialogue_text = str(line["text"])
                dialogue_position = str(line["position"])
                if str(line["speaker_target"]) == "player":
                    dialogue_speaker_x = round((x - camera_x) * core["MAP_RENDER_SCALE"] + offset_x)
                else:
                    dialogue_speaker_x = round((cutscene_npc_world_x - camera_x) * core["MAP_RENDER_SCALE"] + offset_x)
                typewriter_key = f"{cutscene_state}:{dialogue_index}"
                if dialogue_typewriter_state != typewriter_key:
                    dialogue_typewriter_state = typewriter_key
                    dialogue_shown_chars = 0.0
                if dialogue_voice_key_played != typewriter_key:
                    dialogue_voice_key_played = typewriter_key
                    voice_file = str(line.get("voice_file") or "").strip()
                    if voice_file:
                        try:
                            sound = dialogue_voice_cache.get(voice_file)
                            if sound is None:
                                sound = pygame.mixer.Sound((sound_dir / voice_file).as_posix())
                                dialogue_voice_cache[voice_file] = sound
                            if dialogue_voice_channel is not None and dialogue_voice_channel.get_busy():
                                dialogue_voice_channel.stop()
                            dialogue_voice_channel = sound.play()
                        except Exception:
                            pass
                dialogue_shown_chars = min(float(len(dialogue_text)), dialogue_shown_chars + dialogue_char_speed * dt)
                dialogue_text_to_draw = dialogue_text[: int(dialogue_shown_chars)]
                dialogue_fully_revealed = int(dialogue_shown_chars) >= len(dialogue_text)
                show_dialogue_hint = dialogue_fully_revealed
                for event in events:
                    if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                        if dialogue_fully_revealed:
                            if bool(line.get("auto_walk_after", False)):
                                cutscene_state = "auto_walk"
                            else:
                                dialogue_index += 1
                                if dialogue_index >= len(dialogue_rows):
                                    cutscene_state = ""
                                    if in_second_map:
                                        monster_alive = True
                                        trigger_battle_after_cutscene = True
                        else:
                            dialogue_shown_chars = float(len(dialogue_text))
                        break
        elif cutscene_state == "auto_walk":
            dialogue_typewriter_state = ""
            dialogue_voice_key_played = ""
            to_target = pygame.Vector2(cutscene_target.x - x, cutscene_target.y - y)
            distance = to_target.length()
            cutscene_walk_timeout = max(0.0, cutscene_walk_timeout - dt)
            if distance <= 2.0 or cutscene_walk_timeout <= 0.0:
                if tiled_map.can_move_to(
                    cutscene_target.x,
                    cutscene_target.y + collision_foot_offset,
                    collision_half_w,
                    collision_half_h,
                ):
                    x = cutscene_target.x
                    y = cutscene_target.y
                direction = "up"
                dialogue_index += 1
                if dialogue_index >= len(dialogue_rows):
                    cutscene_state = ""
                    if in_second_map:
                        monster_alive = True
                        trigger_battle_after_cutscene = True
                else:
                    cutscene_state = "line_wait"
            else:
                moving = True
                speed = core["MOVE_SPEED"] * 0.92
                vec = to_target.normalize() * speed * dt
                move_dx = vec.x
                move_dy = vec.y
        else:
            dialogue_typewriter_state = ""
            dialogue_voice_key_played = ""
            keys = pygame.key.get_pressed()
            move_dx = float((keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT]))
            move_dy = float((keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP]))
            moving = move_dx != 0.0 or move_dy != 0.0

        next_anim = run_anim if moving else stand_anim
        next_anim_name = "run" if moving else "stand"
        if next_anim_name != active_anim_name:
            active_anim = next_anim
            active_anim_name = next_anim_name
            frame_idx = 0
            anim_timer = 0.0

        if moving:
            vec = pygame.Vector2(move_dx, move_dy)
            vec = vec.normalize() * core["MOVE_SPEED"] * dt
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

        anim_fps = core["ANIM_FPS"] if moving else core["STAND_ANIM_FPS"]
        anim_timer += dt
        if anim_timer >= 1.0 / anim_fps:
            anim_timer = 0.0
            frame_idx = (frame_idx + 1) % len(active_anim[direction])

        frame_idx %= len(active_anim[direction])
        current = active_anim[direction][frame_idx]
        half_w = current.get_width() // 2
        half_h = current.get_height() // 2

        x = max(half_w, min(tiled_map.pixel_width - half_w, x))
        y = max(half_h, min(tiled_map.pixel_height - half_h, y))

        map_switched = False
        if cutscene_state == "" and teleport_cooldown <= 0.0 and teleports:
            foot_point = (round(x), round(y + collision_foot_offset))
            for teleport in teleports:
                if not teleport["rect"].collidepoint(foot_point):
                    continue
                try:
                    target_map_file = _resolve_target_map_file(
                        current_map_file,
                        str(teleport["target_map"]),
                        map_dir,
                    )
                    tiled_map = core["TiledMap"](target_map_file)
                    current_map_file = target_map_file
                    teleports = _load_teleports(current_map_file)
                    x, y = _pick_spawn_position(
                        tiled_map,
                        teleport,
                        collision_half_w,
                        collision_half_h,
                        collision_foot_offset,
                        core,
                    )
                    teleport_cooldown = 0.35
                    if in_second_map:
                        cutscene_state = ""
                    if current_map_file.name.lower() == "map2.json" and not cutscene_played_on_second_map:
                        dialogue_csv = assets_dir / "dialogue" / "map2_intro.csv"
                        dialogue_rows = _load_dialogue_rows(dialogue_csv, player_name)
                        if not dialogue_rows:
                            dialogue_rows = [
                                {
                                    "speaker": "蜘蛛女孩",
                                    "text": "你来啦",
                                    "position": "top",
                                    "speaker_target": "npc",
                                    "auto_walk_after": True,
                                    "voice_file": "girl1.wav",
                                },
                                {
                                    "speaker": player_name,
                                    "text": "你认识我？",
                                    "position": "bottom",
                                    "speaker_target": "player",
                                    "auto_walk_after": False,
                                    "voice_file": "man1.wav",
                                },
                            ]
                        anchor = _find_object_anchor(current_map_file)
                        if anchor is not None:
                            cutscene_npc_world_x = anchor[0]
                            monster_world_x = anchor[0]
                            monster_world_y = anchor[1]
                            cutscene_target = pygame.Vector2(
                                anchor[0],
                                anchor[1] + max(106.0, run_anim["down"][0].get_height() * 0.9),
                            )
                        else:
                            monster_world_x = tiled_map.pixel_width * 0.54
                            monster_world_y = tiled_map.pixel_height * 0.45
                            cutscene_target = pygame.Vector2(
                                monster_world_x,
                                monster_world_y + max(106.0, run_anim["down"][0].get_height() * 0.9),
                            )
                        cutscene_walk_timeout = 5.0
                        dialogue_index = 0
                        dialogue_voice_key_played = ""
                        cutscene_state = "line_wait"
                        cutscene_played_on_second_map = True
                    else:
                        cutscene_state = ""
                    map_switched = True
                except Exception as exc:
                    print(exc)
                break
        if map_switched:
            continue

        screen.fill((0, 0, 0))
        tiled_map.draw(screen, camera_x, camera_y, core["MAP_RENDER_SCALE"], offset_x, offset_y)
        if core["SHOW_TILE_COORDS"]:
            tiled_map.draw_tile_coordinates(screen, camera_x, camera_y, coord_font, core["MAP_RENDER_SCALE"], offset_x, offset_y)

        if core["SHOW_PLAYER_STEP_COORD"]:
            core["draw_player_step_coordinate"](screen, coord_font, x, y + collision_foot_offset)

        player_center_x = round((x - camera_x) * core["MAP_RENDER_SCALE"] + offset_x)
        player_center_y = round((y - camera_y) * core["MAP_RENDER_SCALE"] + offset_y)
        shadow_rect = player_shadow.get_rect(center=(player_center_x, player_center_y + max(8, current.get_height() // 3)))
        screen.blit(player_shadow, shadow_rect)
        player_rect = current.get_rect(center=(player_center_x, player_center_y))
        screen.blit(current, player_rect)

        core["draw_weather_effects"](screen, pygame.time.get_ticks() / 1000.0)
        hp_label = ui_font.render(f"{player_name} HP {player_hp}/{player_max_hp}", True, (232, 240, 250))
        screen.blit(hp_label, (18, 54))
        if cutscene_state != "" and dialogue_text:
            _draw_dialogue_overlay(
                screen,
                dialogue_title,
                dialogue_text_to_draw or dialogue_text,
                show_hint=show_dialogue_hint,
                position=dialogue_position,
                speaker_x=dialogue_speaker_x,
            )
        pygame.display.flip()
