# -*- coding: utf-8 -*-
"""牌表示与解析。

34 种牌统一用整数 0..33 表示：

    0..8    一万..九万      (m)
    9..17   一筒..九筒      (p)
    18..26  一条..九条      (s)
    27..33  东 南 西 北 白 发 中   (z)

这套"34 索引"是全内核的公共语言：向听、进张、番种、概率、识别都用它。
输入层允许玩家写 ``123m456p789s11z``、``123万456筒789条东东中``、
``1m 2m 3m``、``一二三万``，解析后一律转成索引列表。
"""

from __future__ import annotations

NUM_TILE_TYPES = 34

M_START, P_START, S_START, Z_START = 0, 9, 18, 27

# 风牌
EAST, SOUTH, WEST, NORTH = 27, 28, 29, 30
# 箭牌（白 发 中）
HAKU, HATSU, CHUN = 31, 32, 33

HONOR_INDICES = tuple(range(Z_START, NUM_TILE_TYPES))
WIND_INDICES = (EAST, SOUTH, WEST, NORTH)
DRAGON_INDICES = (HAKU, HATSU, CHUN)
TERMINAL_INDICES = (0, 8, 9, 17, 18, 26)
YAOCHU_INDICES = TERMINAL_INDICES + HONOR_INDICES

HONORS = frozenset(HONOR_INDICES)
WINDS = frozenset(WIND_INDICES)
DRAGONS = frozenset(DRAGON_INDICES)
TERMINALS = frozenset(TERMINAL_INDICES)
YAOCHU = frozenset(YAOCHU_INDICES)
# 老头牌（数牌 1/9），不含字牌
SUIT_TERMINALS = frozenset(TERMINAL_INDICES)

TILE_NAMES = tuple(
    [str(n) + "m" for n in range(1, 10)]
    + [str(n) + "p" for n in range(1, 10)]
    + [str(n) + "s" for n in range(1, 10)]
    + ["东", "南", "西", "北", "白", "发", "中"]
)

TILE_NAMES_CN = tuple(
    [n + "万" for n in "一二三四五六七八九"]
    + [n + "筒" for n in "一二三四五六七八九"]
    + [n + "条" for n in "一二三四五六七八九"]
    + ["东", "南", "西", "北", "白板", "发财", "红中"]
)

# 花牌不进 34 索引，单独计数（国标 144 张用）
FLOWER_NAMES = ("春", "夏", "秋", "冬", "梅", "兰", "竹", "菊")


def is_honor(tile):
    return tile >= Z_START


def is_wind(tile):
    return EAST <= tile <= NORTH


def is_dragon(tile):
    return tile >= HAKU


def is_terminal(tile):
    """数牌 1 / 9"""
    return tile < Z_START and (tile % 9 == 0 or tile % 9 == 8)


def is_yaochu(tile):
    """幺九牌：数牌 1/9 与全部字牌"""
    return tile >= Z_START or tile % 9 == 0 or tile % 9 == 8


def is_simple(tile):
    """中张：2..8 的数牌"""
    return tile < Z_START and 0 < tile % 9 < 8


def suit_of(tile):
    """0=万 1=筒 2=条 3=字"""
    return tile // 9 if tile < Z_START else 3


def rank_of(tile):
    """数牌 1..9，字牌 1..7"""
    return tile % 9 + 1 if tile < Z_START else tile - Z_START + 1


def tile_from(suit, rank):
    """(suit 0..3, rank 1..) -> 索引"""
    if suit == 3:
        return Z_START + rank - 1
    return suit * 9 + rank - 1


def dora_next(tile):
    """宝牌指示牌 -> 实际宝牌（日麻用；国标/血战不用，但保留给花牌与百搭扩展）"""
    if tile >= Z_START:
        if tile <= NORTH:
            return EAST + (tile - EAST + 1) % 4
        return HAKU + (tile - HAKU + 1) % 3
    base = (tile // 9) * 9
    return base + (tile % 9 + 1) % 9


def tile_name(tile):
    return TILE_NAMES[tile]


def tile_name_cn(tile):
    return TILE_NAMES_CN[tile]


# ---------------------------------------------------------------------------
#  解析
# ---------------------------------------------------------------------------

_FULLWIDTH = {ord(c): ord(c) - 0xFEE0 for c in "０１２３４５６７８９ｍｐｓｚ"}
_FULLWIDTH[ord("　")] = ord(" ")

_CN_DIGITS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
    "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5,
    "陆": 6, "柒": 7, "捌": 8, "玖": 9,
}

