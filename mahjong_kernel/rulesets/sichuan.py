# -*- coding: utf-8 -*-
"""四川血战到底（含常见地方变体）。

规则要点
--------
* 108 张：只有万 / 筒 / 条，没有字牌和花牌。
* **不能吃**，只能碰 / 杠。
* 必须**定缺**：选了哪一门，手里就不能留这门牌，留着也不能和。
* 血战到底：一家和牌后其余人继续打，直到三家和牌或摸完。
* 番数相加后按 ``2^番`` 折算分数（封顶可配）。

番种（常见口径）
----------------
平胡 1 / 碰碰胡 2 / 七对 4 / 龙七对 8 / 清一色 4 / 清对 8 / 将对 8 /
金钩钓 1 / 根 每根 1 / 自摸 1 / 杠上花 1 / 抢杠 1 / 海底捞月 1
"""

from __future__ import annotations

from ..meld import Decomposition, is_chiitoi, normalize_kind
from ..tiles import NUM_TILE_TYPES, Z_START, is_yaochu
from .base import FanItem, FanSet, RuleSet, ScoreContext, groups_of, all_tiles_of

SICHUAN_FANS = {
    "平胡": 1,
    "碰碰胡": 2,
    "七对": 4,
    "龙七对": 8,
    "清一色": 4,
    "清对": 8,
    "将对": 8,
    "金钩钓": 1,
    "幺九": 4,
    "根": 1,
    "自摸": 1,
    "杠上花": 1,
    "杠上炮": 1,
    "抢杠和": 1,
    "海底捞月": 1,
}


class SichuanRuleSet(RuleSet):
    key = "sichuan"
    name = "四川血战到底"
    description = "108 张 / 定缺 / 不能吃 / 血战到底 / 番数按 2^番 折算"
    min_fan = 1
    base_points = 1
    dealer_multiplier = 1.0
    allow_chi = False
    allow_peng = True
    allow_gang = True
    has_honors = False
    has_flowers = False
    requires_deficiency = True
    max_points = 1024          # 封顶倍数，可按桌规调
    default_win_points = 4     # 大约 2 番
    default_deal_points = 4

    def fan_to_points(self, fan):
        fan = max(1, fan)
        return min(self.max_points, 2 ** fan)

    def build_payments(self, points, ctx):
        if ctx.is_tsumo:
            return {"each": points, "total": points * 3}
        return {"discarder": points, "total": points}

    # -- 合法性 ---------------------------------------------------------

    def validate_win(self, ctx: ScoreContext):
        bad = []
        if ctx.deficiency_suit is not None:
            suit = ctx.deficiency_suit
            lo, hi = suit * 9, suit * 9 + 9
            if suit < 3 and any(ctx.counts[i] for i in range(lo, hi)):
                bad.append("手里还有定缺（%s）的牌，不能和" % "万筒条"[suit])
            for m in ctx.melds:
                if suit < 3 and lo <= m.tile < hi:
                    bad.append("副露里有定缺（%s）的牌，不能和" % "万筒条"[suit])
                    break
        if any(ctx.counts[i] for i in range(Z_START, NUM_TILE_TYPES)):
            bad.append("血战到底没有字牌")
        return bad

    # -- 番种 -----------------------------------------------------------

    def detect_special(self, ctx: ScoreContext):
        out = []
        counts = ctx.counts
        if ctx.melds:
            return out
        if not is_chiitoi(counts):
            return out

        fs = FanSet()
        quartets = sum(1 for c in counts if c == 4)
        if quartets:
            fs.add("龙七对", 8, "%d 个四张相同" % quartets)
        else:
            fs.add("七对", 4)
        if quartets:
            fs.add("根", quartets, "%d 根" % quartets)
        suits = {i // 9 for i, c in enumerate(counts) if c}
        if len(suits) == 1:
            fs.add("清一色", 4)
        if ctx.is_tsumo:
            fs.add("自摸", 1)
        out.append(("七对", fs.items()))
        return out

    def detect_fans(self, ctx: ScoreContext, dec: Decomposition):
        fs = FanSet()
        seqs, trips = groups_of(dec)
        tiles = all_tiles_of(dec)
        pair = dec.pair
        win = ctx.win_tile

        all_trip = len(trips) == 4
        suits = {t // 9 for t in tiles}
        pure = len(suits) == 1

        # 根：4 张相同（含杠）
        actual = list(ctx.counts)
        for m in ctx.melds:
            for t in m.tiles():
                actual[t] += 1
        roots = sum(1 for c in actual if c >= 4)

        if all_trip:
            if pure:
                fs.add("清对", 8)
            elif all(t < Z_START and t % 9 + 1 in (2, 5, 8) for t in tiles):
                fs.add("将对", 8)
            else:
                fs.add("碰碰胡", 2)
        elif pure:
            fs.add("清一色", 4)
        else:
            fs.add("平胡", 1)

        if all(is_yaochu(t) for t in tiles) and all_trip:
            fs.add("幺九", 4)
        if roots:
            fs.add("根", roots, "%d 根" % roots)
        if (len(ctx.melds) == 4 and all(not m.is_concealed for m in ctx.melds)
                and not ctx.is_tsumo and pair == win and len(ctx.counts) == 2):
            fs.add("金钩钓", 1)
        if ctx.is_tsumo:
            fs.add("自摸", 1)
        if ctx.is_after_kan and ctx.is_tsumo:
            fs.add("杠上花", 1)
        if ctx.is_after_kan and not ctx.is_tsumo:
            fs.add("杠上炮", 1)
        if ctx.is_chankan:
            fs.add("抢杠和", 1)
        if ctx.is_last_tile:
            fs.add("海底捞月", 1)

        return fs.items()

    def resolve_exclusions(self, items, ctx: ScoreContext):
        present = {i.name for i in items}
        drop = set()
        if "清对" in present:
            drop |= {"碰碰胡", "清一色"}
        if "将对" in present:
            drop |= {"碰碰胡"}
        if "龙七对" in present:
            drop |= {"七对"}
        kept = [i for i in items if i.name not in drop]
        return kept or items


class ChangshaRuleSet(SichuanRuleSet):
    key = "changsha"
    name = "长沙麻将"
    description = "108 张 / 将牌必须是 2·5·8 / 不能吃"
    min_fan = 1
    requires_deficiency = False

    def validate_win(self, ctx: ScoreContext):
        bad = []
        if any(ctx.counts[i] for i in range(Z_START, NUM_TILE_TYPES)):
            bad.append("长沙麻将没有字牌")
        # 需要“将牌”：雀头必须是 2 / 5 / 8
        pair_ok = False
        for dec in ctx.decompositions:
            if dec.pair < Z_START and dec.pair % 9 + 1 in (2, 5, 8):
                pair_ok = True
                break
        if ctx.decompositions and not pair_ok:
            bad.append("雀头必须是 2 / 5 / 8 才能和（将有）")
        return bad
