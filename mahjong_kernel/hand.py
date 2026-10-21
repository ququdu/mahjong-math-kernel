# -*- coding: utf-8 -*-
"""局面状态：手牌 + 副露 + 场况。

对外接口（HTTP / CLI / 截图识别）都先归一化成 BoardState，再交给引擎。
这样核心计算与输入方式解耦：键盘输入的、截图识别出来的、别家程序发来的，
最终都是同一个对象。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .meld import Meld, parse_meld
from .tiles import (
    EAST,
    NUM_TILE_TYPES,
    from_counts,
    parse_tiles,
    to_counts,
    counts_to_str,
)

WIND_NAMES = {"east": EAST, "e": EAST, "东": EAST,
              "south": EAST + 1, "s": EAST + 1, "南": EAST + 1,
              "west": EAST + 2, "w": EAST + 2, "西": EAST + 2,
              "north": EAST + 3, "n": EAST + 3, "北": EAST + 3}

SUIT_NAMES = {"m": 0, "万": 0, "w": 0,
              "p": 1, "筒": 1, "饼": 1,
              "s": 2, "条": 2, "t": 2,
              "z": 3, "字": 3}


def parse_wind(v):
    if v is None:
        return None
    if isinstance(v, int):
        return v
    key = str(v).strip().lower()
    if key in WIND_NAMES:
        return WIND_NAMES[key]
    if key.isdigit():
        n = int(key)
        if 1 <= n <= 4:
            return EAST + n - 1
    raise ValueError("无法识别的风位: %r" % (v,))


def parse_suit(v):
    if v is None:
        return None
    if isinstance(v, int):
        return v
    key = str(v).strip().lower()
    if key in SUIT_NAMES:
        return SUIT_NAMES[key]
    raise ValueError("无法识别的花色: %r" % (v,))


@dataclass
class BoardState:
    """一个完整可算的局面。"""

    tiles: List[int] = field(default_factory=list)   # 自己暗牌（不含副露）
    melds: List[Meld] = field(default_factory=list)
    flowers: int = 0
    ruleset: str = "gb"

    # 场况
    seat_wind: int = EAST
    round_wind: int = EAST
    is_dealer: bool = True
    turn: int = 1
    wall_remaining: Optional[int] = None

    # 信息
    self_discards: List[int] = field(default_factory=list)
    visible: List[int] = field(default_factory=lambda: [0] * NUM_TILE_TYPES)
    dora_indicators: List[int] = field(default_factory=list)
    deficiency_suit: Optional[int] = None

    # 和牌判定
    agari_tile: Optional[int] = None
    is_tsumo: bool = False

    # 偶然役标记（海底 / 杠上开花 / 抢杠 ...）
    flags: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self):
        self.tiles = sorted(int(t) for t in self.tiles)
        self.visible = list(self.visible)[:] if self.visible else [0] * NUM_TILE_TYPES
        if len(self.visible) != NUM_TILE_TYPES:
            filled = [0] * NUM_TILE_TYPES
            for i, c in enumerate(self.visible[:NUM_TILE_TYPES]):
                filled[i] = c
            self.visible = filled

    # -- 派生量 ---------------------------------------------------------

    @property
    def counts(self):
        return to_counts(self.tiles)

    @property
    def open_meld_count(self):
        return len(self.melds)

    @property
    def hand_size(self):
        """暗牌张数（不含副露）"""
        return len(self.tiles)

    @property
    def total_size(self):
        return len(self.tiles) + 3 * len(self.melds)

    @property
    def is_full_hand(self):
        """能否构成和牌形（3n+2）"""
        return self.total_size % 3 == 2

    def seen_counts(self):
        """自己视角的"已经见过的牌"：手牌 + 副露 + 河 + 外部可见。"""
        seen = list(self.visible)
        for t in self.tiles:
            seen[t] += 1
        for m in self.melds:
            for t in m.tiles():
                seen[t] += 1
        for t in self.self_discards:
            seen[t] += 1
        for t in self.dora_indicators:
            seen[t] += 1
        return seen

    def visible_counts(self):
        """手牌之外已经看到的牌（用于扣张）。不重复统计手牌。"""
        seen = list(self.visible)
        for m in self.melds:
            for t in m.tiles():
                seen[t] += 1
        for t in self.self_discards:
            seen[t] += 1
        return seen

    def wall_size(self, default_from_turn=True):
        if self.wall_remaining is not None:
            return max(0, int(self.wall_remaining))
        # 136 张 - 开局发出的 53 张（庄家 14）- 每巡 4 张
        if default_from_turn:
            return max(0, 136 - 53 - 4 * (self.turn - 1))
        return 0

    def hand_str(self):
        return counts_to_str(self.counts)

    def to_dict(self):
        return {
            "ruleset": self.ruleset,
            "hand": self.hand_str(),
            "tiles": list(self.tiles),
            "melds": [m.to_dict() for m in self.melds],
            "flowers": self.flowers,
            "seat_wind": self.seat_wind,
            "round_wind": self.round_wind,
            "is_dealer": self.is_dealer,
            "turn": self.turn,
            "wall_remaining": self.wall_remaining,
            "self_discards": list(self.self_discards),
            "visible": list(self.visible),
            "dora_indicators": list(self.dora_indicators),
            "deficiency_suit": self.deficiency_suit,
            "agari_tile": self.agari_tile,
            "is_tsumo": self.is_tsumo,
            "flags": dict(self.flags),
        }

    # -- 构造 -----------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Dict):
        if data is None:
            data = {}
        ruleset = data.get("ruleset") or "gb"

        raw_tiles = data.get("tiles")
        if raw_tiles is None:
            raw_tiles = data.get("hand") or ""
        if isinstance(raw_tiles, str):
            tiles = parse_tiles(raw_tiles)
        else:
            tiles = [int(t) for t in raw_tiles]

        melds = []
        for m in data.get("melds") or []:
            if isinstance(m, dict):
                melds.append(parse_meld(m.get("kind"), m.get("tile", 0)))
            elif isinstance(m, (list, tuple)):
                melds.append(parse_meld(m[0], m[1]))
            elif isinstance(m, Meld):
                melds.append(m)

        visible = data.get("visible")
        if isinstance(visible, str):
            visible_counts = to_counts(parse_tiles(visible))
        elif visible is None:
            visible_counts = [0] * NUM_TILE_TYPES
        else:
            visible_counts = list(visible)

        def as_tiles(v):
            if v is None:
                return []
            if isinstance(v, str):
                return parse_tiles(v)
            return [int(t) for t in v]

        dora = data.get("dora_indicators")
        agari = data.get("agari_tile")
        if isinstance(agari, str):
            agari_tiles = parse_tiles(agari)
            agari = agari_tiles[0] if agari_tiles else None

        return cls(
            tiles=tiles,
            melds=melds,
            flowers=int(data.get("flowers") or 0),
            ruleset=str(ruleset),
            seat_wind=parse_wind(data.get("seat_wind")) if data.get("seat_wind") is not None else EAST,
            round_wind=parse_wind(data.get("round_wind")) if data.get("round_wind") is not None else EAST,
            is_dealer=bool(data.get("is_dealer", True)),
            turn=int(data.get("turn") or 1),
            wall_remaining=(None if data.get("wall_remaining") is None
                            else int(data["wall_remaining"])),
            self_discards=as_tiles(data.get("self_discards")),
            visible=visible_counts,
            dora_indicators=as_tiles(dora),
            deficiency_suit=(parse_suit(data["deficiency_suit"])
                             if data.get("deficiency_suit") not in (None, "") else None),
            agari_tile=agari,
            is_tsumo=bool(data.get("is_tsumo", False)),
            flags=dict(data.get("flags") or {}),
        )
