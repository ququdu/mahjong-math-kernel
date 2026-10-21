# -*- coding: utf-8 -*-
"""国标麻将（中国标准麻将）—— 81 个番种 + 8 番起和 + 不计原则。

规则依据：国家体育总局《中国麻将竞赛规则》。底分 8 分，和牌者得分 =
底分 × 番数；点炮者付全部，自摸三家各付。起和番 8 番。

实现说明
--------
* 番种判定对**每一种合法拆解**都跑一遍，取番数最高的那一种（规则要求）。
* "不计"（番种不重复计算）按官方标注整理成一张排除表；官方文档里没有
  明确标注的组合一律保留，宁可多算也不漏算。
* 听牌形式（两面 / 边张 / 坎张 / 单钓）在和牌张落点有歧义时，取番数
  最高的解释。
"""

from __future__ import annotations

from ..meld import Decomposition, is_all_unrelated, is_chiitoi, is_kokushi, is_seven_stars, normalize_kind
from ..tiles import (
    HAKU, HATSU, CHUN, EAST, SOUTH, WEST, NORTH,
    NUM_TILE_TYPES, Z_START, is_honor, is_yaochu,
)
from .base import FanItem, FanSet, RuleSet, ScoreContext, groups_of, concealed_groups_of, all_tiles_of

# ---------------------------------------------------------------------------
#  番种表（81 个）
# ---------------------------------------------------------------------------

FAN_TABLE = {
    # 88 番
    "大四喜": 88, "大三元": 88, "绿一色": 88, "九莲宝灯": 88,
    "四杠": 88, "连七对": 88, "十三幺": 88,
    # 64 番
    "清幺九": 64, "小四喜": 64, "小三元": 64, "字一色": 64,
    "四暗刻": 64, "一色双龙会": 64,
    # 48 番
    "一色四同顺": 48, "一色四节高": 48,
    # 32 番
    "一色四步高": 32, "三杠": 32, "混幺九": 32,
    # 24 番
    "七对": 24, "七星不靠": 24, "全双刻": 24, "清一色": 24,
    "一色三同顺": 24, "一色三节高": 24, "全大": 24, "全中": 24, "全小": 24,
    # 16 番
    "清龙": 16, "三色双龙会": 16, "一色三步高": 16, "全带五": 16,
    "三同刻": 16, "三暗刻": 16,
    # 12 番
    "全不靠": 12, "组合龙": 12, "大于五": 12, "小于五": 12, "三风刻": 12,
    # 8 番
    "花龙": 8, "推不倒": 8, "三色三同顺": 8, "三色三节高": 8,
    "无番和": 8, "妙手回春": 8, "海底捞月": 8, "杠上开花": 8, "抢杠和": 8,
    # 6 番
    "碰碰和": 6, "混一色": 6, "三色三步高": 6, "五门齐": 6,
    "全求人": 6, "双暗杠": 6, "双箭刻": 6,
    # 4 番
    "全带幺": 4, "不求人": 4, "双明杠": 4, "和绝张": 4,
    # 2 番
    "箭刻": 2, "圈风刻": 2, "门风刻": 2, "门前清": 2, "平和": 2,
    "四归一": 2, "双同刻": 2, "双暗刻": 2, "暗杠": 2, "断幺": 2,
    # 1 番
    "一般高": 1, "喜相逢": 1, "连六": 1, "老少副": 1, "幺九刻": 1,
    "明杠": 1, "缺一门": 1, "无字": 1, "边张": 1, "坎张": 1,
    "单钓将": 1, "自摸": 1, "花牌": 1,
}

# ---------------------------------------------------------------------------
#  "不计"排除表：key 出现时，value 里的番种不再计入
# ---------------------------------------------------------------------------

