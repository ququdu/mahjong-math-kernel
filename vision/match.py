# -*- coding: utf-8 -*-
"""模板匹配：把一个小格子和 34 张牌面对比，取最像的那张。

用的是**归一化互相关**（NCC）：

    NCC(a, b) = <a - mean(a), b - mean(b)> / (|a - mean(a)| · |b - mean(b)|)

好处是对整体亮度、对比度变化不敏感——不同截图工具、不同压缩率都能用。
没有 OpenCV 也能跑，numpy 向量化一次算完 34 个模板。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .image import resize, to_float_rgb

NUM_TILES = 34


def _features(a, gray=False) -> np.ndarray:
    """把一张小图变成匹配用的向量。

    默认用 **RGB 三通道**：数牌之间只靠颜色区分的地方很多（2万 vs 2筒），
    只转灰度会把颜色信息丢掉，实测会认错一整片牌。
    """
    arr = to_float_rgb(a)
    if gray:
        arr = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2])[..., None]
    return arr.ravel()


def _normalize(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float32).ravel()
    a = a - a.mean()
    n = float(np.linalg.norm(a))
    return a / n if n > 1e-8 else a


class Matcher:
    """把模板包预先归一化，之后每格只做一次矩阵乘法。"""

    def __init__(self, templates: Dict[int, np.ndarray], size: Optional[Tuple[int, int]] = None,
                 gray: bool = False):
        if not templates:
            raise ValueError("模板包是空的")
        first = np.asarray(list(templates.values())[0])
        self.size = size or first.shape[:2]   # (h, w)
        self.gray = gray
        tiles = sorted(templates)
        mat = []
        for t in tiles:
            img = np.asarray(templates[t])
            if img.shape[:2] != self.size:
                img = resize(to_float_rgb(img), (self.size[1], self.size[0]))
            mat.append(_normalize(_features(img, gray)))
        self.tiles = tiles
        self.matrix = np.stack(mat, axis=0)          # (34, N)
        self._by_tile = {t: mat[i] for i, t in enumerate(tiles)}

    def match(self, cell, topk: int = 3):
        """单格 -> [(牌索引, 分数), ...]，分数 1 表示完全一致。"""
        img = to_float_rgb(cell)
        if img.shape[:2] != self.size:
            img = resize(img, (self.size[1], self.size[0]))
        v = _normalize(_features(img, self.gray))
        scores = self.matrix @ v
        order = np.argsort(-scores)[:max(1, topk)]
        return [(self.tiles[i], float(scores[i])) for i in order]

    def match_cell(self, cell):
        """单格 -> (最像的牌, 分数, 次高牌, 分数)"""
        top = self.match(cell, topk=2)
        best = top[0]
        second = top[1] if len(top) > 1 else (None, -1.0)
        return best[0], best[1], second[0], second[1]

    def classify_cells(self, cells, min_score=0.35):
        """一排格子 -> (牌索引列表, 每格明细)"""
        out = []
        detail = []
        for cell in cells:
            tile, score, alt, alt_score = self.match_cell(cell)
            out.append(tile)
            detail.append({
                "tile": tile,
                "score": round(score, 4),
                "runner_up": alt,
                "runner_up_score": round(alt_score, 4),
                "ok": score >= min_score and (score - alt_score) > 0.02,
            })
        return out, detail

    def classify_blank_aware(self, cells, blank_score=0.55, min_score=0.35):
        """识别一排格子，允许中间/末尾有空位（空格子分数都会很低）。

        返回 (牌列表, 明细)。空格子不进列表。
        """
        tiles = []
        detail = []
        for cell in cells:
            tile, score, alt, alt_score = self.match_cell(cell)
            is_blank = score < blank_score
            detail.append({
                "tile": None if is_blank else tile,
                "best": tile,
                "score": round(score, 4),
                "runner_up": alt,
                "runner_up_score": round(alt_score, 4),
                "ok": (not is_blank) and score >= min_score,
            })
            if not is_blank:
                tiles.append(tile)
        return tiles, detail


def tile_index(suit, rank):
    """(0=万/1=筒/2=条/3=字, rank 1..) -> 0..33"""
    if suit == 3:
        return 26 + rank
    return suit * 9 + rank - 1


def parse_tile_string(text, honor_map=None):
    """'123m456p' / '1万2万3万' -> [0,1,2, ...]

    这里刻意不去 import 内核的解析器：识别层要保持"只懂图像和小整数"。
    """
    text = (text or "").strip().lower()
    out = []
    pending = []
    suit_of = {"m": 0, "w": 0, "万": 0, "p": 1, "t": 1, "筒": 1, "饼": 1,
               "s": 2, "条": 2, "索": 2, "z": 3, "字": 3}
    default_honor = {"东": 27, "南": 28, "西": 29, "北": 30, "白": 31, "发": 32, "中": 33}
    for ch in text:
        if ch.isdigit():
            pending.append(int(ch))
        elif ch in suit_of:
            s = suit_of[ch]
            for r in pending:
                out.append(tile_index(s, r))
            pending = []
        elif ch in default_honor:
            out.append(default_honor[ch])
            pending = []
        elif ch in " ,":
            continue
        else:
            raise ValueError("认不出的字符 %r" % ch)
    return out
