from __future__ import annotations

from pathlib import Path

SCREEN_WIDTH = 1536
SCREEN_HEIGHT = 1024
FPS = 60

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = PROJECT_ROOT / "assets"
ATTACK_ASSET_DIR = ASSET_DIR / "attack"
FONT_CANDIDATES = [
    ASSET_DIR / "fonts" / "霞鹜文楷+Bold.ttf",
    ASSET_DIR / "fonts" / "SourceHanSerifCN-Bold-2.otf",
]

BATTLE_BG = ATTACK_ASSET_DIR / "zdbg.jpg"
ENEMY_IMAGE_CANDIDATES = [
    ATTACK_ASSET_DIR / "蛛蜘女孩.png",
    ATTACK_ASSET_DIR / "蜘蛛女孩.png",
]
AVATAR_FRAME = ATTACK_ASSET_DIR / "头像框.png"
AVATAR_IMAGE = ATTACK_ASSET_DIR / "头像.png"
HP_BAR_BG = ATTACK_ASSET_DIR / "血条.png"
RED_BLOCK = ATTACK_ASSET_DIR / "红块.png"
BLUE_BLOCK = ATTACK_ASSET_DIR / "蓝块.png"
SOUL_IMAGE = ATTACK_ASSET_DIR / "莲花.png"
