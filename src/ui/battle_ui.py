from __future__ import annotations

import math
import pygame

from src.battle.data import BattleRuntime


class BattleUI:
    def __init__(
        self,
        background: pygame.Surface,
        avatar_frame: pygame.Surface,
        avatar: pygame.Surface,
        bar_bg: pygame.Surface,
        red_block: pygame.Surface,
        blue_block: pygame.Surface,
        enemy_name: str,
        font_large: pygame.font.Font,
        font_mid: pygame.font.Font,
        font_small: pygame.font.Font,
    ) -> None:
        self.background = background
        self.avatar_frame = avatar_frame
        self.avatar = avatar
        self.bar_bg = bar_bg
        self.red_block = red_block
        self.blue_block = blue_block
        self.enemy_name = enemy_name
        self.font_large = font_large
        self.font_mid = font_mid
        self.font_small = font_small
        self.main_actions = ["攻伐", "叩心", "物件", "释怀"]

    def draw_background(self, screen: pygame.Surface) -> None:
        w, h = screen.get_size()
        screen.fill((0, 0, 0))
        scale = min(w / self.background.get_width(), h / self.background.get_height())
        draw_w = max(1, int(self.background.get_width() * scale))
        draw_h = max(1, int(self.background.get_height() * scale))
        bg = pygame.transform.smoothscale(self.background, (draw_w, draw_h))
        x = (w - draw_w) // 2
        y = (h - draw_h) // 2
        screen.blit(bg, (x, y))

        fog = pygame.Surface((w, h), pygame.SRCALPHA)
        fog.fill((8, 8, 12, 52))
        screen.blit(fog, (0, 0))

    def draw_enemy(self, screen: pygame.Surface, enemy_surface: pygame.Surface, center: tuple[int, int], t: float) -> pygame.Rect:
        offset_y = int(math.sin(t * 2.4) * 6)
        rect = enemy_surface.get_rect(center=(center[0], center[1] + offset_y))
        screen.blit(enemy_surface, rect)
        return rect

    def _draw_ratio_bar(
        self,
        screen: pygame.Surface,
        pos: tuple[int, int],
        ratio: float,
        blocks: int,
        use_blue: bool = False,
        bar_w: int = 290,
    ) -> None:
        x, y = pos
        bg = pygame.transform.smoothscale(self.bar_bg, (bar_w, 24))
        screen.blit(bg, (x, y))

        # HP fill uses left-aligned block count exactly matched to ratio.
        clamped_ratio = max(0.0, min(1.0, ratio))
        filled = blocks if clamped_ratio >= 0.999 else int(blocks * clamped_ratio)
        block_img = self.blue_block if use_blue else self.red_block
        block_w = max(8, (bar_w - 22) // blocks)
        block = pygame.transform.smoothscale(block_img, (block_w, 14))
        for i in range(filled):
            screen.blit(block, (x + 10 + i * block_w, y + 5))

    def _draw_blocks_only(
        self,
        screen: pygame.Surface,
        pos: tuple[int, int],
        ratio: float,
        blocks: int,
        use_blue: bool = False,
        block_w: int = 24,
        block_h: int = 14,
        gap: int = 2,
    ) -> None:
        x, y = pos
        clamped_ratio = max(0.0, min(1.0, ratio))
        filled = blocks if clamped_ratio >= 0.999 else int(blocks * clamped_ratio)
        block_img = self.blue_block if use_blue else self.red_block
        block = pygame.transform.smoothscale(block_img, (block_w, block_h))
        for i in range(filled):
            screen.blit(block, (x + i * (block_w + gap), y))

    def draw_hud(
        self,
        screen: pygame.Surface,
        runtime: BattleRuntime,
        player_name: str,
        battle_box: pygame.Rect,
    ) -> None:
        w, h = screen.get_size()
        sx = w / 1536.0
        sy = h / 1024.0

        def rx(v: float) -> int:
            return int(round(v * sx))

        def ry(v: float) -> int:
            return int(round(v * sy))

        # These positions follow assets/attack/attack_UI.json object coordinates.
        frame_rect = pygame.Rect(rx(43), ry(72), rx(599), ry(232))
        avatar_rect = pygame.Rect(rx(72), ry(110), rx(156), ry(156))
        hp_bar_pos = (rx(299), ry(180))
        mind_blocks_pos = (rx(313), ry(222))
        qingsi_blocks_pos = (rx(299), ry(250))

        frame = pygame.transform.smoothscale(self.avatar_frame, frame_rect.size)
        avatar = pygame.transform.smoothscale(self.avatar, avatar_rect.size)
        screen.blit(frame, frame_rect)
        screen.blit(avatar, avatar_rect)

        enemy = runtime.enemy
        player = runtime.player

        # Enemy title: shift left ~1 Chinese character and down ~half character.
        title = self.font_mid.render(self.enemy_name, True, (240, 230, 206))
        title_shadow = self.font_mid.render(self.enemy_name, True, (16, 12, 10))
        screen.blit(title_shadow, (rx(292), ry(122)))
        screen.blit(title, (rx(290), ry(120)))

        # HP value: smaller and placed right after "HP", above the health bar.
        hp_value = self.font_small.render(f"{enemy.hp}/{enemy.max_hp}", True, (236, 214, 190))
        hp_value_shadow = self.font_small.render(f"{enemy.hp}/{enemy.max_hp}", True, (16, 12, 10))

        self._draw_ratio_bar(screen, hp_bar_pos, enemy.hp / max(1, enemy.max_hp), 20, use_blue=False, bar_w=rx(265))
        # Draw HP number after the bar so it stays on top.
        screen.blit(hp_value_shadow, (rx(408), ry(186)))
        screen.blit(hp_value, (rx(406), ry(184)))

        # 心绪/情丝: no bar background, only red/blue block counts by progress.
        self._draw_blocks_only(screen, mind_blocks_pos, enemy.mind / max(1, enemy.max_mind), 10, use_blue=False, block_w=rx(24), block_h=ry(14), gap=max(1, rx(2)))
        self._draw_blocks_only(screen, qingsi_blocks_pos, enemy.spare_progress / 100.0, 10, use_blue=True, block_w=rx(24), block_h=ry(14), gap=max(1, rx(2)))

        screen.blit(self.font_small.render("心绪", True, (218, 224, 244)), (rx(246), ry(206)))
        screen.blit(self.font_small.render("情丝", True, (246, 224, 212)), (rx(246), ry(234)))

        status = self.font_mid.render(f"{player_name}  HP {player.hp}/{player.max_hp}", True, (242, 242, 248))
        status_shadow = self.font_mid.render(f"{player_name}  HP {player.hp}/{player.max_hp}", True, (12, 12, 16))
        status_rect = status.get_rect(center=(battle_box.centerx, int(round(battle_box.bottom + ry(10)))))
        shadow_rect = status_rect.move(2, 2)
        screen.blit(status_shadow, shadow_rect)
        screen.blit(status, status_rect)

    def draw_battle_box(self, screen: pygame.Surface, box: pygame.Rect) -> None:
        # The background artwork already contains the battle frame.
        return

    def draw_action_bar(self, screen: pygame.Surface, selected: int, disabled_spare: bool) -> list[pygame.Rect]:
        buttons: list[pygame.Rect] = []
        w = screen.get_width()
        h = screen.get_height()
        btn_w = min(210, int(w * 0.14))
        btn_h = 56

        # Fixed centers aligned to baked slots on attack background artwork.
        slot_center_x = [
            int(round(w * ((440 + 12) / 1536.0))),
            int(round(w * (651 / 1536.0))),
            int(round(w * ((862 - 12) / 1536.0))),
            int(round(w * ((1073 - 24) / 1536.0))),
        ]
        slot_center_y = int(round(h * (818 / 1024.0)))

        mouse_pos = pygame.mouse.get_pos()

        for i, label in enumerate(self.main_actions):
            rect = pygame.Rect(0, 0, btn_w, btn_h)
            rect.center = (slot_center_x[i], slot_center_y)
            buttons.append(rect)
            is_selected = i == selected
            is_hovered = rect.collidepoint(mouse_pos)
            disabled = label == "释怀" and disabled_spare

            text_color = (228, 218, 188)
            scale = 1.0
            if (is_selected or is_hovered) and not disabled:
                text_color = (232, 92, 92)
                scale = 1.12
            if disabled:
                text_color = (168, 160, 150)
                scale = 1.0

            shadow = self.font_mid.render(label, True, (20, 14, 10))
            txt = self.font_mid.render(label, True, text_color)
            if abs(scale - 1.0) > 1e-4:
                tw, th = txt.get_size()
                txt = pygame.transform.smoothscale(txt, (max(1, int(tw * scale)), max(1, int(th * scale))))
                sw, sh = shadow.get_size()
                shadow = pygame.transform.smoothscale(shadow, (max(1, int(sw * scale)), max(1, int(sh * scale))))

            text_rect = txt.get_rect(center=rect.center)
            shadow_rect = shadow.get_rect(center=(text_rect.centerx + 2, text_rect.centery + 2))
            screen.blit(shadow, shadow_rect)
            screen.blit(txt, text_rect)

        return buttons

    def draw_info(self, screen: pygame.Surface, lines: list[str]) -> None:
        w = screen.get_width()
        h = screen.get_height()
        text_x = int(round(w * (276 / 1536.0))) + int(round(w * (120 / 1536.0)))
        text_y = int(round(h * (884 / 1024.0)))

        text1_shadow = self.font_small.render(lines[0] if lines else "", True, (12, 12, 16))
        text1 = self.font_small.render(lines[0] if lines else "", True, (232, 236, 244))
        screen.blit(text1_shadow, (text_x + 2, text_y + 2))
        screen.blit(text1, (text_x, text_y))

        if len(lines) > 1:
            text2_shadow = self.font_small.render(lines[1], True, (12, 12, 16))
            text2 = self.font_small.render(lines[1], True, (214, 224, 236))
            screen.blit(text2_shadow, (text_x + 2, text_y + 34))
            screen.blit(text2, (text_x, text_y + 32))

    def draw_list_menu(self, screen: pygame.Surface, box: pygame.Rect, options: list[str], selected: int, title: str) -> None:
        screen.blit(self.font_mid.render(title, True, (245, 240, 228)), (box.left + 26, box.top + 20))
        row_h = 46
        for i, text in enumerate(options):
            color = (255, 236, 170) if i == selected else (228, 236, 248)
            line = self.font_small.render(text, True, color)
            screen.blit(line, (box.left + 52, box.top + 78 + i * row_h))

    def draw_attack_bar(self, screen: pygame.Surface, box: pygame.Rect, pointer_ratio: float) -> None:
        t = pygame.time.get_ticks() / 1000.0
        bar = pygame.Rect(box.left + 96, box.centery - 20, box.width - 192, 40)

        # Ancient dark-metal shell.
        pygame.draw.rect(screen, (16, 18, 24), bar, border_radius=8)
        pygame.draw.rect(screen, (104, 108, 118), bar, width=2, border_radius=8)
        pygame.draw.rect(screen, (42, 46, 56), bar.inflate(-4, -4), width=1, border_radius=7)

        # Weathered cracks with faint ember glow.
        crack_color = (216, 118, 40, 26)
        crack_glow = pygame.Surface((bar.width, bar.height), pygame.SRCALPHA)
        for i in range(7):
            cx = int(bar.width * (0.08 + i * 0.13))
            cy = int(bar.height * (0.34 + 0.18 * math.sin(t * 0.9 + i * 0.7)))
            pygame.draw.line(crack_glow, crack_color, (cx - 8, cy - 3), (cx + 8, cy + 2), 1)
        screen.blit(crack_glow, bar.topleft)

        inner = bar.inflate(-10, -12)
        pygame.draw.rect(screen, (22, 24, 30), inner, border_radius=5)

        # Layered zones:
        # low (base full bar), mid (center 1/3), crit (center 1/6).
        low_zone = pygame.Rect(inner.left, inner.top + 1, inner.width, inner.height - 2)
        mid_w = max(1, inner.width // 3)
        crit_w = max(1, inner.width // 6)
        mid_zone = pygame.Rect(inner.centerx - mid_w // 2, inner.top + 4, mid_w, max(8, inner.height - 8))
        crit_zone = pygame.Rect(inner.centerx - crit_w // 2, inner.top + 7, crit_w, max(6, inner.height - 14))
        pygame.draw.rect(screen, (82, 30, 38), low_zone, border_radius=4)
        pygame.draw.rect(screen, (52, 34, 86), mid_zone, border_radius=4)
        pygame.draw.rect(screen, (146, 24, 38), crit_zone, border_radius=4)
        pygame.draw.rect(screen, (94, 56, 60), low_zone, width=1, border_radius=4)
        pygame.draw.rect(screen, (86, 68, 126), mid_zone, width=1, border_radius=4)
        pygame.draw.rect(screen, (198, 84, 74), crit_zone, width=1, border_radius=4)

        # Golden sparks around critical area.
        spark_layer = pygame.Surface((inner.width, inner.height), pygame.SRCALPHA)
        for i in range(10):
            phase = t * (1.2 + i * 0.09) + i * 0.7
            sx = int((crit_zone.left - inner.left) + crit_zone.width * (0.08 + 0.84 * ((math.sin(phase) + 1) * 0.5)))
            sy = int(inner.height * (0.28 + 0.48 * ((math.sin(phase * 1.9) + 1) * 0.5)))
            r = 1 if i % 2 else 2
            pygame.draw.circle(spark_layer, (242, 198, 108, 115), (sx, sy), r)
        screen.blit(spark_layer, inner.topleft)

        # Rune glow along edges.
        rune_layer = pygame.Surface((bar.width, bar.height), pygame.SRCALPHA)
        rune_color = (110, 168, 255, 42)
        for i in range(12):
            rx = int(bar.width * (0.06 + i * 0.08))
            h = 4 + (i % 3)
            pygame.draw.line(rune_layer, rune_color, (rx, 4), (rx, 4 + h), 1)
            pygame.draw.line(rune_layer, rune_color, (rx, bar.height - 4), (rx, bar.height - 4 - h), 1)
        screen.blit(rune_layer, bar.topleft)

        # Ghostly pale-blue flame pointer.
        pointer_x = int(inner.left + inner.width * max(0.0, min(1.0, pointer_ratio)))
        flame = pygame.Surface((26, inner.height + 34), pygame.SRCALPHA)
        flame_mid = flame.get_width() // 2
        bob = math.sin(t * 6.2) * 1.3
        pygame.draw.ellipse(flame, (156, 216, 255, 34), (2, 8, 22, flame.get_height() - 4))
        pygame.draw.ellipse(flame, (190, 234, 255, 62), (5, 12 + bob, 16, flame.get_height() - 14))
        pygame.draw.rect(flame, (212, 242, 255, 180), (flame_mid - 1, 8, 2, flame.get_height() - 16), border_radius=1)
        screen.blit(flame, (pointer_x - flame_mid, inner.top - 16))
        pygame.draw.line(screen, (230, 248, 255), (pointer_x, inner.top - 8), (pointer_x, inner.bottom + 8), 2)

        # Subtle dark mist around corners.
        mist = pygame.Surface((bar.width + 40, bar.height + 26), pygame.SRCALPHA)
        for i in range(4):
            mx = 14 + i * (mist.get_width() - 28) // 3
            my = 9 + int(math.sin(t * (0.9 + i * 0.2) + i) * 3)
            pygame.draw.ellipse(mist, (10, 10, 14, 38), (mx - 16, my, 34, 14))
        screen.blit(mist, (bar.left - 20, bar.top - 10))

        hint = self.font_small.render("Space/Enter 定格", True, (216, 220, 232))
        screen.blit(hint, (bar.left, bar.bottom + 14))
