# -*- coding: utf-8 -*-
"""模板包与版面配置：识别所需要的两份"先验"。

**模板包**（TemplatePack）—— 34 张牌面各一张小图。
    第一次用的时候从你自己的截图里"学"一遍（见 ``calibrate.py``），
    之后就固定下来，识别时只做比对。

**版面**（Layout）—— 手牌区、副露区在截图里的位置和格子尺寸。
    不同游戏、不同窗口大小都不一样，所以必须标定一次。

两个都能存成文件，跟着你走。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from .image import resize, to_float_rgb
from .match import Matcher

TILE_NAMES = (
    [str(n) + "m" for n in range(1, 10)]
    + [str(n) + "p" for n in range(1, 10)]
    + [str(n) + "s" for n in range(1, 10)]
    + ["东", "南", "西", "北", "白", "发", "中"]
)


# ---------------------------------------------------------------------------
#  模板包
# ---------------------------------------------------------------------------

class TemplatePack:
    """34 张牌面的模板集合。"""

    def __init__(self, size=(40, 56)):
        self.size = (int(size[0]), int(size[1]))   # (w, h)
        self.templates: Dict[int, np.ndarray] = {}

    # -- 维护 -----------------------------------------------------------

    def add(self, tile: int, image):
        """学习一张牌面（会自动缩放到统一尺寸）。"""
        if not 0 <= tile < 34:
            raise ValueError("牌索引必须在 0..33: %r" % (tile,))
        self.templates[int(tile)] = resize(to_float_rgb(image), self.size)

    def missing(self) -> List[int]:
        return [t for t in range(34) if t not in self.templates]

    def coverage(self) -> Dict:
        return {
            "learned": len(self.templates),
            "missing": [TILE_NAMES[t] for t in self.missing()],
            "complete": len(self.templates) == 34,
        }

    def matcher(self) -> Matcher:
        if not self.templates:
            raise ValueError("模板包是空的：先用标定工具学几张牌面")
        return Matcher(self.templates, (self.size[1], self.size[0]))

    def __len__(self):
        return len(self.templates)

    def __contains__(self, tile):
        return int(tile) in self.templates

    # -- 读写 -----------------------------------------------------------

    def save(self, path):
        meta = {"size": list(self.size), "count": len(self.templates)}
        payload = {"__meta__": np.array(json.dumps(meta))}
        for t, arr in self.templates.items():
            payload["tile_%d" % t] = arr.astype(np.float32)
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        np.savez_compressed(path, **payload)
        return path

    @classmethod
    def load(cls, path):
        data = np.load(path, allow_pickle=False)
        meta = json.loads(str(data["__meta__"]))
        pack = cls(size=tuple(meta.get("size", (40, 56))))
        for key in data.files:
            if key.startswith("tile_"):
                pack.templates[int(key[5:])] = data[key]
        return pack


# ---------------------------------------------------------------------------
#  版面
# ---------------------------------------------------------------------------

@dataclass
class Region:
    """一条横排牌的取图规则。"""

    x: int
    y: int
    cell_w: int
    cell_h: int
    pitch: float = 0.0
    count: int = 14

    def __post_init__(self):
        if not self.pitch:
            self.pitch = float(self.cell_w)

    def to_dict(self):
        return {"mode": "row", "x": int(self.x), "y": int(self.y),
                "cell_w": int(self.cell_w), "cell_h": int(self.cell_h),
                "pitch": float(self.pitch), "count": int(self.count)}

    @classmethod
    def from_dict(cls, d):
        return cls(x=int(d["x"]), y=int(d["y"]),
                   cell_w=int(d["cell_w"]), cell_h=int(d["cell_h"]),
                   pitch=float(d.get("pitch") or d["cell_w"]),
                   count=int(d.get("count", 14)))


@dataclass
class Layout:
    """整张截图的取图版面。"""

    hand: Optional[Region] = None
    melds: List[Region] = field(default_factory=list)
    notes: str = ""

    def to_dict(self):
        return {
            "version": 1,
            "hand": self.hand.to_dict() if self.hand else None,
            "melds": [m.to_dict() for m in self.melds],
            "notes": self.notes,
        }

    def roi(self, margin: int = 6):
        """手牌区 + 副露区的外接矩形（可以先裁剪截图再识别）。

        返回 ``(x, y, w, h)``。整屏截图里牌只占一小块时，先按这个矩形裁一刀，
        识别会快很多、也更准。
        """
        regions = [r for r in ([self.hand] if self.hand else []) + list(self.melds) if r]
        if not regions:
            return None
        x0 = min(r.x for r in regions) - margin
        y0 = min(r.y for r in regions) - margin
        x1 = max(r.x + r.pitch * max(0, r.count - 1) + r.cell_w for r in regions) + margin
        y1 = max(r.y + r.cell_h for r in regions) + margin
        return (max(0, int(x0)), max(0, int(y0)),
                max(1, int(x1 - x0)), max(1, int(y1 - y0)), )

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)
        return path

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return cls.from_dict(d)

    @classmethod
    def from_dict(cls, d):
        hand = Region.from_dict(d["hand"]) if d.get("hand") else None
        melds = [Region.from_dict(m) for m in d.get("melds") or []]
        return cls(hand=hand, melds=melds, notes=d.get("notes", ""))

    def shifted(self, dx: int, dy: int):
        """整份版面平移（截图被裁剪过时，用裁剪的偏移量平一下）。"""
        def move(r):
            return None if r is None else Region(
                x=r.x - dx, y=r.y - dy, cell_w=r.cell_w, cell_h=r.cell_h,
                pitch=r.pitch, count=r.count)
        return Layout(hand=move(self.hand), melds=[move(m) for m in self.melds],
                      notes=self.notes)


# ---------------------------------------------------------------------------
#  默认路径
# ---------------------------------------------------------------------------

def default_pack_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "vision_data", "templates.npz")


def default_layout_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "vision_data", "layout.json")
