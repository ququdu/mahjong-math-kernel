# -*- coding: utf-8 -*-
"""向听数（shanten）——手牌距离听牌还差几步。

三个方程都在这里：

* 标准型  ``shanten = 8 - 2*面子 - 搭子 - 雀头``（式子没变，但用带剪枝的
  DFS 精确求解，副露也算进面子数）
* 七对子  ``shanten = 6 - 对子数 + max(0, 7 - 种类数)``
* 十三幺  ``shanten = 13 - 幺九种类数 - (是否已有幺九对子)``

返回值语义：``-1`` 表示已经和牌，``0`` 表示听牌，``n`` 表示 n 向听。
"""

from __future__ import annotations

from functools import lru_cache

from .tiles import (
    NUM_TILE_TYPES,
    Z_START,
    YAOCHU,
    to_counts,
)

INF_SHANTEN = 8


# ---------------------------------------------------------------------------
#  标准型
# ---------------------------------------------------------------------------

def _standard_shanten(counts, open_melds):
    """带安全剪枝的 DFS。counts 必须是被本函数独占的可变列表。

    注意：这里刻意不限制“面子+搭子总数 ≤ 4”。多出来的搭子虽然不计分，
    但它们占住的牌可以重新组成面子，限制住会漏解（实测会误报）。
    所以改用“剩余牌张数能拿到的分数上限”做剪枝，方向是安全的。
    """
    best = 100
    open_m = open_melds
    total = 0
    for c in counts:
        total += c

    def dfs(i, melds, partials, pair, remaining):
        nonlocal best, total

        m_total = melds + open_m
        # 面子最多算 4 组，多出来的张数（非法张数输入）不影响公式
        if m_total > 4:
            m_total = 4
        if m_total >= 4 and pair:
            value = 8 - 2 * m_total - pair
            if value < best:
                best = value
            return

        # 乐观估算：剩下的牌最多还能提供多少分。
        # 把“面子 / 搭子 / 雀头”看作一个松弛问题（忽略牌型限制，只算张数），
        # 枚举取出多少个额外面子，取最大值。因为是上界，剪掉的子树不可能更优。
        slots = 4 - m_total
        if slots <= 0:
            ub_score = 2 * m_total + 1
        elif partials == 0 and pair == 0:
            # 没有已有搭子/雀头时，面子每张牌收益严格最高，贪心就是最优，
            # 不用枚举，直接算（这条捷径覆盖了 DFS 的绝大多数节点）
            k1 = remaining // 3
            if k1 > slots:
                k1 = slots
            left = remaining - 3 * k1
            k2 = left // 2
            if k2 > slots - k1:
                k2 = slots - k1
            ub_score = 2 * (m_total + k1) + k2
            if left - 2 * k2 >= 2:
                ub_score += 1
        else:
            max_extra_m = remaining // 3
            if max_extra_m > slots:
                max_extra_m = slots
            ub_score = -1
            for k1 in range(0, max_extra_m + 1):
                used = 3 * k1
                k2_max = (remaining - used) // 2
                if k2_max > slots - k1:
                    k2_max = slots - k1
                room = slots - k1
                t_total = partials + k2_max
                if t_total > room:
                    t_total = room
                if pair:
                    pair_pts = 1
                elif partials > 0 or remaining - used >= 2:
                    pair_pts = 1
                else:
                    pair_pts = 0
                score = 2 * (m_total + k1) + t_total + pair_pts
                if score > ub_score:
                    ub_score = score
        if 8 - ub_score >= best:
            return

        while i < NUM_TILE_TYPES and counts[i] == 0:
            i += 1
        if i >= NUM_TILE_TYPES:
            avail = slots if slots > 0 else 0
            value = 8 - 2 * m_total - (partials if partials < avail else avail) - pair
            if value < best:
                best = value
            return

        suit_pos = i % 9
        numeric = i < Z_START

        # 刻子
        if counts[i] >= 3:
            counts[i] -= 3
            dfs(i, melds + 1, partials, pair, remaining - 3)
            counts[i] += 3

        # 顺子
        if numeric and suit_pos <= 6 and counts[i + 1] and counts[i + 2]:
            counts[i] -= 1
            counts[i + 1] -= 1
            counts[i + 2] -= 1
            dfs(i, melds + 1, partials, pair, remaining - 3)
            counts[i] += 1
            counts[i + 1] += 1
            counts[i + 2] += 1

        if counts[i] >= 2:
            # 对子当雀头
            if not pair:
                counts[i] -= 2
                dfs(i, melds, partials, 1, remaining - 2)
                counts[i] += 2
            # 对子当搭子
            counts[i] -= 2
            dfs(i, melds, partials + 1, pair, remaining - 2)
            counts[i] += 2

        # 两面 / 边张搭子
        if numeric and suit_pos <= 7 and counts[i + 1]:
            counts[i] -= 1
            counts[i + 1] -= 1
            dfs(i, melds, partials + 1, pair, remaining - 2)
            counts[i] += 1
            counts[i + 1] += 1

        # 嵌张搭子
        if numeric and suit_pos <= 6 and counts[i + 2]:
            counts[i] -= 1
            counts[i + 2] -= 1
            dfs(i, melds, partials + 1, pair, remaining - 2)
            counts[i] += 1
            counts[i + 2] += 1

        # 这张牌不再参与任何结构
        dropped = counts[i]
        counts[i] = 0
        dfs(i + 1, melds, partials, pair, remaining - dropped)
        counts[i] = dropped

    dfs(0, 0, 0, 0, total)
    return best


