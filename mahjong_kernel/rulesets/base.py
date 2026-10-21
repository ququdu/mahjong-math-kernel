# -*- coding: utf-8 -*-
"""规则集抽象层。

一套麻将规则 = 牌池 + 允许的动作 + 番种表 + 起和条件 + 算分方式。
把这些抽出来，加新规则（长沙、武汉、上海……）就只是加一个 ``RuleSet`` 子类。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..meld import Decomposition, Meld, normalize_kind
from ..tiles import NUM_TILE_TYPES, Z_START


@dataclass(frozen=True)
class FanItem:
    """一个番种（或役种）。"""

    name: str
    fan: int
    detail: str = ""

    def to_dict(self):
        d = {"name": self.name, "fan": self.fan}
        if self.detail:
            d["detail"] = self.detail
        return d


@dataclass
class ScoreContext:
    """算分需要的全部输入。"""

    counts: List[int]                       # 14 张（含和牌张）
    melds: List[Meld] = field(default_factory=list)   # 副露
    win_tile: int = -1
    is_tsumo: bool = False
    seat_wind: int = 0
    round_wind: int = 0
    is_dealer: bool = True
    visible: Optional[List[int]] = None     # 全场已见（含自己手牌）
    flowers: int = 0

    # 偶然役标记
    is_last_tile: bool = False              # 最后一张牌（海底 / 妙手回春）
    is_after_kan: bool = False              # 杠上开花
    is_chankan: bool = False                # 抢杠和
    is_robbing_kan: bool = False
    deficiency_suit: Optional[int] = None   # 定缺花色

    # 由引擎填充
    decompositions: List[Decomposition] = field(default_factory=list)

    @property
    def menzen(self):
        """门清：没有明面副露（暗杠不算破门清）"""
        return all(m.is_concealed for m in self.melds)

    @property
    def open_meld_count(self):
        return len(self.melds)


@dataclass
class ScoreResult:
    ok: bool
    fan: int = 0
    points: int = 0
    fan_items: List[FanItem] = field(default_factory=list)
    payments: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    ruleset: str = ""
    best: Optional[Dict] = None

    def to_dict(self):
        return {
            "ok": self.ok,
            "ruleset": self.ruleset,
            "fan": self.fan,
            "points": self.points,
            "fan_items": [f.to_dict() for f in self.fan_items],
            "payments": self.payments,
            "notes": self.notes,
        }


class RuleSet:
    """规则集基类。"""

    key = "base"
    name = "通用"
    description = ""
    min_fan = 1
    base_points = 1
    dealer_multiplier = 1.0
    allow_chi = True
    allow_peng = True
    allow_gang = True
    has_honors = True
    has_flowers = False
    requires_deficiency = False
    max_copies = 4

    # 期望值模块用的典型分值（不是规则，只是"这个规则下一般一手牌值多少"）
    default_win_points = 8
    default_deal_points = 8

    @property
    def tiles(self):
        """可用牌索引集合"""
        if self.has_honors:
            return frozenset(range(NUM_TILE_TYPES))
        return frozenset(range(Z_START))

    @property
    def total_tiles(self):
        return 4 * len(self.tiles) + (8 if self.has_flowers else 0)

    # -- 番种 -----------------------------------------------------------

    def detect_fans(self, ctx: ScoreContext, dec: Decomposition):
        """返回某个拆解下的番种列表（未做不计处理）。"""
        raise NotImplementedError

    def resolve_exclusions(self, items, ctx: ScoreContext):
        """应用“不计”规则（番种不重复计算）。"""
        return list(items)

    def validate_win(self, ctx: ScoreContext):
        """和牌合法性约束（定缺、将牌限制等）。返回违规说明列表。"""
        return []

    # -- 算分 -----------------------------------------------------------

    def fan_to_points(self, fan: int) -> int:
        """番数 -> 和牌者总得分。"""
        return self.base_points * fan

    def build_payments(self, points: int, ctx: ScoreContext) -> Dict[str, int]:
        """得分 -> 各家的支付明细。"""
        if ctx.is_tsumo:
            each = max(1, int(round(points / 3.0)))
            return {"each": each, "total": each * 3}
        return {"discarder": points, "total": points}

    def detect_all(self, ctx: ScoreContext):
        """产出 (标签, 番种列表) 候选。特殊和牌形在子类里扩展。"""
        for dec in ctx.decompositions:
            yield ("standard", self.detect_fans(ctx, dec))
        for label, items in self.detect_special(ctx):
            yield (label, items)

    def detect_special(self, ctx: ScoreContext):
        """特殊和牌形（七对 / 十三幺 / 全不靠 ...）。返回 [(label, items), ...]"""
        return []

    def fallback_items(self, ctx: ScoreContext):
        """一个番种都没有时的兜底（国标是“无番和”，其它规则一般没有）。"""
        return []

    def score(self, ctx: ScoreContext) -> ScoreResult:
        from ..meld import decompose_with_melds

        ctx.decompositions = decompose_with_melds(ctx.counts, ctx.melds)

        violations = self.validate_win(ctx)
        if violations:
            return ScoreResult(ok=False, ruleset=self.key, notes=violations)

        candidates = list(self.detect_all(ctx))
        if not candidates:
            return ScoreResult(
                ok=False,
                ruleset=self.key,
                notes=["手牌不构成和牌形（无法拆成 4 面子 + 1 雀头）"],
            )

        best_items = None
        best_fan = -1
        best_label = ""
        best_dec = None

        for label, raw_items in candidates:
            items = self.resolve_exclusions(list(raw_items), ctx)
            if not items:
                items = list(self.fallback_items(ctx))
            fan = sum(i.fan for i in items)
            if ctx.flowers:
                items.append(FanItem("花牌", ctx.flowers, "%d 张花牌" % ctx.flowers))
                fan += ctx.flowers
            if fan > best_fan:
                best_fan = fan
                best_items = items
                best_label = label
                best_dec = ctx.decompositions[0] if label == "standard" and ctx.decompositions else None

        notes = []
        if best_fan < self.min_fan:
            notes.append("%d 番不足起和番 %d" % (best_fan, self.min_fan))
            return ScoreResult(
                ok=False, ruleset=self.key, fan=best_fan,
                fan_items=list(best_items or []), notes=notes,
            )

        points = self.fan_to_points(best_fan)
        payments = self.build_payments(points, ctx)
        return ScoreResult(
            ok=True,
            ruleset=self.key,
            fan=best_fan,
            points=points,
            fan_items=list(best_items),
            payments=payments,
            notes=notes,
            best={"shape": best_label, "decomposition": self._dec_dict(best_dec)},
        )

    def _dec_dict(self, dec):
        if dec is None:
            return None
        return {
            "melds": [{"kind": k, "tile": t} for k, t in dec.melds],
            "pair": dec.pair,
        }

    def to_dict(self):
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "min_fan": self.min_fan,
            "base_points": self.base_points,
            "allow_chi": self.allow_chi,
            "allow_peng": self.allow_peng,
            "allow_gang": self.allow_gang,
            "has_honors": self.has_honors,
            "has_flowers": self.has_flowers,
            "requires_deficiency": self.requires_deficiency,
            "tile_count": self.total_tiles,
        }


# ---------------------------------------------------------------------------
#  番种集合工具
# ---------------------------------------------------------------------------

class FanSet:
    """番种收集器：同名的只保留一个（取较大值），方便写检测逻辑。"""

    def __init__(self):
        self._items: Dict[str, FanItem] = {}

    def add(self, name, fan, detail=""):
        old = self._items.get(name)
        if old is None or fan > old.fan:
            self._items[name] = FanItem(name, fan, detail)
        return self

    def has(self, name):
        return name in self._items

    def drop(self, *names):
        for n in names:
            self._items.pop(n, None)
        return self

    def drop_if(self, name, cond):
        if cond:
            self._items.pop(name, None)
        return self

    def items(self):
        return sorted(self._items.values(), key=lambda i: (-i.fan, i.name))

    def total(self):
        return sum(i.fan for i in self._items.values())

    def names(self):
        return set(self._items)


def groups_of(dec: Decomposition):
    """拆解 -> (顺子起始牌列表, 刻子牌列表)，明暗不区分。"""
    seqs = [t for k, t in dec.melds if normalize_kind(k) == "s"]
    trips = [t for k, t in dec.melds if normalize_kind(k) == "t"]
    return seqs, trips


def concealed_groups_of(dec: Decomposition):
    """只取暗面子。"""
    seqs = [t for k, t in dec.melds if k == "s"]
    trips = [t for k, t in dec.melds if k == "t"]
    return seqs, trips


def all_tiles_of(dec: Decomposition):
    """拆解涉及的 14 张牌（杠按 3 张计结构）。"""
    out = []
    for k, t in dec.melds:
        if normalize_kind(k) == "s":
            out.extend((t, t + 1, t + 2))
        else:
            out.extend((t, t, t))
    out.extend((dec.pair, dec.pair))
    return out


def kind_is_open(kind):
    return kind.endswith("o")


def suit_of(tile):
    return tile // 9 if tile < Z_START else 3


def rank_of(tile):
    return tile % 9 + 1 if tile < Z_START else tile - Z_START + 1


def is_yaochu(tile):
    return tile >= Z_START or tile % 9 == 0 or tile % 9 == 8


def is_terminal(tile):
    return tile < Z_START and (tile % 9 == 0 or tile % 9 == 8)


def is_honor(tile):
    return tile >= Z_START
