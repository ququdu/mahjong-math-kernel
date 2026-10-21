# -*- coding: utf-8 -*-
"""副露（吃 / 碰 / 明杠 / 暗杠 / 加杠）与和牌拆解。

和牌拆解是番种识别的地基：国标 81 番里绝大多数规则都是"在某个面子组合上
看有没有某种形状"，所以这里要枚举**全部**合法拆解，而不是随便找一个。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple

from .tiles import NUM_TILE_TYPES, Z_START

# 拆解结果里的面子类型（只区分形状，不区分明暗）
TRIPLET = "t"
SEQUENCE = "s"


@dataclass(frozen=True)
class Meld:
    """副露。tile 对顺子表示起始牌，对刻子/杠表示牌本身。"""

    kind: str          # 'chi' | 'pon' | 'minkan' | 'ankan' | 'kakan'
    tile: int

    @property
    def is_kan(self):
        return self.kind in ("minkan", "ankan", "kakan")

    @property
    def is_triplet_shape(self):
        return self.kind != "chi"

    @property
    def is_concealed(self):
        return self.kind == "ankan"

    @property
    def open(self):
        return not self.is_concealed

    def tiles(self):
        if self.kind == "chi":
            return (self.tile, self.tile + 1, self.tile + 2)
        n = 4 if self.is_kan else 3
        return (self.tile,) * n

    def to_dict(self):
        return {"kind": self.kind, "tile": self.tile}


MELD_ALIASES = {
    "chi": "chi", "吃": "chi",
    "pon": "pon", "pong": "pon", "碰": "pon",
    "minkan": "minkan", "kan": "minkan", "明杠": "minkan", "大明杠": "minkan",
    "ankan": "ankan", "暗杠": "ankan",
    "kakan": "kakan", "加杠": "kakan", "小明杠": "kakan",
}


def parse_meld(kind, tile):
    k = MELD_ALIASES.get(str(kind).strip().lower())
    if k is None:
        k = MELD_ALIASES.get(str(kind).strip())
    if k is None:
        raise ValueError("未知副露类型: %r" % (kind,))
    return Meld(k, int(tile))


@dataclass(frozen=True)
class Decomposition:
    """一种完整拆解：若干面子 + 一个雀头。"""

    melds: Tuple[Tuple[str, int], ...]
    pair: int

    def shape_key(self):
        return (tuple(sorted(self.melds)), self.pair)


# ---------------------------------------------------------------------------
#  枚举全部拆解
# ---------------------------------------------------------------------------

def decompose_standard(counts, need_melds=4):
    """枚举 counts 拆成 need_melds 个面子 + 1 个雀头的所有方案。

    返回 ``[Decomposition, ...]``。counts 为 34 长度计数列表。
    """
    counts = list(counts)
    out = []

    def take_melds(c, start, need, acc, sink):
        if need == 0:
            if not any(c):
                sink.append(tuple(acc))
            return
        i = start
        n = len(c)
        while i < n and c[i] == 0:
            i += 1
        if i >= n:
            return
        # 刻子
        if c[i] >= 3:
            c[i] -= 3
            acc.append((TRIPLET, i))
            take_melds(c, i, need - 1, acc, sink)
            acc.pop()
            c[i] += 3
        # 顺子
        if i < Z_START and i % 9 <= 6 and c[i + 1] and c[i + 2]:
            c[i] -= 1
            c[i + 1] -= 1
            c[i + 2] -= 1
            acc.append((SEQUENCE, i))
            take_melds(c, i, need - 1, acc, sink)
            acc.pop()
            c[i] += 1
            c[i + 1] += 1
            c[i + 2] += 1

    for p in range(NUM_TILE_TYPES):
        if counts[p] >= 2:
            counts[p] -= 2
            found = []
            take_melds(counts, 0, need_melds, [], found)
            for melds in found:
                out.append(Decomposition(tuple(melds), p))
            counts[p] += 2

    # 去重（同形不同枚举顺序）
    seen = set()
    uniq = []
    for d in out:
        k = d.shape_key()
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq


def decompose_with_melds(counts, open_melds: Iterable[Meld] = ()):
    """把暗牌拆解与已副露的面子合并，用于番种识别。

    面子类型使用 4 个值，带 ``o`` 后缀的表示“明面”：

    ======  ==================
    's'     暗顺子
    't'     暗刻（暗杠也算暗刻）
    'so'    明顺子（吃）
    'to'    明刻（碰 / 明杠 / 加杠）
    ======  ==================
    """
    open_melds = list(open_melds)
    need = 4 - len(open_melds)
    if need < 0:
        return []
    open_shapes = []
    for m in open_melds:
        if m.kind == "chi":
            open_shapes.append((SEQUENCE + "o", m.tile))
        elif m.kind == "ankan":
            open_shapes.append((TRIPLET, m.tile))
        else:
            open_shapes.append((TRIPLET + "o", m.tile))

    results = []
    for d in decompose_standard(counts, need):
        results.append(Decomposition(tuple(open_shapes) + d.melds, d.pair))
    return results


def normalize_kind(kind):
    """'so' -> 's'，'to' -> 't'"""
    return kind[0]


def is_open_kind(kind):
    return kind.endswith("o")


# ---------------------------------------------------------------------------
#  特殊和牌形
# ---------------------------------------------------------------------------

def is_chiitoi(counts):
    """七对子：7 个对子。4 张相同算两对（国标/血战允许，日麻不允许）。

    条件简化为“14 张且每种牌都是偶数张”。
    """
    if sum(counts) != 14:
        return False
    return all(c % 2 == 0 for c in counts)


def is_kokushi(counts):
    """十三幺：13 种幺九牌齐 + 其中一张成对。"""
    if sum(counts) != 14:
        return False
    yao = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33]
    yao_set = set(yao)
    for t in range(NUM_TILE_TYPES):
        if t not in yao_set and counts[t]:
            return False
    kinds = 0
    pair = 0
    for t in yao:
        c = counts[t]
        if c == 0:
            return False
        if c == 2:
            pair += 1
            kinds += 1
        elif c == 1:
            kinds += 1
        else:
            return False
    return kinds == 13 and pair == 1


def is_kokushi_13wait(counts):
    """十三面听：和牌前 13 张互不相同的幺九牌（用于判定十三幺的听牌形）。"""
    if sum(counts) != 13:
        return False
    yao = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33]
    return all(counts[t] == 1 for t in yao)


# 全不靠/七星不靠需要的 147 / 258 / 369 位置
_TERMINAL_SEQ_POS = (0, 3, 6)   # 数牌内的 rank-1


def _is_all_singles(counts):
    return all(c <= 1 for c in counts)


def is_all_unrelated(counts):
    """全不靠：14 张全部单张，来自 3 种花色的 147/258/369 三组（不能错位）
    与东南西北中发白。

    “不能错位”= 每个位置组（147 / 258 / 369）只能来自单一花色，
    且不同位置组必须来自不同花色。
    """
    if sum(counts) != 14 or not _is_all_singles(counts):
        return False
    group_suit = {}
    for suit in range(3):
        for pos in range(9):
            if counts[suit * 9 + pos]:
                g = pos % 3
                if g in group_suit and group_suit[g] != suit:
                    return False
                group_suit[g] = suit
    if not group_suit:
        return False
    return len(set(group_suit.values())) == len(group_suit)


def is_seven_stars(counts):
    """七星不靠：全不靠 + 东南西北中发白 7 种字牌全有。"""
    if sum(counts) != 14:
        return False
    if not all(counts[t] == 1 for t in range(27, 34)):
        return False
    return is_all_unrelated(counts)


def standard_alive(counts):
    """是否存在至少一种"4 面子 + 雀头"拆解（不含特殊型）。"""
    return bool(decompose_standard(counts, 4))
