# -*- coding: utf-8 -*-
"""广东推倒和（鸡胡）—— 最宽松的玩法：任何和牌形都能和。

规则要点
--------
* 136 张（含字牌），可吃可碰可杠。
* 推倒和：没有番缚，能凑成 4 面子 + 1 雀头就能和。
* 番数按 ``2^番`` 折算分数（分值为倍数，底分为 1）。

番种口径取最常见的"广东推倒和 / 鸡胡"一套。
"""

from __future__ import annotations

from ..meld import Decomposition, is_chiitoi, is_kokushi, normalize_kind
from ..tiles import HAKU, HATSU, CHUN, EAST, SOUTH, WEST, NORTH, Z_START, is_yaochu
from .base import FanSet, RuleSet, ScoreContext, groups_of, all_tiles_of

GUANGDONG_FANS = {
    "鸡胡": 0,
    "平胡": 1,
    "碰碰胡": 3,
    "混一色": 3,
    "清一色": 5,
    "七对": 5,
    "豪华七对": 7,
    "混幺九": 6,
    "字一色": 10,
    "小三元": 6,
    "大三元": 10,
    "小四喜": 10,
    "大四喜": 13,
    "四暗刻": 10,
    "十三幺": 13,
    "清幺九": 13,
    "自摸": 1,
    "杠上开花": 1,
    "抢杠和": 1,
    "海底捞月": 1,
    "花牌": 1,
}

EXCLUSIONS = {
    "清一色": ["混一色", "混幺九"],
    "大三元": ["小三元"],
    "大四喜": ["小四喜"],
    "字一色": ["混幺九"],
    "清幺九": ["混幺九"],
    "豪华七对": ["七对"],
    "四暗刻": ["碰碰胡"],
    "字一色": ["碰碰胡", "混幺九"],
    "清幺九": ["碰碰胡"],
    "十三幺": ["混幺九"],
}


class GuangdongRuleSet(RuleSet):
    key = "guangdong"
    name = "广东推倒和"
    description = "144 张（含 8 张花牌）/ 推倒和（无番缚）/ 番数按 2^番 折算"
    min_fan = 0
    base_points = 1
    dealer_multiplier = 1.0
    allow_chi = True
    allow_peng = True
    allow_gang = True
    has_honors = True
    has_flowers = True
    max_points = 1024
    default_win_points = 4
    default_deal_points = 4

    def fan_to_points(self, fan):
        return min(self.max_points, max(1, 2 ** max(0, fan)))

    def build_payments(self, points, ctx):
        if ctx.is_tsumo:
            return {"each": points, "total": points * 3}
        return {"discarder": points, "total": points}

    # -- 特殊和牌形 ------------------------------------------------------

    def detect_special(self, ctx: ScoreContext):
        out = []
        counts = ctx.counts
        if ctx.melds:
            return out

        if is_kokushi(counts):
            fs = FanSet()
            fs.add("十三幺", 13)
            out.append(("十三幺", fs.items()))
            return out

        if is_chiitoi(counts):
            fs = FanSet()
            quartets = sum(1 for c in counts if c == 4)
            if quartets:
                fs.add("豪华七对", 7)
            else:
                fs.add("七对", 5)
            suits = {i // 9 for i, c in enumerate(counts) if c and i < Z_START}
            honor = any(counts[i] for i in range(Z_START, 34))
            if len(suits) == 1 and not honor:
                fs.add("清一色", 5)
            elif len(suits) == 1 and honor:
                fs.add("混一色", 3)
            if ctx.is_tsumo:
                fs.add("自摸", 1)
            out.append(("七对", fs.items()))
        return out

    # -- 主检测 ----------------------------------------------------------

    def detect_fans(self, ctx: ScoreContext, dec: Decomposition):
        fs = FanSet()
        seqs, trips = groups_of(dec)
        tiles = all_tiles_of(dec)
        pair = dec.pair
        win = ctx.win_tile
        all_trip = len(trips) == 4
        honor = any(t >= Z_START for t in tiles)
        suits = {t // 9 for t in tiles if t < Z_START}

        dragon_trips = {t for t in trips if t >= HAKU}
        wind_trips = {t for t in trips if EAST <= t <= NORTH}

        if all_trip and all(is_yaochu(t) for t in tiles):
            if honor:
                fs.add("混幺九", 6)
            else:
                fs.add("清幺九", 13)
        if all(t >= Z_START for t in tiles):
            fs.add("字一色", 10)
        if len(dragon_trips) == 3:
            fs.add("大三元", 10)
        elif len(dragon_trips) == 2 and pair >= HAKU:
            fs.add("小三元", 6)
        if len(wind_trips) == 4:
            fs.add("大四喜", 13)
        elif len(wind_trips) == 3 and EAST <= pair <= NORTH:
            fs.add("小四喜", 10)
        if all_trip:
            fs.add("碰碰胡", 3)
        if len(suits) == 1 and not honor:
            fs.add("清一色", 5)
        elif len(suits) == 1 and honor:
            fs.add("混一色", 3)
        if len(seqs) == 4:
            fs.add("平胡", 1)
        if not fs.has("碰碰胡") and not fs.has("清一色") and not fs.has("混一色") \
                and not fs.has("混幺九") and not fs.has("清幺九") and not fs.has("字一色"):
            fs.add("鸡胡", 0)

        # 四暗刻（抢和完成的刻子算明刻）
        concealed = [t for k, t in dec.melds if normalize_kind(k) == "t"]
        for m in ctx.melds:
            if m.kind == "ankan":
                concealed.append(m.tile)
        if not ctx.is_tsumo and win in concealed:
            concealed.remove(win)
        if len(concealed) >= 4:
            fs.add("四暗刻", 10)

        if ctx.is_tsumo:
            fs.add("自摸", 1)
        if ctx.is_after_kan and ctx.is_tsumo:
            fs.add("杠上开花", 1)
        if ctx.is_chankan:
            fs.add("抢杠和", 1)
        if ctx.is_last_tile:
            fs.add("海底捞月", 1)
        return fs.items()

    def resolve_exclusions(self, items, ctx: ScoreContext):
        present = {i.name for i in items}
        drop = set()
        for name in present:
            drop |= set(EXCLUSIONS.get(name, ()))
        kept = [i for i in items if i.name not in drop]
        return kept or [i for i in items if i.name == "鸡胡"] or items
