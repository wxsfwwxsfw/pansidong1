from __future__ import annotations

import json
import random
from enum import Enum, auto
from pathlib import Path

import pygame

from src.battle.data import BattleRuntime, clamp_enemy_stats, get_enemy_pressure_profile, get_item, refresh_spare_progress
from src.battle.patterns import Bullet, draw_bullets, spawn_corner_drops, spawn_top_threads, update_bullets
from src.constants import (
    AVATAR_FRAME,
    AVATAR_IMAGE,
    BATTLE_BG,
    BLUE_BLOCK,
    ENEMY_IMAGE_CANDIDATES,
    FONT_CANDIDATES,
    HP_BAR_BG,
    RED_BLOCK,
    SOUL_IMAGE,
)
from src.ui.battle_ui import BattleUI

HIT_SOUND_CANDIDATES = (
    Path(__file__).resolve().parent.parent.parent / "assets" / "sonund2.wav",
    Path(__file__).resolve().parent.parent.parent / "assets" / "sound2" / "shang.WAV",
)
HIT_EFFECT_JSON_CANDIDATES = (
    Path(__file__).resolve().parent.parent.parent / "assets" / "attack" / "shousheng.json",
    Path(__file__).resolve().parent.parent.parent / "assets" / "attack" / "shoushang.json",
)


class BattleState(Enum):
    OBSERVE = auto()
    PLAYER_MENU = auto()
    PLAYER_ACTION = auto()
    ENEMY_BULLETS = auto()
    FEEDBACK = auto()


