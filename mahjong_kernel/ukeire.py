# -*- coding: utf-8 -*-
"""有效牌与进张（牌效率）。

有效牌 = 摸进后向听数下降的牌；进张数 = 这些牌在牌山里还剩几张。
"牌效率" 定义成 有效牌张数 / 牌山剩余张数，也就是下一巡的直接命中率，
对应视频里的第 4 条方程。
"""

from __future__ import annotations

from functools import lru_cache

from .shanten import shanten
from .tiles import NUM_TILE_TYPES, to_counts


def remaining_copies(counts, visible, tile):
    """某张牌还剩几张可摸"""
    return max(0, 4 - counts[tile] - visible[tile])


def effective_tiles(counts, open_melds=0, visible=None, allow_chiitoi=True,
                    allow_kokushi=True, allowed=None):
    """有效牌（带缓存版，见 ``_effective_tiles``）"""
    key_visible = tuple(visible) if visible is not None else None
    key_allowed = tuple(sorted(allowed)) if allowed is not None else None
    result = _effective_tiles(tuple(counts), open_melds, key_visible,
                              allow_chiitoi, allow_kokushi, key_allowed)
    return dict(result)


@lru_cache(maxsize=50000)
def _effective_tiles(counts_key, open_melds, key_visible, allow_chiitoi,
                     allow_kokushi, key_allowed):
    counts = list(counts_key)
    visible = list(key_visible) if key_visible is not None else [0] * NUM_TILE_TYPES
    allowed = set(key_allowed) if key_allowed is not None else None
    return tuple(_effective_tiles_impl(counts, open_melds, visible,
                                       allow_chiitoi, allow_kokushi, allowed).items())


def _effective_tiles_impl(counts, open_melds, visible, allow_chiitoi,
                          allow_kokushi, allowed):
    """返回 {牌索引: 剩余张数}。

    counts     : 34 长度计数（暗牌）
    open_melds : 副露数量（只影响面子数，不参与本轮摸牌）
    visible    : 34 长度计数，手牌之外的已见牌（弃牌 / 副露 / 牌河）
    allowed    : 可选的可摸牌索引集合（例如四川定缺后排除缺门）
    """
    counts = list(counts)
    if visible is None:
        visible = [0] * NUM_TILE_TYPES

    base = shanten(counts, open_melds, allow_chiitoi, allow_kokushi)
    if base < 0:
        return {}          # 已经和牌，没有“有效牌”这回事
    result = {}
    for t in range(NUM_TILE_TYPES):
        if allowed is not None and t not in allowed:
            continue
        left = remaining_copies(counts, visible, t)
        if left <= 0:
            continue
        counts[t] += 1
        s = shanten(counts, open_melds, allow_chiitoi, allow_kokushi)
        counts[t] -= 1
        if s < base:
            result[t] = left
    return result


def ukeire_total(eff):
    return sum(eff.values())


def required_draws(counts, open_melds=0, allow_chiitoi=True, allow_kokushi=True):
    """还差几步向听（= 至少需要摸到几张有效牌）"""
    return max(0, shanten(counts, open_melds, allow_chiitoi, allow_kokushi))


# ---------------------------------------------------------------------------
#  14 张手牌的舍牌候选
# ---------------------------------------------------------------------------

def discard_options(counts14, open_melds=0, visible=None, allow_chiitoi=True,
                    allow_kokushi=True, allowed=None):
    """对每个可打出的牌，算出打出后的向听、进张。

    返回列表，元素形如::

        {"discard": 4, "shanten": 1, "ukeire": 36, "tiles": {2: 3, ...}}
    """
    counts14 = list(counts14)
    if visible is None:
        visible = [0] * NUM_TILE_TYPES

    options = []
    for t in range(NUM_TILE_TYPES):
        if counts14[t] == 0:
            continue
        counts14[t] -= 1
        if allowed is not None and t not in allowed:
            # 定缺牌必须打出，仍然列为候选
            s = shanten(counts14, open_melds, allow_chiitoi, allow_kokushi)
            options.append({
                "discard": t,
                "shanten": s,
                "ukeire": 0,
                "tiles": {},
                "forced": True,
            })
        else:
            s = shanten(counts14, open_melds, allow_chiitoi, allow_kokushi)
            eff = effective_tiles(counts14, open_melds, visible,
                                  allow_chiitoi, allow_kokushi, allowed)
            options.append({
                "discard": t,
                "shanten": s,
                "ukeire": ukeire_total(eff),
                "tiles": eff,
                "forced": False,
            })
        counts14[t] += 1

    options.sort(key=lambda o: (not o["forced"], o["shanten"], -o["ukeire"]))
    return options