# 花色别名 -> suit 编号
_SUIT_CHARS = {"m": 0, "w": 0, "万": 0, "萬": 0,
               "p": 1, "t": 1, "b": 1, "筒": 1, "饼": 1, "餅": 1,
               "s": 2, "索": 2, "条": 2, "條": 2,
               "z": 3, "字": 3, "f": 3}

# 单独出现的字牌字符
_HONOR_CHARS = {"东": EAST, "東": EAST,
                "南": SOUTH,
                "西": WEST,
                "北": NORTH,
                "白": HAKU,
                "发": HATSU, "發": HATSU,
                "中": CHUN}

# 连写形式：红中 / 白板 / 发财 / 幺鸡(一条)
_HONOR_WORDS = {"红中": CHUN, "紅中": CHUN, "白板": HAKU, "发财": HATSU,
                "發財": HATSU, "幺鸡": 18, "幺雞": 18}


def parse_tiles(s):
    """把任意常见写法解析成牌索引列表（已排序）。

    >>> parse_tiles("123m456p789s11z")
    [0, 1, 2, 9, 10, 11, 19, 20, 21, 27, 27]
    >>> parse_tiles("123万456筒789条东东中")
    [0, 1, 2, 9, 10, 11, 18, 19, 20, 27, 27]
    """
    if not s:
        return []
    text = str(s).translate(_FULLWIDTH)

    tiles = []
    pending = []

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]

        # 三字词优先（红中/白板/发财）
        if i + 1 < n:
            two = text[i:i + 2]
            if two in _HONOR_WORDS:
                tiles.append(_HONOR_WORDS[two])
                pending = []
                i += 2
                continue

        if ch.isdigit():
            d = int(ch)
            if d < 1 or d > 9:
                raise ValueError("牌的序号必须是 1..9: %r" % ch)
            pending.append(d)
            i += 1
            continue

        if ch in _CN_DIGITS:
            pending.append(_CN_DIGITS[ch])
            i += 1
            continue

        if ch in _SUIT_CHARS:
            suit = _SUIT_CHARS[ch]
            if not pending:
                raise ValueError("花色前缺少数字: %r" % ch)
            for r in pending:
                if suit == 3 and r > 7:
                    raise ValueError("字牌只有 1z..7z（东南西北白发中），收到 %dz" % r)
                tiles.append(tile_from(suit, r))
            pending = []
            i += 1
            continue

        if ch in _HONOR_CHARS:
            # "东" 前面若挂着数字（如 "3z" 已处理），忽略
            tiles.append(_HONOR_CHARS[ch])
            pending = []
            i += 1
            continue

        if ch in " ,、/|[]()（）":
            i += 1
            continue

        raise ValueError("无法识别的字符 %r（输入: %r）" % (ch, s))

    if pending:
        raise ValueError("结尾有数字没有花色: %r" % s)

    return sorted(tiles)


def to_counts(tiles):
    """索引列表 -> 34 长度计数列表"""
    counts = [0] * NUM_TILE_TYPES
    for t in tiles:
        if not 0 <= t < NUM_TILE_TYPES:
            raise ValueError("牌索引越界: %r（合法 0..33）" % (t,))
        counts[t] += 1
    return counts


def from_counts(counts):
    """计数列表 -> 索引列表"""
    out = []
    for i, c in enumerate(counts):
        if c:
            out.extend([i] * c)
    return out


def counts_key(counts):
    """计数列表 -> 可哈希元组（缓存用）"""
    return tuple(counts)


def counts_to_str(counts):
    """计数列表 -> 紧凑串，如 '123m456p11z'"""
    parts = []
    for start, suit in ((0, "m"), (9, "p"), (18, "s")):
        digits = "".join(str(i - start + 1) * min(counts[i], 4)
                         for i in range(start, start + 9))
        if digits:
            parts.append(digits + suit)
    z = "".join(str(i - Z_START + 1) * counts[i] for i in range(Z_START, NUM_TILE_TYPES))
    if z:
        parts.append(z + "z")
    return "".join(parts) or "-"


def tiles_to_str(tiles):
    return counts_to_str(to_counts(tiles))


def tiles_to_cn(tiles):
    return " ".join(TILE_NAMES_CN[t] for t in sorted(tiles))


def validate_counts(counts, max_copies=4):
    """检查每张牌是否超过 max_copies，返回违规索引列表"""
    return [i for i, c in enumerate(counts) if c < 0 or c > max_copies]


def count_total(counts):
    return sum(counts)