class BattleScene:
    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock, player_hp: int, player_max_hp: int, player_name: str = "莲心") -> None:
        self.screen = screen
        self.clock = clock
        self.runtime = BattleRuntime()
        self.runtime.player.name = player_name.strip() or "莲心"
        self.runtime.player.hp = max(1, min(player_max_hp, player_hp))
        self.runtime.player.max_hp = player_max_hp

        self.font_large = self._load_font(44)
        self.font_mid = self._load_font(34)
        self.font_small = self._load_font(28)

        self.background = self._load_image(BATTLE_BG, alpha=False)
        self.enemy_image = self._load_enemy_image()
        self.avatar_frame = self._load_image(AVATAR_FRAME)
        self.avatar_image = self._load_image(AVATAR_IMAGE, required=True)
        self.bar_bg = self._load_image(HP_BAR_BG)
        self.red_block = self._load_image(RED_BLOCK)
        self.blue_block = self._load_image(BLUE_BLOCK)
        self.soul = self._load_image(SOUL_IMAGE)
        self.soul = pygame.transform.smoothscale(
            self.soul,
            (max(1, self.soul.get_width() // 2), max(1, self.soul.get_height() // 2)),
        )

        self.ui = BattleUI(
            self.background,
            self.avatar_frame,
            self.avatar_image,
            self.bar_bg,
            self.red_block,
            self.blue_block,
            self.runtime.enemy.name,
            self.font_large,
            self.font_mid,
            self.font_small,
        )

        w, h = screen.get_size()
        sx = w / 1536.0
        sy = h / 1024.0

        # Match positions authored in assets/attack/attack_UI.json (base: 1536x1024).
        self.battle_box = pygame.Rect(
            int(round(252 * sx)),
            int(round(322 * sy)),
            int(round(1032 * sx)),
            int(round(408 * sy)),
        )
        self.enemy_draw_center = (int(round(1030 * sx)), int(round(261 * sy)))
        self.soul_pos = pygame.Vector2(int(round(757 * sx)), int(round(669 * sy)))

        self.state = BattleState.OBSERVE
        self.state_timer = 0.9
        self.info_lines = ["敌意在蛛丝间回响……", "按 Enter 可跳过"]
        self.main_selected = 0
        self.list_selected = 0
        self.list_mode: str | None = None
        self.action_buttons: list[pygame.Rect] = []
        self.feedback_delay = 1.2

        self.attack_pointer = 0.0
        self.attack_dir = 1.0
        self.attack_elapsed = 0.0
        self.attack_duration = 1.55
        self.attack_locked = False

        self.bullets: list[Bullet] = []
        self.bullet_timer = 0.0
        self.hit_cooldown = 0.0
        self.hit_sound = self._load_hit_sound()
        self.enemy_turn_count = 0
        self.pressure_profile = get_enemy_pressure_profile(self.runtime.enemy.name)
        self.enemy_hit_effect_frames = self._load_hit_effect_frames()
        self.enemy_hit_effect_active = False
        self.enemy_hit_effect_timer = 0.0
        self.enemy_hit_effect_index = 0
        self.enemy_hit_effect_frame_interval = 0.055
        self.enemy_hit_effect_anchor = pygame.Vector2(self.enemy_draw_center)
        self.enemy_hit_shake_timer = 0.0
        self.enemy_hit_shake_duration = 0.20
        self.enemy_hit_shake_amp = 15

        self.result: str | None = None

    def _load_font(self, size: int) -> pygame.font.Font:
        for path in FONT_CANDIDATES:
            if path.exists():
                return pygame.font.Font(path.as_posix(), size)
        return pygame.font.Font(None, size)

    def _load_image(self, path: Path, alpha: bool = True, required: bool = True) -> pygame.Surface | None:
        if not path.exists():
            if required:
                raise FileNotFoundError(f"Missing battle asset: {path}")
            return None
        surf = pygame.image.load(path.as_posix())
        return surf.convert_alpha() if alpha else surf.convert()

    def _load_enemy_image(self) -> pygame.Surface:
        for path in ENEMY_IMAGE_CANDIDATES:
            if path.exists():
                img = pygame.image.load(path.as_posix()).convert_alpha()
                return img
        raise FileNotFoundError("Missing enemy image: 蛛蜘女孩.png/蜘蛛女孩.png")

    def _load_hit_sound(self) -> pygame.mixer.Sound | None:
        for path in HIT_SOUND_CANDIDATES:
            if not path.exists():
                continue
            try:
                return pygame.mixer.Sound(path.as_posix())
            except Exception:
                continue
        return None

    def _load_hit_effect_frames(self) -> list[pygame.Surface]:
        for json_path in HIT_EFFECT_JSON_CANDIDATES:
            if not json_path.exists():
                continue
            try:
                with json_path.open("r", encoding="utf-8") as f:
                    content = json.load(f)
                frames = content.get("frames", {})
                meta = content.get("meta", {})
                png_name = meta.get("image") or f"{json_path.stem}.png"
                png_path = json_path.with_name(png_name)
                if not png_path.exists():
                    png_path = json_path.with_suffix(".png")
                if not png_path.exists():
                    continue
                sheet = pygame.image.load(png_path.as_posix()).convert_alpha()
                frame_names = sorted(
                    frames.keys(),
                    key=lambda name: int("".join(ch for ch in name if ch.isdigit()) or "0"),
                )
                sequence: list[pygame.Surface] = []
                for frame_name in frame_names:
                    frame_info = frames.get(frame_name, {})
                    rect_info = frame_info.get("frame", {})
                    x = int(rect_info.get("x", 0))
                    y = int(rect_info.get("y", 0))
                    w = int(rect_info.get("w", 0))
                    h = int(rect_info.get("h", 0))
                    if w <= 0 or h <= 0:
                        continue
                    sequence.append(sheet.subsurface(pygame.Rect(x, y, w, h)).copy())
                if sequence:
                    return sequence
            except Exception:
                continue
        return []

    def _play_hit_sound(self) -> None:
        if self.hit_sound is None:
            return
        try:
            self.hit_sound.play()
        except Exception:
            pass

    def _trigger_enemy_hit_feedback(self) -> None:
        self.enemy_hit_shake_timer = self.enemy_hit_shake_duration
        if not self.enemy_hit_effect_frames:
            self.enemy_hit_effect_active = False
            return
        self.enemy_hit_effect_active = True
        self.enemy_hit_effect_timer = 0.0
        self.enemy_hit_effect_index = 0
        self.enemy_hit_effect_anchor = pygame.Vector2(self.enemy_draw_center)

    def _enemy_hit_offset(self) -> tuple[int, int]:
        if self.enemy_hit_shake_timer <= 0:
            return (0, 0)
        ratio = self.enemy_hit_shake_timer / self.enemy_hit_shake_duration
        amp = max(0, int(self.enemy_hit_shake_amp * ratio))
        return (random.randint(-amp, amp), random.randint(-max(1, amp // 2), max(1, amp // 2)))

    def _soul_rect(self) -> pygame.Rect:
        return self.soul.get_rect(center=(int(self.soul_pos.x), int(self.soul_pos.y)))

    def run(self) -> dict[str, object]:
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return {"quit": True, "player_hp": self.runtime.player.hp, "monster_defeated": False, "outcome": None}
                self._handle_event(event)

            self._update(dt)
            self._draw()
            pygame.display.flip()

            if self.result is not None:
                return {
                    "quit": False,
                    "player_hp": self.runtime.player.hp,
                    "monster_defeated": self.result in {"victory", "spared"},
                    "outcome": self.result,
                }

        return {"quit": True, "player_hp": self.runtime.player.hp, "monster_defeated": False, "outcome": None}

    def _handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if self.state == BattleState.OBSERVE and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._enter_player_menu()
                return
            if self.state == BattleState.PLAYER_MENU:
                self._handle_player_menu_keys(event.key)
                return
            if self.state == BattleState.PLAYER_ACTION:
                self._handle_player_action_keys(event.key)
                return


    def _handle_player_menu_keys(self, key: int) -> None:
        if key in (pygame.K_LEFT, pygame.K_a):
            self.main_selected = (self.main_selected - 1) % 4
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self.main_selected = (self.main_selected + 1) % 4
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._start_selected_action()

    def _handle_player_action_keys(self, key: int) -> None:
        if self.list_mode == "attack":
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self.attack_locked = True
            return

        options = self._active_options()
        if key in (pygame.K_UP, pygame.K_w):
            self.list_selected = (self.list_selected - 1) % len(options)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.list_selected = (self.list_selected + 1) % len(options)
        elif key == pygame.K_ESCAPE:
            self._enter_player_menu()
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.list_mode == "talk":
                self._resolve_talk(options[self.list_selected])
            elif self.list_mode == "item":
                self._resolve_item(options[self.list_selected])

    def _start_selected_action(self) -> None:
        if self.main_selected == 0:
            self.state = BattleState.PLAYER_ACTION
            self.list_mode = "attack"
            self.attack_pointer = 0.0
            self.attack_dir = 1.0
            self.attack_elapsed = 0.0
            self.attack_locked = False
            self.info_lines = ["凝神一击", "在黄金区按下 Space"]
        elif self.main_selected == 1:
            self.state = BattleState.PLAYER_ACTION
            self.list_mode = "talk"
            self.list_selected = 0
            self.info_lines = ["选择叩心方式", "上下选择 Enter 确认"]
        elif self.main_selected == 2:
            self.state = BattleState.PLAYER_ACTION
            self.list_mode = "item"
            self.list_selected = 0
            self.info_lines = ["翻找物件", "上下选择 Enter 使用"]
        else:
            enemy = self.runtime.enemy
            if enemy.spare_progress >= 60 and enemy.key_act_done:
                self.info_lines = ["童蛛退回蛛网深处……", "你选择了释怀"]
                self.result = "spared"
            else:
                self._set_feedback(["情丝未解，无法释怀", "继续叩心吧"], go_enemy=False)

    def _active_options(self) -> list[str]:
        if self.list_mode == "talk":
            return ["哼唱", "轻问", "递布", "喝止"]
        if self.list_mode == "item":
            return [f"{item.name} x{item.count} - {item.desc}" for item in self.runtime.inventory]
        return []

    def _resolve_talk(self, option_line: str) -> None:
        name = option_line.split()[0]
        enemy = self.runtime.enemy
        if name == "哼唱":
            enemy.mind -= 10
            enemy.bond += 18
            enemy.key_act_done = True
            text = ["你轻声哼唱", "心绪下降，情丝微动"]
        elif name == "轻问":
            enemy.bond += 14
            text = ["你放低声音询问", "情丝上升"]
        elif name == "递布":
            cloth = get_item(self.runtime, "布条")
            if cloth and cloth.count > 0:
                cloth.count -= 1
                enemy.bond += 30
                enemy.mind -= 5
                enemy.key_act_done = True
                text = ["你递出布条", "她手中的丝线松动了"]
            else:
                text = ["你摸了摸腰间", "没有布条可递"]
        else:
            enemy.mind += 12
            enemy.bond -= 8
            text = ["你厉声喝止", "她的敌意更浓了"]

        refresh_spare_progress(enemy)
        clamp_enemy_stats(enemy)
        if enemy.spare_progress >= 60:
            text.append("情丝松动……可以释怀")
        self._set_feedback(text, go_enemy=True)

    def _resolve_item(self, option_line: str) -> None:
        name = option_line.split(" x", 1)[0]
        item = get_item(self.runtime, name)
        if item is None or item.count <= 0:
            self._set_feedback(["物件已耗尽", "换一个试试"], go_enemy=False)
            return

        if name == "甘露":
            item.count -= 1
            self.runtime.player.hp = min(self.runtime.player.max_hp, self.runtime.player.hp + 5)
            self._set_feedback(["饮下甘露", "HP +5"], go_enemy=True)
        elif name == "布条":
            self._set_feedback(["布条需要在叩心-递布使用", "本回合未消耗"], go_enemy=False)
        else:
            self._set_feedback(["暂时无法使用该物品"], go_enemy=False)

    def _set_feedback(self, lines: list[str], go_enemy: bool) -> None:
        self.state = BattleState.FEEDBACK
        self.list_mode = None
        self.state_timer = self.feedback_delay
        self.info_lines = lines
        self._feedback_to_enemy = go_enemy

    def _enter_player_menu(self) -> None:
        self.state = BattleState.PLAYER_MENU
        self.list_mode = None
        self.info_lines = ["选择你的行动", "←/→ 或点击按钮"]

    def _start_enemy_turn(self) -> None:
        self.state = BattleState.ENEMY_BULLETS
        self.bullet_timer = random.uniform(3.5, 4.8)
        self.bullets.clear()
        self.enemy_turn_count += 1
        pressure = max(0, self.enemy_turn_count - 1)
        profile = self.pressure_profile
        pattern = random.choice(("corner", "top"))
        if pattern == "corner":
            amount = min(
                profile.corner_cap,
                round(profile.corner_base_amount * (1.0 + pressure * profile.corner_growth)),
            )
            self.bullets.extend(spawn_corner_drops(self.battle_box, amount=amount))
            self.info_lines = [f"细丝点从四角落下（第{self.enemy_turn_count}回合）", "回合越久越危险"]
        else:
            amount = min(
                profile.top_cap,
                round(profile.top_base_amount * (1.0 + pressure * profile.top_growth)),
            )
            self.bullets.extend(spawn_top_threads(self.battle_box, amount=amount))
            self.info_lines = [f"洞顶落丝（第{self.enemy_turn_count}回合）", "回合越久越危险"]

        step_turns = max(1, profile.size_boost_step_turns)
        size_boost = min(profile.size_boost_cap, pressure // step_turns)
        speed_scale = 1.0 + min(profile.speed_growth_cap, pressure * profile.speed_growth)
        for bullet in self.bullets:
            bullet.radius = min(14, bullet.radius + size_boost)
            bullet.vel *= speed_scale

    def _update(self, dt: float) -> None:
        if self.enemy_hit_shake_timer > 0:
            self.enemy_hit_shake_timer = max(0.0, self.enemy_hit_shake_timer - dt)
        if self.enemy_hit_effect_active:
            self.enemy_hit_effect_timer += dt
            while self.enemy_hit_effect_timer >= self.enemy_hit_effect_frame_interval:
                self.enemy_hit_effect_timer -= self.enemy_hit_effect_frame_interval
                self.enemy_hit_effect_index += 1
                if self.enemy_hit_effect_index >= len(self.enemy_hit_effect_frames):
                    self.enemy_hit_effect_active = False
                    break

        if self.state == BattleState.OBSERVE:
            self.state_timer -= dt
            if self.state_timer <= 0:
                self._enter_player_menu()
            return

        if self.state == BattleState.PLAYER_ACTION and self.list_mode == "attack":
            self.attack_elapsed += dt
            self.attack_pointer += self.attack_dir * dt * 1.2
            if self.attack_pointer >= 1.0:
                self.attack_pointer = 1.0
                self.attack_dir = -1.0
            elif self.attack_pointer <= 0.0:
                self.attack_pointer = 0.0
                self.attack_dir = 1.0

            if self.attack_locked or self.attack_elapsed >= self.attack_duration:
                self._resolve_attack()
            return

        if self.state == BattleState.ENEMY_BULLETS:
            self.bullet_timer -= dt
            self.hit_cooldown = max(0.0, self.hit_cooldown - dt)
            self._update_soul_movement(dt)
            dmg, hit_count = update_bullets(self.bullets, dt, self.battle_box, self._soul_rect())
            if dmg > 0 and self.hit_cooldown <= 0.0:
                self.runtime.player.hp = max(0, self.runtime.player.hp - dmg)
                self.hit_cooldown = 0.22
                for _ in range(hit_count):
                    self._play_hit_sound()
                self.info_lines = [f"莲心受击 -{dmg}", "保持躲避"]
                if self.runtime.player.hp <= 0:
                    self.info_lines = ["莲心倒下了", "战斗失败"]
                    self.result = "defeat"
                    return

            if self.bullet_timer <= 0:
                self.bullets.clear()
                self._set_feedback(["敌方回合结束", "轮到你行动"], go_enemy=False)
            return

        if self.state == BattleState.FEEDBACK:
            self.state_timer -= dt
            if self.state_timer <= 0:
                if self.result is not None:
                    return
                if self.runtime.enemy.hp <= 0:
                    self.info_lines = ["蛛丝散尽", "你赢得了战斗"]
                    self.result = "victory"
                elif self._feedback_to_enemy:
                    self._start_enemy_turn()
                else:
                    self._enter_player_menu()

    def _resolve_attack(self) -> None:
        r = self.attack_pointer
        miss = r < 0.08 or r > 0.92
        perfect = 0.47 <= r <= 0.53
        good = 0.39 <= r <= 0.61
        enemy = self.runtime.enemy

        if miss:
            dmg = 0
            tier = "MISS"
        elif perfect:
            dmg = 7
            tier = "PERFECT"
        elif good:
            dmg = 5
            tier = "GOOD"
        else:
            dmg = 3
            tier = "NORMAL"

        enemy.hp -= dmg
        clamp_enemy_stats(enemy)
        if dmg > 0:
            self._trigger_enemy_hit_feedback()
            self._set_feedback([f"{tier}! 造成 {dmg} 点伤害", f"敌人 HP {enemy.hp}/{enemy.max_hp}"], go_enemy=True)
        else:
            self._set_feedback(["攻击落空", "未造成伤害"], go_enemy=True)

    def _update_soul_movement(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        dx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        dy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        vec = pygame.Vector2(dx, dy)
        if vec.length_squared() > 0:
            vec = vec.normalize() * self.runtime.player.speed * dt
            self.soul_pos += vec

        margin = 22
        top_margin = margin + 24  # Lower upper movement ceiling by roughly one character height.
        self.soul_pos.x = max(self.battle_box.left + margin, min(self.battle_box.right - margin, self.soul_pos.x))
        self.soul_pos.y = max(self.battle_box.top + top_margin, min(self.battle_box.bottom - margin, self.soul_pos.y))

    def _draw(self) -> None:
        self.ui.draw_background(self.screen)
        offset_x, offset_y = self._enemy_hit_offset()
        enemy_center = (self.enemy_draw_center[0] + offset_x, self.enemy_draw_center[1] + offset_y)
        enemy_rect = self.ui.draw_enemy(self.screen, self.enemy_image, enemy_center, pygame.time.get_ticks() / 1000.0)
        if self.enemy_hit_effect_active and self.enemy_hit_effect_frames:
            idx = min(self.enemy_hit_effect_index, len(self.enemy_hit_effect_frames) - 1)
            frame = self.enemy_hit_effect_frames[idx]
            scale = max(1, int(frame.get_height() * 1.15))
            frame_scaled = pygame.transform.smoothscale(
                frame,
                (max(1, int(frame.get_width() * scale / max(1, frame.get_height()))), scale),
            )
            fx = int(enemy_rect.centerx - frame_scaled.get_width() * 0.56)
            fy = int(enemy_rect.centery - frame_scaled.get_height() * 0.60)
            self.screen.blit(frame_scaled, (fx, fy))
        self.ui.draw_hud(self.screen, self.runtime, self.runtime.player.name, self.battle_box)

        self.ui.draw_battle_box(self.screen, self.battle_box)
        if self.state in (BattleState.ENEMY_BULLETS, BattleState.FEEDBACK, BattleState.PLAYER_MENU):
            self.screen.blit(self.soul, self._soul_rect())
        if self.state == BattleState.ENEMY_BULLETS:
            draw_bullets(self.screen, self.bullets)

        if self.state == BattleState.PLAYER_ACTION and self.list_mode == "talk":
            self.ui.draw_list_menu(self.screen, self.battle_box, self._active_options(), self.list_selected, "叩心")
        elif self.state == BattleState.PLAYER_ACTION and self.list_mode == "item":
            self.ui.draw_list_menu(self.screen, self.battle_box, self._active_options(), self.list_selected, "物件")
        elif self.state == BattleState.PLAYER_ACTION and self.list_mode == "attack":
            self.ui.draw_attack_bar(self.screen, self.battle_box, self.attack_pointer)

        disabled_spare = not (self.runtime.enemy.spare_progress >= 60 and self.runtime.enemy.key_act_done)
        self.action_buttons = self.ui.draw_action_bar(self.screen, self.main_selected, disabled_spare)
        self.ui.draw_info(self.screen, self.info_lines)
