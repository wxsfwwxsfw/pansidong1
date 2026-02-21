from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame


@dataclass
class Bullet:
    pos: pygame.Vector2
    vel: pygame.Vector2
    radius: int
    damage: int
    color: tuple[int, int, int]

    @property
    def rect(self) -> pygame.Rect:
        size = self.radius * 2
        return pygame.Rect(int(self.pos.x - self.radius), int(self.pos.y - self.radius), size, size)


def spawn_corner_drops(box: pygame.Rect, amount: int = 32) -> list[Bullet]:
    corners = [
        pygame.Vector2(box.left + 8, box.top + 8),
        pygame.Vector2(box.right - 8, box.top + 8),
        pygame.Vector2(box.left + 8, box.bottom - 8),
        pygame.Vector2(box.right - 8, box.bottom - 8),
    ]
    bullets: list[Bullet] = []
    for i in range(amount):
        c = corners[i % len(corners)]

        # Aim toward a moving focus region near the center to increase pressure.
        target_x = random.uniform(box.centerx - box.width * 0.25, box.centerx + box.width * 0.25)
        target_y = random.uniform(box.centery - box.height * 0.12, box.bottom - 24)
        direction = pygame.Vector2(target_x - c.x, target_y - c.y)
        if direction.length_squared() == 0:
            direction = pygame.Vector2(0, 1)
        direction = direction.normalize()

        speed = random.uniform(165, 245)
        drift = pygame.Vector2(random.uniform(-22, 22), random.uniform(-14, 14))
        vel = direction * speed + drift

        bullets.append(
            Bullet(
                pos=pygame.Vector2(c.x + random.uniform(-16, 16), c.y + random.uniform(-12, 12)),
                vel=vel,
                radius=6,
                damage=2,
                color=(255, 120, 120),
            )
        )
    return bullets


def spawn_top_threads(box: pygame.Rect, amount: int = 38) -> list[Bullet]:
    bullets: list[Bullet] = []
    for _ in range(amount):
        x = random.uniform(box.left + 12, box.right - 12)
        y = random.uniform(box.top + 2, box.top + 28)
        speed = random.uniform(220, 320)
        bullets.append(
            Bullet(
                pos=pygame.Vector2(x, y),
                vel=pygame.Vector2(random.uniform(-48, 48), speed),
                radius=5,
                damage=2,
                color=(120, 180, 255),
            )
        )
    return bullets


def update_bullets(
    bullets: list[Bullet],
    dt: float,
    box: pygame.Rect,
    player_rect: pygame.Rect,
) -> tuple[int, int]:
    damage = 0
    hit_count = 0
    alive: list[Bullet] = []
    for bullet in bullets:
        bullet.pos += bullet.vel * dt
        if bullet.rect.colliderect(player_rect):
            damage += bullet.damage
            hit_count += 1
            continue
        if box.inflate(30, 30).colliderect(bullet.rect):
            alive.append(bullet)
    bullets[:] = alive
    return damage, hit_count


def draw_bullets(surface: pygame.Surface, bullets: list[Bullet]) -> None:
    for bullet in bullets:
        pygame.draw.circle(surface, bullet.color, (int(bullet.pos.x), int(bullet.pos.y)), bullet.radius)
