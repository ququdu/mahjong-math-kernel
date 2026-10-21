# -*- coding: utf-8 -*-
"""合成测试图：不依赖任何真实素材，就能端到端验证识别链路。

每张牌按"花色定颜色 + 点数画圆点"的方式画出来，34 张互不相同。
``pytest`` 用它生成截图，再用识别链去认——如果能 100% 认对，
说明"切格 -> 匹配 -> 拼牌"这套逻辑没问题。真实素材的准确率取决于
你自己的模板包质量，那是标定工具的事。
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np

from .image import require_pil

TILE_W, TILE_H = 40, 56
GAP = 2
BG = (36, 42, 56)
SUIT_COLOR = {
    0: (198, 42, 42),    # 万 红
    1: (38, 92, 198),    # 筒 蓝
    2: (26, 130, 78),    # 条 绿
    3: (122, 58, 168),   # 字 紫
}


def _draw_tile(tile: int, size: Tuple[int, int] = (TILE_W, TILE_H)):
    require_pil()
    from PIL import Image, ImageDraw

    w, h = size
    img = Image.new("RGB", (w, h), (248, 248, 242))
    d = ImageDraw.Draw(img)
    suit = 0 if tile < 9 else (1 if tile < 18 else (2 if tile < 27 else 3))
    rank = tile % 9 + 1 if tile < 27 else tile - 26
    color = SUIT_COLOR[suit]

    d.rectangle([0, 0, w - 1, h - 1], outline=color, width=2)
    # 花色标记：左上角一条色带；字牌多一条竖带以便和数牌区分
    d.rectangle([0, 0, w - 1, 5], fill=color)
    if suit == 3:
        d.rectangle([0, 0, 5, h - 1], fill=color)

    # 点数用圆点表示：1..9 / 字牌 1..7
    cols = 3
    r = max(2, min(w, h) // 12)
    spacing_x = w // (cols + 1)
    for i in range(rank):
        row = i // cols
        col = i % cols
        cx = spacing_x * (col + 1)
        cy = 12 + row * (2 * r + 5)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    return np.array(img)


def make_tile_image(tile: int, size: Tuple[int, int] = (TILE_W, TILE_H)):
    return _draw_tile(tile, size)


def make_screenshot(tiles: Sequence[int],
                    size: Tuple[int, int] = (TILE_W, TILE_H),
                    gap: int = GAP,
                    origin: Tuple[int, int] = (10, 10),
                    canvas: Tuple[int, int] = (900, 300)):
    """把一串牌画成一张"截图"。"""
    require_pil()
    from PIL import Image

    w, h = size
    W, H = canvas
    img = Image.new("RGB", (W, H), BG)
    x0, y0 = origin
    for i, t in enumerate(tiles):
        tile_img = Image.fromarray(_draw_tile(t, size))
        img.paste(tile_img, (x0 + i * (w + gap), y0))
    return np.array(img)


def make_templates(size: Tuple[int, int] = (TILE_W, TILE_H)):
    """34 张模板（和合成截图同一种画法）。"""
    return {t: _draw_tile(t, size) for t in range(34)}


def layout_for(count=14, size=(TILE_W, TILE_H), gap=GAP, origin=(10, 10)):
    """给合成截图配一个版面。"""
    from .pack import Layout, Region

    w, h = size
    return Layout(hand=Region(x=origin[0], y=origin[1],
                              cell_w=w, cell_h=h,
                              pitch=w + gap, count=count),
                  notes="synthetic")
