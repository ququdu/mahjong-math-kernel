# -*- coding: utf-8 -*-
"""牌表示 / 向听数 / 有效牌 / 和牌拆解 的回归测试。

向听数的正确性不靠"看起来对"，靠两条：

1. 与不剪枝的朴素 DFS 在大量随机手牌上逐一对齐；
2. 与"和牌判定"自洽（向听 -1 <=> 能和，向听 0 <=> 存在一张牌能和牌）。
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from mahjong_kernel import meld as meld_mod
from mahjong_kernel import shanten as shanten_mod
from mahjong_kernel import tiles as T
from mahjong_kernel.ukeire import effective_tiles, ukeire_total


# ---------------------------------------------------------------------------
#  工具
# ---------------------------------------------------------------------------

def random_counts(n, seed, kinds=34):
    rnd = random.Random(seed)
    pool = []
    for t in range(kinds):
        pool.extend([t] * 4)
    rnd.shuffle(pool)
    return T.to_counts(sorted(pool[:n]))


def naive_shanten(counts, open_melds=0):
    """不剪枝的参照实现，只用于对照。"""
    best = [100]
    c = list(counts)

    def dfs(i, m, t, p):
        while i < 34 and c[i] == 0:
            i += 1
        if i >= 34:
            mm = m + open_melds
            avail = max(0, 4 - mm)
            v = 8 - 2 * mm - min(t, avail) - p
            if v < best[0]:
                best[0] = v
            return
        if c[i] >= 3:
            c[i] -= 3
            dfs(i, m + 1, t, p)
            c[i] += 3
        if i < 27 and i % 9 <= 6 and c[i + 1] and c[i + 2]:
            c[i] -= 1; c[i + 1] -= 1; c[i + 2] -= 1
            dfs(i, m + 1, t, p)
            c[i] += 1; c[i + 1] += 1; c[i + 2] += 1
        if c[i] >= 2:
            if not p:
                c[i] -= 2
                dfs(i, m, t, 1)
                c[i] += 2
            c[i] -= 2
            dfs(i, m, t + 1, p)
            c[i] += 2
        if i < 27 and i % 9 <= 7 and c[i + 1]:
            c[i] -= 1; c[i + 1] -= 1
            dfs(i, m, t + 1, p)
            c[i] += 1; c[i + 1] += 1
        if i < 27 and i % 9 <= 6 and c[i + 2]:
            c[i] -= 1; c[i + 2] -= 1
            dfs(i, m, t + 1, p)
            c[i] += 1; c[i + 2] += 1
        saved = c[i]
        c[i] = 0
        dfs(i + 1, m, t, p)
        c[i] = saved

    dfs(0, 0, 0, 0)
    return best[0]


def is_win(counts):
    if sum(counts) != 14:
        return False
    if meld_mod.is_chiitoi(counts) or meld_mod.is_kokushi(counts):
        return True
    if meld_mod.is_seven_stars(counts):
        return True
    return bool(meld_mod.decompose_standard(counts, 4))


def H(s):
    """解析并断言手牌张数合法（13 或 14）。"""
    tiles = T.parse_tiles(s)
    assert len(tiles) in (13, 14), "%s -> %d 张" % (s, len(tiles))
    return T.to_counts(tiles)


# ---------------------------------------------------------------------------
#  解析
# ---------------------------------------------------------------------------

def test_parse_compact():
    assert T.parse_tiles("123m") == [0, 1, 2]
    assert T.parse_tiles("9s") == [26]
    assert T.parse_tiles("11z") == [27, 27]
    assert T.parse_tiles("7z") == [33]
    assert T.parse_tiles("123m456p789s11z") == [0, 1, 2, 12, 13, 14, 24, 25, 26, 27, 27]


def test_parse_chinese():
    assert T.parse_tiles("123万") == [0, 1, 2]
    assert T.parse_tiles("123筒") == [9, 10, 11]
    assert T.parse_tiles("123条") == [18, 19, 20]
    assert T.parse_tiles("东东中") == [27, 27, 33]
    assert T.parse_tiles("123万456筒789条东东中") == T.parse_tiles("123m456p789s11z7z")
    assert T.parse_tiles("红中发财白板") == [31, 32, 33]
    assert T.parse_tiles("一二三万") == [0, 1, 2]


def test_parse_rejects_bad_input():
    with pytest.raises(ValueError):
        T.parse_tiles("9z")
    with pytest.raises(ValueError):
        T.parse_tiles("123")          # 有数字没花色
    with pytest.raises(ValueError):
        T.parse_tiles("123mx")


def test_roundtrip_string():
    for s in ("123m456p789s11z", "1112345678999m", "19m19p19s1234567z"):
        counts = T.to_counts(T.parse_tiles(s))
        assert T.to_counts(T.parse_tiles(T.counts_to_str(counts))) == counts


def test_tile_classification():
    assert T.is_honor(27) and not T.is_honor(26)
    assert T.is_terminal(0) and T.is_terminal(8) and not T.is_terminal(1)
    assert T.is_yaochu(27) and T.is_yaochu(0) and not T.is_yaochu(4)
    assert T.suit_of(18) == 2 and T.suit_of(33) == 3
    assert T.rank_of(18) == 1 and T.rank_of(33) == 7


# ---------------------------------------------------------------------------
#  向听数：已知样例
# ---------------------------------------------------------------------------

KNOWN = [
    ("123m456p789s111z4z", 0),      # 4 面子 + 9z 单骑听
    ("123m456p789s11z23m", 0),      # 两面听 1m/4m
    ("123m456p789s11z2z3z", 1),     # 3 面子 + 雀头 + 两张散牌
    ("19m19p19s1234567z", 0),       # 十三面听
    ("19m19p19s12345677z", -1),     # 十三幺和牌
    ("1122334455667m", 0),          # 七对 / 标准两听
    ("11223344556677m", -1),        # 七对和牌
    ("1112345678999m", 0),          # 九莲宝灯形，听牌
    ("11122233344455m", -1),        # 四暗刻单骑形
]


@pytest.mark.parametrize("hand,expected", KNOWN)
def test_known_shanten(hand, expected):
    counts = H(hand)
    assert shanten_mod.shanten(counts) == expected


def test_naive_examples():
    """四张相同算两对（国标七对允许）"""
    assert meld_mod.is_chiitoi(T.to_counts(T.parse_tiles("11223344556677m")))
    assert meld_mod.is_chiitoi(T.to_counts(T.parse_tiles("1111222233334m"))) is False


# ---------------------------------------------------------------------------
#  向听数：与朴素实现对比
# ---------------------------------------------------------------------------

def test_shanten_matches_naive_random():
    for seed in range(120):
        counts = random_counts(13, seed)
        assert shanten_mod.shanten_standard(counts) == naive_shanten(counts)
    for seed in range(60):
        counts = random_counts(14, seed + 1000)
        assert shanten_mod.shanten_standard(counts) == naive_shanten(counts)
    for open_melds in (1, 2, 3):
        for seed in range(40):
            counts = random_counts(13 - 3 * open_melds, seed + open_melds * 31)
            assert (shanten_mod.shanten_standard(counts, open_melds)
                    == naive_shanten(counts, open_melds))


def test_shanten_tenpai_consistency():
    """向听 0 <=> 存在一张牌能让手牌和牌。"""
    for seed in range(120):
        counts = random_counts(13, seed + 5000)
        s = shanten_mod.shanten(counts)
        completes = any(
            is_win([c + (1 if i == t else 0) for i, c in enumerate(counts)])
            for t in range(34) if counts[t] < 4
        )
        assert (s == 0) == completes, T.counts_to_str(counts)


def test_shanten_agari_consistency():
    """向听 -1 <=> 手牌真的是和牌形。"""
    rnd = random.Random(7)
    for _ in range(3000):
        counts = random_counts(14, rnd.randrange(10 ** 6))
        assert (shanten_mod.shanten(counts) < 0) == is_win(counts), T.counts_to_str(counts)


def test_chiitoi_and_kokushi_formula():
    assert shanten_mod.shanten_chiitoi(T.to_counts(T.parse_tiles("1122334455667m"))) == 0
    assert shanten_mod.shanten_chiitoi(T.to_counts(T.parse_tiles("11223344556677m"))) == -1
    assert shanten_mod.shanten_kokushi(T.to_counts(T.parse_tiles("19m19p19s1234567z"))) == 0
    assert shanten_mod.shanten_kokushi(T.to_counts(T.parse_tiles("19m19p19s12345677z"))) == -1


def test_open_hand_ignores_special_shapes():
    counts = T.to_counts(T.parse_tiles("1122334455m"))
    # 有副露时七对已不可能，向听不应小于标准型
    assert shanten_mod.shanten(counts, open_melds=1) == shanten_mod.shanten_standard(counts, 1)


# ---------------------------------------------------------------------------
#  有效牌
# ---------------------------------------------------------------------------

def test_effective_tiles_tanki():
    counts = H("123m456p789s111z4z")      # 单骑听 9z
    eff = effective_tiles(counts)
    assert set(eff) == {T.parse_tiles("4z")[0]}
    assert ukeire_total(eff) == 3         # 自己手里 1 张，剩 3 张


def test_effective_tiles_visible_deduction():
    counts = H("123m456p789s111z4z")
    visible = T.to_counts(T.parse_tiles("4z"))   # 已经打出去一张 9z
    eff = effective_tiles(counts, visible=visible)
    assert ukeire_total(eff) == 2


def test_effective_tiles_ryammen():
    counts = H("123m456p789s11z23m")
    eff = effective_tiles(counts)
    assert set(eff) == {T.parse_tiles("1m")[0], T.parse_tiles("4m")[0]}
    # 手里 1m 1 张、4m 0 张 -> 3 + 4 = 7
    assert ukeire_total(eff) == 7


def test_effective_tiles_none_when_agari():
    counts = H("123m456p789s111z44z")
    assert shanten_mod.shanten(counts) == -1
    assert effective_tiles(counts) == {}


def test_effective_tiles_open_hand():
    # 碰了 111z，剩下 123m456p789s2z 形
    counts = T.to_counts(T.parse_tiles("123m456p789s2z"))
    eff = effective_tiles(counts, open_melds=1)
    assert set(eff) == {T.parse_tiles("2z")[0]}


# ---------------------------------------------------------------------------
#  和牌拆解
# ---------------------------------------------------------------------------

def test_decompose_all():
    counts = T.to_counts(T.parse_tiles("11122233344455m"))
    assert len(meld_mod.decompose_standard(counts, 4)) >= 1


def test_decompose_counts_are_complete():
    counts = T.to_counts(T.parse_tiles("123m123p123s111z22z"))
    decs = meld_mod.decompose_standard(counts, 4)
    assert decs
    for d in decs:
        assert len(d.melds) == 4
        used = T.to_counts([])
        for kind, tile in d.melds:
            if kind == meld_mod.SEQUENCE:
                for k in range(3):
                    used[tile + k] += 1
            else:
                used[tile] += 3
        used[d.pair] += 2
        assert used == counts


def test_special_shapes():
    assert meld_mod.is_kokushi(T.to_counts(T.parse_tiles("19m19p19s12345677z")))
    assert not meld_mod.is_kokushi(T.to_counts(T.parse_tiles("19m19p19s1234567z2m")))
    assert meld_mod.is_chiitoi(T.to_counts(T.parse_tiles("11223344556677m")))