EXCLUSIONS = {
    "大四喜": ["三风刻", "碰碰和", "圈风刻", "门风刻"],
    "大三元": ["箭刻", "双箭刻"],
    "绿一色": ["混一色"],
    "九莲宝灯": ["清一色", "门前清", "无字", "缺一门"],
    "四杠": ["碰碰和", "三杠", "双明杠", "双暗杠", "明杠", "暗杠", "单钓将"],
    "连七对": ["七对", "清一色", "门前清", "单钓将", "无字", "缺一门"],
    "十三幺": ["五门齐", "门前清", "单钓将", "无字"],
    "清幺九": ["碰碰和", "全带幺", "幺九刻", "无字", "缺一门"],
    "小四喜": ["三风刻"],
    "小三元": ["箭刻", "双箭刻"],
    "字一色": ["碰碰和", "全带幺", "幺九刻", "混幺九"],
    "四暗刻": ["碰碰和", "三暗刻", "双暗刻", "门前清", "不求人", "单钓将"],
    "一色双龙会": ["七对", "清一色", "平和", "一般高", "老少副", "无字", "缺一门"],
    "一色四同顺": ["一色三同顺", "一般高", "四归一"],
    "一色四节高": ["一色三节高", "碰碰和"],
    "一色四步高": ["一色三步高", "连六"],
    "三杠": ["双明杠", "双暗杠", "明杠", "暗杠"],
    "混幺九": ["碰碰和", "全带幺", "幺九刻"],
    "七对": ["门前清", "单钓将"],
    "七星不靠": ["全不靠", "五门齐", "门前清"],
    "全双刻": ["碰碰和", "断幺"],
    "清一色": ["无字", "缺一门"],
    "一色三同顺": ["一般高"],
    "清龙": ["连六", "老少副"],
    "三色双龙会": ["喜相逢", "老少副", "平和", "无字"],
    "一色三步高": ["连六"],
    "三同刻": ["双同刻"],
    "三暗刻": ["双暗刻"],
    "组合龙": ["五门齐", "花龙"],
    "大于五": [],
    "三风刻": ["幺九刻"],
    "花龙": ["连六", "老少副"],
    "三色三同顺": ["喜相逢"],
    "三色三节高": ["双同刻"],
    "全求人": ["单钓将", "门前清"],
    "双箭刻": ["箭刻"],
    "不求人": ["自摸", "门前清"],
    "双明杠": ["明杠"],
    "双暗杠": ["暗杠"],
    "平和": ["无字"],
    "断幺": ["无字"],
    "箭刻": [],
    "圈风刻": [],
    "门风刻": [],
    "和绝张": [],
    "妙手回春": ["自摸"],
    "海底捞月": [],
    "杠上开花": [],
    "抢杠和": [],
    "无番和": list(FAN_TABLE.keys()),
}

# 推不倒用的牌面集合（180° 旋转后不变的牌）
PUSHABLE_TILES = frozenset(
    [9, 10, 11, 12, 13, 16, 17]        # 1p 2p 3p 4p 5p 8p 9p
    + [19, 21, 22, 23, 25, 26]         # 2s 4s 5s 6s 8s 9s
    + [HAKU]
)

GREEN_TILES = frozenset([19, 20, 21, 23, 25, HATSU])   # 2s3s4s6s8s 发