@lru_cache(maxsize=200000)
def _cached_standard(counts_key, open_melds):
    return _standard_shanten(list(counts_key), open_melds)


def shanten_standard(counts, open_melds=0):
    """标准型向听数（4 面子 + 1 雀头）"""
    if isinstance(counts, (list, tuple)):
        return _cached_standard(tuple(counts), open_melds)
    return _standard_shanten(list(counts), open_melds)


# ---------------------------------------------------------------------------
#  七对子 / 十三幺
# ---------------------------------------------------------------------------

def shanten_chiitoi(counts):
    """七对子：6 - 对子数 + max(0, 7 - 种类数)"""
    pairs = 0
    kinds = 0
    for c in counts:
        if c >= 1:
            kinds += 1
        if c >= 2:
            pairs += 1
    return 6 - pairs + max(0, 7 - kinds)


def shanten_kokushi(counts):
    """十三幺：13 - 幺九种类数 - (有没有幺九对子)"""
    kinds = 0
    has_pair = False
    for t in YAOCHU:
        c = counts[t]
        if c >= 1:
            kinds += 1
            if c >= 2:
                has_pair = True
    return 13 - kinds - (1 if has_pair else 0)


# ---------------------------------------------------------------------------
#  合并入口
# ---------------------------------------------------------------------------

def total_tiles(counts):
    return sum(counts)


def shanten(counts, open_melds=0, allow_chiitoi=True, allow_kokushi=True):
    """综合向听数（取标准型 / 七对子 / 十三幺的最小值）。

    特殊型只在门清（无副露）且手牌数为 13 或 14 张时才有意义。
    """
    if isinstance(counts, tuple):
        counts = list(counts)

    best = shanten_standard(counts, open_melds)

    if open_melds == 0:
        n = sum(counts)
        if n in (13, 14):
            if allow_chiitoi:
                s = shanten_chiitoi(counts)
                if s < best:
                    best = s
            if allow_kokushi:
                s = shanten_kokushi(counts)
                if s < best:
                    best = s
    return best


def shanten_from_tiles(tiles, open_melds=0, **kw):
    return shanten(to_counts(tiles), open_melds, **kw)


# ---------------------------------------------------------------------------
#  听牌形（向听 0 时的待牌）
# ---------------------------------------------------------------------------

def tenpai_tiles(counts, open_melds=0, visible=None, allow_chiitoi=True,
                 allow_kokushi=True):
    """返回 {牌索引: 剩余张数}：使手牌和牌的所有牌。

    手牌必须是 13 张（3n+1）形。已和牌时返回空字典。
    """
    counts = list(counts)
    if visible is None:
        visible = [0] * NUM_TILE_TYPES

    base = shanten(counts, open_melds, allow_chiitoi, allow_kokushi)
    if base < 0:
        return {}
    if base > 0:
        return {}

    result = {}
    for t in range(NUM_TILE_TYPES):
        if counts[t] + visible[t] >= 4:
            continue
        counts[t] += 1
        s = shanten(counts, open_melds, allow_chiitoi, allow_kokushi)
        counts[t] -= 1
        if s < 0:
            result[t] = 4 - counts[t] - visible[t]
    return result
