from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlayerState:
    name: str = "莲心"
    hp: int = 20
    max_hp: int = 20
    speed: float = 290.0


@dataclass
class EnemyState:
    name: str = "蜘蛛女孩"
    hp: int = 18
    max_hp: int = 18
    mind: int = 45
    max_mind: int = 100
    bond: int = 0
    max_bond: int = 100
    spare_progress: int = 0
    key_act_done: bool = False


@dataclass
class InventoryItem:
    name: str
    count: int
    desc: str


@dataclass
class BattleRuntime:
    player: PlayerState = field(default_factory=PlayerState)
    enemy: EnemyState = field(default_factory=EnemyState)
    inventory: list[InventoryItem] = field(
        default_factory=lambda: [
            InventoryItem("甘露", 2, "回复 5 HP"),
            InventoryItem("布条", 1, "用于叩心:递布"),
        ]
    )


@dataclass(frozen=True)
class EnemyPressureProfile:
    corner_base_amount: int
    corner_growth: float
    corner_cap: int
    top_base_amount: int
    top_growth: float
    top_cap: int
    size_boost_step_turns: int
    size_boost_cap: int
    speed_growth: float
    speed_growth_cap: float


DEFAULT_PRESSURE_PROFILE = EnemyPressureProfile(
    corner_base_amount=32,
    corner_growth=0.18,
    corner_cap=72,
    top_base_amount=38,
    top_growth=0.16,
    top_cap=86,
    size_boost_step_turns=2,
    size_boost_cap=6,
    speed_growth=0.05,
    speed_growth_cap=0.40,
)


ENEMY_PRESSURE_PROFILES: dict[str, EnemyPressureProfile] = {
    "蜘蛛女孩": EnemyPressureProfile(
        corner_base_amount=34,
        corner_growth=0.20,
        corner_cap=78,
        top_base_amount=40,
        top_growth=0.18,
        top_cap=92,
        size_boost_step_turns=2,
        size_boost_cap=6,
        speed_growth=0.055,
        speed_growth_cap=0.42,
    ),
}


def get_enemy_pressure_profile(enemy_name: str) -> EnemyPressureProfile:
    return ENEMY_PRESSURE_PROFILES.get(enemy_name, DEFAULT_PRESSURE_PROFILE)


def get_item(runtime: BattleRuntime, name: str) -> InventoryItem | None:
    for item in runtime.inventory:
        if item.name == name:
            return item
    return None


def clamp_enemy_stats(enemy: EnemyState) -> None:
    enemy.hp = max(0, min(enemy.max_hp, enemy.hp))
    enemy.mind = max(0, min(enemy.max_mind, enemy.mind))
    enemy.bond = max(0, min(enemy.max_bond, enemy.bond))
    enemy.spare_progress = max(0, min(100, enemy.spare_progress))


def refresh_spare_progress(enemy: EnemyState) -> None:
    enemy.spare_progress = max(enemy.spare_progress, enemy.bond)
    clamp_enemy_stats(enemy)
