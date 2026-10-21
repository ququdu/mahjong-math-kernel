# -*- coding: utf-8 -*-
"""自定义规则（JSON 声明式）。

不想写 Python 也能加一套地方规则：把番种写成"条件 -> 番数"的声明即可。
条件词表见 ``PREDICATES``，键值全部是"必须成立"的与关系；值写 ``false``
表示"必须不成立"。

示例
----
::

    {
      "key": "my_local",
      "name": "我的地方规则",
      "min_fan": 1,
      "base_points": 1,
      "has_honors": true,
      "allow_chi": true,
      "fans": [
        {"name": "碰碰胡", "fan": 2, "when": {"all_triplets": true}},
        {"name": "清一色", "fan": 4, "when": {"pure_suit": true}},
        {"name": "自摸",   "fan": 1, "when": {"tsumo": true}},
        {"name": "边张",   "fan": 1, "when": {"wait_in": ["边张"]}}
      ],
      "exclusions": {"清一色": ["混一色"]}
    }
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ..meld import Decomposition, is_chiitoi, is_kokushi, normalize_kind
from ..tiles import HAKU, EAST, Z_START, is_yaochu
from .base import FanItem, FanSet, RuleSet, ScoreContext, all_tiles_of, groups_of


def _ranks(tiles):
    return [t % 9 + 1 for t in tiles if t < Z_START]


# ---------------------------------------------------------------------------
#  条件词表
# ---------------------------------------------------------------------------

def _concealed_triplets(ctx, dec, win):
    out = [t for k, t in dec.melds if normalize_kind(k) == "t"]
    for m in ctx.melds:
        if m.kind == "ankan":
            out.append(m.tile)
    if not ctx.is_tsumo and win in out:
        out.remove(win)
    return out


def _pred_all_triplets(ctx, dec, opts):
    return len(groups_of(dec)[1]) == 4


def _pred_all_sequences(ctx, dec, opts):
    return len(groups_of(dec)[0]) == 4


def _pred_pure_suit(ctx, dec, opts):
    tiles = all_tiles_of(dec)
    suits = {t // 9 for t in tiles if t < Z_START}
    return len(suits) == 1 and not any(t >= Z_START for t in tiles)


def _pred_half_flush(ctx, dec, opts):
    tiles = all_tiles_of(dec)
    suits = {t // 9 for t in tiles if t < Z_START}
    return len(suits) == 1 and any(t >= Z_START for t in tiles)


def _pred_all_honors(ctx, dec, opts):
    return all(t >= Z_START for t in all_tiles_of(dec))


def _pred_no_honors(ctx, dec, opts):
    return not any(t >= Z_START for t in all_tiles_of(dec))


def _pred_no_terminals(ctx, dec, opts):
    return not any(is_yaochu(t) for t in all_tiles_of(dec))


def _pred_all_yaochu(ctx, dec, opts):
    return all(is_yaochu(t) for t in all_tiles_of(dec))


def _pred_min_rank_ge(ctx, dec, opts):
    r = _ranks(all_tiles_of(dec))
    return bool(r) and min(r) >= int(opts)


def _pred_max_rank_le(ctx, dec, opts):
    r = _ranks(all_tiles_of(dec))
    return bool(r) and max(r) <= int(opts)


def _pred_suit_count_eq(ctx, dec, opts):
    suits = {t // 9 for t in all_tiles_of(dec) if t < Z_START}
    return len(suits) == int(opts)


def _pred_dragon_triplets_ge(ctx, dec, opts):
    trips = groups_of(dec)[1]
    return sum(1 for t in trips if t >= HAKU) >= int(opts)


def _pred_wind_triplets_ge(ctx, dec, opts):
    trips = groups_of(dec)[1]
    return sum(1 for t in trips if EAST <= t <= EAST + 3) >= int(opts)


def _pred_concealed_triplets_ge(ctx, dec, opts):
    return len(_concealed_triplets(ctx, dec, ctx.win_tile)) >= int(opts)


def _pred_kan_count_ge(ctx, dec, opts):
    return sum(1 for m in ctx.melds if m.is_kan) >= int(opts)


def _pred_pair_in(ctx, dec, opts):
    return dec.pair < Z_START and dec.pair % 9 + 1 in [int(x) for x in opts]


def _pred_pair_is_dragon(ctx, dec, opts):
    return dec.pair >= HAKU


def _pred_wait_in(ctx, dec, opts):
    ws = getattr(ctx, "_waits", None)
    if ws is None:
        ws = _wait_options(ctx, dec)
        ctx._waits = ws
    return bool(set(ws) & set(opts))


def _wait_options(ctx, dec):
    w = ctx.win_tile
    out = set()
    if w < 0:
        return {"unknown"}
    if dec.pair == w:
        out.add("单钓")
    for k, t in dec.melds:
        if normalize_kind(k) != "s":
            continue
        if t <= w <= t + 2:
            pos = t % 9
            if w == t:
                out.add("边张" if pos == 6 else "两面")
            elif w == t + 1:
                out.add("坎张")
            else:
                out.add("边张" if pos == 0 else "两面")
    return out or {"unknown"}


def _flag(name):
    return lambda ctx, dec, opts: bool(getattr(ctx, name, False))


def _flag_ron(ctx, dec, opts):
    return not ctx.is_tsumo


PREDICATES = {
    "all_triplets": _pred_all_triplets,
    "all_sequences": _pred_all_sequences,
    "pure_suit": _pred_pure_suit,
    "half_flush": _pred_half_flush,
    "all_honors": _pred_all_honors,
    "no_honors": _pred_no_honors,
    "no_terminals": _pred_no_terminals,
    "all_yaochu": _pred_all_yaochu,
    "min_rank_ge": _pred_min_rank_ge,
    "max_rank_le": _pred_max_rank_le,
    "suit_count_eq": _pred_suit_count_eq,
    "dragon_triplets_ge": _pred_dragon_triplets_ge,
    "wind_triplets_ge": _pred_wind_triplets_ge,
    "concealed_triplets_ge": _pred_concealed_triplets_ge,
    "kan_count_ge": _pred_kan_count_ge,
    "pair_in": _pred_pair_in,
    "pair_is_dragon": _pred_pair_is_dragon,
    "wait_in": _pred_wait_in,
    "tsumo": _flag("is_tsumo"),
    "menzen": lambda ctx, dec, opts: ctx.menzen,
    "ron": _flag_ron,
    "after_kan": _flag("is_after_kan"),
    "last_tile": _flag("is_last_tile"),
    "chankan": _flag("is_chankan"),
}

# 带参数的条件：配置里的值就是参数本身
PARAM_PREDICATES = frozenset([
    "min_rank_ge", "max_rank_le", "suit_count_eq",
    "dragon_triplets_ge", "wind_triplets_ge", "concealed_triplets_ge",
    "kan_count_ge", "pair_in", "wait_in",
])


class CustomRuleSet(RuleSet):
    key = "custom"
    name = "自定义规则"

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.key = str(self.config.get("key") or "custom")
        self.name = str(self.config.get("name") or self.key)
        self.description = str(self.config.get("description") or "自定义规则")
        self.min_fan = int(self.config.get("min_fan", 0))
        self.base_points = int(self.config.get("base_points", 1))
        self.dealer_multiplier = float(self.config.get("dealer_multiplier", 1.0))
        self.allow_chi = bool(self.config.get("allow_chi", True))
        self.allow_peng = bool(self.config.get("allow_peng", True))
        self.allow_gang = bool(self.config.get("allow_gang", True))
        self.has_honors = bool(self.config.get("has_honors", True))
        self.has_flowers = bool(self.config.get("has_flowers", False))
        self.fan_mode = str(self.config.get("fan_mode", "exponential"))
        self.max_points = int(self.config.get("max_points", 1024))
        self._fans = list(self.config.get("fans") or [])
        self._exclusions = dict(self.config.get("exclusions") or {})
        self._special = list(self.config.get("special_shapes") or [])
        self._validate_config()

    def _validate_config(self):
        for spec in self._fans:
            if "name" not in spec or "fan" not in spec:
                raise ValueError("自定义番种必须包含 name 和 fan: %r" % (spec,))
            for pred in (spec.get("when") or {}):
                if pred not in PREDICATES:
                    raise ValueError(
                        "未知条件 %r，可用：%s" % (pred, ", ".join(sorted(PREDICATES)))
                    )

    # -- 算分 -----------------------------------------------------------

    def fan_to_points(self, fan):
        if self.fan_mode == "linear":
            return max(1, self.base_points * fan)
        return min(self.max_points, max(1, 2 ** max(0, fan)))

    def build_payments(self, points, ctx):
        if ctx.is_tsumo:
            return {"each": points, "total": points * 3}
        return {"discarder": points, "total": points}

    # -- 检测 -----------------------------------------------------------

    def detect_special(self, ctx: ScoreContext):
        out = []
        counts = ctx.counts
        if not ctx.melds:
            for spec in self._special:
                shape = spec.get("shape")
                ok = False
                if shape == "chiitoi":
                    ok = is_chiitoi(counts)
                elif shape == "kokushi":
                    ok = is_kokushi(counts)
                if ok:
                    fs = FanSet()
                    for item in spec.get("fans") or []:
                        fs.add(item["name"], int(item["fan"]))
                    out.append((shape, fs.items()))
        return out

    def detect_fans(self, ctx: ScoreContext, dec: Decomposition):
        fs = FanSet()
        for spec in self._fans:
            when = spec.get("when") or {}
            ok = True
            for pred, expect in when.items():
                fn = PREDICATES[pred]
                if pred in PARAM_PREDICATES:
                    if not fn(ctx, dec, expect):
                        ok = False
                        break
                else:
                    if bool(fn(ctx, dec, None)) != bool(expect):
                        ok = False
                        break
            if ok:
                fs.add(spec["name"], int(spec["fan"]), spec.get("detail", ""))
        return fs.items()

    def resolve_exclusions(self, items, ctx: ScoreContext):
        present = {i.name for i in items}
        drop = set()
        for name in present:
            drop |= set(self._exclusions.get(name, ()))
        return [i for i in items if i.name not in drop]

    def to_dict(self):
        d = RuleSet.to_dict(self)
        d["custom"] = True
        return d


def from_json(text_or_path):
    """从 dict / JSON 文本 / 文件路径构造自定义规则。"""
    import os

    if isinstance(text_or_path, dict):
        return CustomRuleSet(text_or_path)
    if os.path.exists(text_or_path):
        with open(text_or_path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
    else:
        config = json.loads(text_or_path)
    return CustomRuleSet(config)