def _suits_present(tiles):
    out = set()
    for t in tiles:
        out.add(t // 9 if t < Z_START else 3)
    return out


def _num_suits(tiles):
    return {t // 9 for t in tiles if t < Z_START}


def _ranks_in_suit(seqs, suit):
    return sorted({s - suit * 9 + 1 for s in seqs if suit * 9 <= s < suit * 9 + 7})


def _trips_in_suit(trips, suit):
    return sorted({t - suit * 9 + 1 for t in trips if suit * 9 <= t < suit * 9 + 9})


def _has_three_consecutive(ranks, step=1):
    """ranks 中是否存在 r, r+step, r+2*step（三个）"""
    rs = set(ranks)
    for r in rs:
        if r + step in rs and r + 2 * step in rs:
            return True
    return False


def _has_four_consecutive(ranks, step=1):
    rs = set(ranks)
    for r in rs:
        if r + step in rs and r + 2 * step in rs and r + 3 * step in rs:
            return True
    return False


class GBRuleSet(RuleSet):
    key = "gb"
    name = "国标麻将"
    description = "中国标准麻将（81 番种 / 8 番起和 / 底分 8）"
    min_fan = 8
    base_points = 8
    dealer_multiplier = 1.0
    allow_chi = True
    allow_peng = True
    allow_gang = True
    has_honors = True
    has_flowers = True
    default_win_points = 64     # 8 番起和 × 底分 8
    default_deal_points = 64

    # -- 特殊和牌形 ------------------------------------------------------

    def fallback_items(self, ctx: ScoreContext):
        return [FanItem("无番和", 8, "没有其它番种，按无番和计 8 番")]

    def detect_special(self, ctx: ScoreContext):
        counts = ctx.counts
        out = []
        if ctx.melds:
            return out

        if is_kokushi(counts):
            fs = FanSet()
            fs.add("十三幺", 88)
            if ctx.menzen and not ctx.is_tsumo:
                pass
            fs.add("门前清", 2)
            fs.add("单钓将", 1)
            if not ctx.is_tsumo:
                pass
            out.append(("十三幺", fs.items()))
            return out

        if is_chiitoi(counts):
            fs = FanSet()
            pairs = [i for i, c in enumerate(counts) if c >= 2]
            # 连七对：同一花色 7 连对
            if len(pairs) == 7 and all(p < Z_START for p in pairs):
                suits = {p // 9 for p in pairs}
                ranks = sorted(p % 9 + 1 for p in pairs)
                if (len(suits) == 1 and ranks == list(range(ranks[0], ranks[0] + 7))):
                    fs.add("连七对", 88)
                    fs.add("清一色", 24)
                    fs.add("门前清", 2)
                    out.append(("连七对", fs.items()))
                    return out
            fs.add("七对", 24)
            fs.add("门前清", 2)
            if ctx.is_tsumo:
                fs.add("自摸", 1)
            if all(p < Z_START for p in pairs) and len({p // 9 for p in pairs}) == 1:
                fs.add("清一色", 24)
            out.append(("七对", fs.items()))

        if is_seven_stars(counts):
            fs = FanSet()
            fs.add("七星不靠", 24)
            fs.add("五门齐", 6)
            fs.add("门前清", 2)
            out.append(("七星不靠", fs.items()))
        elif is_all_unrelated(counts):
            fs = FanSet()
            fs.add("全不靠", 12)
            fs.add("门前清", 2)
            out.append(("全不靠", fs.items()))

        return out

    # -- 主检测 ----------------------------------------------------------

    def detect_fans(self, ctx: ScoreContext, dec: Decomposition):
        fs = FanSet()
        seqs, trips = groups_of(dec)
        cseqs, ctrips = concealed_groups_of(dec)
        pair = dec.pair
        tiles = all_tiles_of(dec)
        win = ctx.win_tile
        menzen = ctx.menzen
        honor_present = any(is_honor(t) for t in tiles)
        suits = _suits_present(tiles)
        num_suits = _num_suits(tiles)
        ranks = [t % 9 + 1 for t in tiles if t < Z_START]

        all_seq = len(seqs) == 4
        all_trip = len(trips) == 4

        # ---- 暗刻统计（抢和完成的刻子算明刻）----
        concealed_trips = list(ctrips)
        if not ctx.is_tsumo and win in concealed_trips:
            concealed_trips.remove(win)
        n_an = len(concealed_trips)

        # 杠
        n_minkan = sum(1 for m in ctx.melds if m.kind in ("minkan", "kakan"))
        n_ankan = sum(1 for m in ctx.melds if m.kind == "ankan")
        n_kan = n_minkan + n_ankan

        # ---- 役满 / 高番 ----
        if all_trip and {EAST, SOUTH, WEST, NORTH}.issubset(set(trips)):
            fs.add("大四喜", 88)
        if {HAKU, HATSU, CHUN}.issubset(set(trips)):
            fs.add("大三元", 88)
        if all(t in GREEN_TILES for t in tiles):
            fs.add("绿一色", 88)
        if n_kan == 4:
            fs.add("四杠", 88)
        if menzen and not ctx.melds and len(num_suits) == 1 and not honor_present:
            suit = next(iter(num_suits))
            base = [3, 1, 1, 1, 1, 1, 1, 1, 3]
            got = [ctx.counts[suit * 9 + i] for i in range(9)]
            if sum(got) == 14 and all(got[i] >= base[i] for i in range(9)):
                fs.add("九莲宝灯", 88)

        # ---- 64 番 ----
        if all_trip and all(t in (0, 8, 9, 17, 18, 26) for t in tiles):
            fs.add("清幺九", 64)
        if all_trip and all(is_yaochu(t) for t in tiles) and honor_present:
            fs.add("混幺九", 32)
        wind_trips = {t for t in trips if EAST <= t <= NORTH}
        dragon_trips = {t for t in trips if t >= HAKU}
        if len(wind_trips) == 3 and EAST <= pair <= NORTH:
            fs.add("小四喜", 64)
        if len(dragon_trips) == 2 and pair >= HAKU:
            fs.add("小三元", 64)
        if all(is_honor(t) for t in tiles):
            fs.add("字一色", 64)
        if n_an == 4:
            fs.add("四暗刻", 64)
        # 一色双龙会：同花色 123 123 789 789 + 5 雀头
        if len(num_suits) == 1 and not honor_present and len(seqs) == 4:
            suit = next(iter(num_suits))
            r = sorted(s - suit * 9 + 1 for s in seqs)
            if r == [1, 1, 7, 7] and pair == suit * 9 + 4:
                fs.add("一色双龙会", 64)

        # ---- 48 番 ----
        if len(seqs) == 4 and len(set(seqs)) == 1:
            fs.add("一色四同顺", 48)
        if len(trips) == 4 and len(set(trips)) == 4:
            for suit in range(3):
                rr = _trips_in_suit(trips, suit)
                if len(rr) == 4 and rr == list(range(rr[0], rr[0] + 4)):
                    fs.add("一色四节高", 48)
                    break

        # ---- 32 番 ----
        if len(seqs) == 4:
            for suit in range(3):
                rr = _ranks_in_suit(seqs, suit)
                if len(rr) == 4 and (_has_four_consecutive(rr, 1) or _has_four_consecutive(rr, 2)):
                    fs.add("一色四步高", 32)
                    break
        if n_kan == 3:
            fs.add("三杠", 32)

        # ---- 24 番 ----
        if all_trip and all(t < Z_START and t % 9 + 1 in (2, 4, 6, 8) for t in tiles):
            fs.add("全双刻", 24)
        if len(num_suits) == 1 and not honor_present:
            fs.add("清一色", 24)
        if len(seqs) >= 3 and max([seqs.count(s) for s in set(seqs)]) >= 3:
            fs.add("一色三同顺", 24)
        if len(trips) >= 3:
            for suit in range(3):
                rr = _trips_in_suit(trips, suit)
                if len(rr) >= 3 and _has_three_consecutive(rr, 1):
                    fs.add("一色三节高", 24)
                    break
        if not honor_present:
            if all(r >= 7 for r in ranks):
                fs.add("全大", 24)
            elif all(4 <= r <= 6 for r in ranks):
                fs.add("全中", 24)
            elif all(r <= 3 for r in ranks):
                fs.add("全小", 24)

        # ---- 16 番 ----
        for suit in range(3):
            rr = set(_ranks_in_suit(seqs, suit))
            if {1, 4, 7}.issubset(rr):
                fs.add("清龙", 16)
                break
        # 三色双龙会：两门各有 123 与 789，第三门 5 作雀头
        if len(seqs) == 4:
            seq_set = set(seqs)
            for a in range(3):
                for b in range(3):
                    if a == b:
                        continue
                    c = 3 - a - b
                    if ({a * 9, a * 9 + 6} <= seq_set
                            and {b * 9, b * 9 + 6} <= seq_set
                            and c < 3 and pair == c * 9 + 4):
                        fs.add("三色双龙会", 16)
        if len(seqs) >= 3:
            for suit in range(3):
                rr = _ranks_in_suit(seqs, suit)
                if len(rr) >= 3 and (_has_three_consecutive(rr, 1) or _has_three_consecutive(rr, 2)):
                    fs.add("一色三步高", 16)
                    break
        if self._all_contain_five(dec):
            fs.add("全带五", 16)
        if len(trips) >= 3:
            for r in range(1, 10):
                if len({t // 9 for t in trips if t < Z_START and t % 9 + 1 == r}) >= 3:
                    fs.add("三同刻", 16)
                    break
        if n_an == 3:
            fs.add("三暗刻", 16)

        # ---- 12 番 ----
        if len(seqs) == 4 and self._is_zuhelong(seqs):
            fs.add("组合龙", 12)
        if not honor_present:
            if all(r >= 6 for r in ranks):
                fs.add("大于五", 12)
            elif all(r <= 4 for r in ranks):
                fs.add("小于五", 12)
        if len(wind_trips) == 3:
            fs.add("三风刻", 12)

        # ---- 8 番 ----
        if len(seqs) == 4 and self._is_hualong(seqs):
            fs.add("花龙", 8)
        if all(t in PUSHABLE_TILES for t in tiles):
            fs.add("推不倒", 8)
        if len(seqs) >= 3:
            for r in range(1, 8):
                ss = {s // 9 for s in seqs if s < Z_START and s % 9 + 1 == r}
                if len(ss) >= 3:
                    fs.add("三色三同顺", 8)
                    break
        if len(trips) >= 3:
            for r in range(1, 8):
                s1 = {t // 9 for t in trips if t < Z_START and t % 9 + 1 == r}
                s2 = {t // 9 for t in trips if t < Z_START and t % 9 + 1 == r + 1}
                s3 = {t // 9 for t in trips if t < Z_START and t % 9 + 1 == r + 2}
                if any(a != b and b != ch and a != ch
                       for a in s1 for b in s2 for ch in s3):
                    fs.add("三色三节高", 8)
                    break

        # ---- 6 番 ----
        if all_trip:
            fs.add("碰碰和", 6)
        if len(num_suits) == 1 and honor_present:
            fs.add("混一色", 6)
        if len(seqs) >= 3:
            for r in range(1, 8):
                s1 = {s // 9 for s in seqs if s < Z_START and s % 9 + 1 == r}
                s2 = {s // 9 for s in seqs if s < Z_START and s % 9 + 1 == r + 1}
                s3 = {s // 9 for s in seqs if s < Z_START and s % 9 + 1 == r + 2}
                if any(a != b and b != c and a != c
                       for a in s1 for b in s2 for c in s3):
                    fs.add("三色三步高", 6)
                    break
        has_wind = any(EAST <= t <= NORTH for t in tiles)
        has_dragon = any(t >= HAKU for t in tiles)
        if len(num_suits) == 3 and has_wind and has_dragon:
            fs.add("五门齐", 6)
        if (len(ctx.melds) == 4 and all(not m.is_concealed for m in ctx.melds)
                and not ctx.is_tsumo and pair == win and len(ctx.counts) == 2):
            fs.add("全求人", 6)
        if n_minkan == 2 and n_kan == 2:
            fs.add("双明杠", 4)
        if n_ankan == 2 and n_kan == 2:
            fs.add("双暗杠", 6)
        if len(dragon_trips) == 2:
            fs.add("双箭刻", 6)

        # ---- 4 番 ----
        if self._all_contain_yaochu(dec):
            fs.add("全带幺", 4)
        if menzen and ctx.is_tsumo:
            fs.add("不求人", 4)
        if ctx.visible is not None and win >= 0 and ctx.visible[win] >= 3:
            fs.add("和绝张", 4)

        # ---- 2 番 ----
        for t in dragon_trips:
            fs.add("箭刻", 2)
        if ctx.round_wind in trips:
            fs.add("圈风刻", 2)
        if ctx.seat_wind in trips:
            fs.add("门风刻", 2)
        if menzen and not ctx.is_tsumo:
            fs.add("门前清", 2)
        if n_an == 2:
            fs.add("双暗刻", 2)
        if n_ankan == 1 and n_kan == 1:
            fs.add("暗杠", 2)
        if not any(is_yaochu(t) for t in tiles):
            fs.add("断幺", 2)
        # 四归一：4 张相同牌分散在不同面子中
        actual = list(ctx.counts)
        for m in ctx.melds:
            for t in m.tiles():
                actual[t] += 1
        for t in range(NUM_TILE_TYPES):
            if actual[t] == 4 and not any(m.is_kan and m.tile == t for m in ctx.melds):
                fs.add("四归一", 2)
        if len(trips) >= 2:
            for r in range(1, 10):
                ss = {t // 9 for t in trips if t < Z_START and t % 9 + 1 == r}
                if len(ss) >= 2:
                    fs.add("双同刻", 2)
                    break

        # ---- 1 番 ----
        if len(seqs) >= 2:
            for s in set(seqs):
                if seqs.count(s) >= 2:
                    fs.add("一般高", 1)
                    break
        if len(seqs) >= 2:
            for r in range(1, 8):
                ss = {s // 9 for s in seqs if s < Z_START and s % 9 + 1 == r}
                if len(ss) >= 2:
                    fs.add("喜相逢", 1)
                    break
        if len(seqs) >= 2:
            seq_set = set(seqs)
            for s in seq_set:
                if s < Z_START and (s % 9) <= 3 and (s + 3) in seq_set:
                    fs.add("连六", 1)
                    break
                if s < Z_START and (s % 9) == 0 and (s + 6) in seq_set:
                    fs.add("老少副", 1)
                    break
        for t in trips:
            if is_yaochu(t):
                fs.add("幺九刻", 1)
                break
        if n_minkan == 1 and n_kan == 1:
            fs.add("明杠", 1)
        if len(num_suits) <= 2:
            fs.add("缺一门", 1)
        if not honor_present:
            fs.add("无字", 1)
        if ctx.is_tsumo:
            fs.add("自摸", 1)

        # ---- 听牌形式 ----
        self._add_wait_fans(fs, ctx, dec, menzen)

        # ---- 偶然役 ----
        if ctx.is_after_kan and ctx.is_tsumo:
            fs.add("杠上开花", 8)
        if ctx.is_chankan:
            fs.add("抢杠和", 8)
        if ctx.is_last_tile:
            if ctx.is_tsumo:
                fs.add("妙手回春", 8)
            else:
                fs.add("海底捞月", 8)

        return fs.items()

    # -- 工具 ------------------------------------------------------------

    @staticmethod
    def _all_contain_five(dec: Decomposition):
        for k, t in dec.melds:
            if normalize_kind(k) == "t":
                if not (t < Z_START and t % 9 + 1 == 5):
                    return False
            else:
                if not (t < Z_START and 3 <= t % 9 + 1 <= 5):
                    return False
        return dec.pair < Z_START and dec.pair % 9 + 1 == 5

    @staticmethod
    def _all_contain_yaochu(dec: Decomposition):
        for k, t in dec.melds:
            if normalize_kind(k) == "t":
                if not is_yaochu(t):
                    return False
            else:
                if not (is_yaochu(t) or is_yaochu(t + 2)):
                    return False
        return is_yaochu(dec.pair)

    @staticmethod
    def _is_zuhelong(seqs):
        """组合龙：三门各一副 123 / 456 / 789（不能错位）"""
        s = set(seqs)
        for a in range(3):
            for b in range(3):
                for c in range(3):
                    if len({a, b, c}) != 3:
                        continue
                    if (a * 9) in s and (b * 9 + 3) in s and (c * 9 + 6) in s:
                        return True
        return False

    @staticmethod
    def _is_hualong(seqs):
        """花龙：三门各一副顺子连成 1-9。

        与组合龙同形（组合龙额外要求 147/258/369 不错位的对齐），
        所以两者同时成立时按不计规则只算组合龙。
        """
        return GBRuleSet._is_zuhelong(seqs)

    @staticmethod
    def _wait_options(ctx: ScoreContext, dec: Decomposition):
        """该拆解下和牌张所有可能的解释"""
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
        if not out:
            out.add("unknown")
        return out

    def _add_wait_fans(self, fs, ctx, dec, menzen):
        seqs, trips = groups_of(dec)
        pair = dec.pair
        options = self._wait_options(ctx, dec)
        all_seq = len(seqs) == 4
        pair_is_value = pair >= HAKU or pair in (ctx.round_wind, ctx.seat_wind)

        best = None
        for w in options:
            bonus = []
            if all_seq and menzen and not pair_is_value and w == "两面":
                bonus.append(("平和", 2))
            if w == "边张":
                bonus.append(("边张", 1))
            elif w == "坎张":
                bonus.append(("坎张", 1))
            elif w == "单钓":
                bonus.append(("单钓将", 1))
            score = sum(f for _, f in bonus)
            if best is None or score > best[0]:
                best = (score, bonus)
        for name, fan in (best[1] if best else []):
            fs.add(name, fan)

    # -- 不计 ------------------------------------------------------------

    def resolve_exclusions(self, items, ctx: ScoreContext):
        present = {i.name for i in items}
        drop = set()
        for name in present:
            for other in EXCLUSIONS.get(name, ()):
                if other != name:
                    drop.add(other)
        # 门清派生关系：不求人 已含 自摸
        if "不求人" in present:
            drop.add("自摸")
        kept = [i for i in items if i.name not in drop]
        if kept:
            kept = [i for i in kept if i.name != "无番和"]
        return kept


def fan_table():
    """81 番种表（name -> fan）"""
    return dict(FAN_TABLE)
