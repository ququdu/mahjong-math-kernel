# -*- coding: utf-8 -*-
"""选牌决策——视频第 13、15、24 条（最优和牌策略 / 攻守判断 / 押引基准）。

这是整个内核的"大脑"：把向听、进张、和牌概率、打点期望、危险度全部折算
成同一个量（期望值），然后对每张可打的牌排序。

为什么要算 EV 而不是只看进张
--------------------------
只看进张会犯两类错：

1. **听牌了但待牌全死在别人手里**：进张数一样，实际和牌率差一倍；
2. **为了多 2 张进张去打一张危险牌**：收益远小于放铳风险。

所以这里每个候选都算：

    EV = P(和牌) × 和牌期望点 − P(放铳) × 放铳期望失点

其中 P(和牌) 来自逐巡推进模型，P(放铳) 来自危险度模型，都是显式可调的。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .ev import attack_defense_judge, expected_value
from .hand import BoardState
from .probability import unseen_total, win_probability_curve
from .rulesets import get_ruleset
from .safety import DEFAULT_MODEL, DangerModel
from .score import build_context
from .shanten import shanten
from .tiles import NUM_TILE_TYPES, TILE_NAMES
from .ukeire import discard_options, effective_tiles, ukeire_total

# 对手听牌率的粗模型：第 1 巡约 10%，每巡 +5%，封顶 85%
TENPAI_BASE = 0.10
TENPAI_GROWTH = 0.05
TENPAI_CAP = 0.85

# 非听牌手牌的"打点潜力"系数（显式启发式）
PROMISE_RULES = (
    (lambda tiles, counts: len({t // 9 for t in tiles if t < 27}) == 1, 1.6),
    (lambda tiles, counts: all(t >= 27 for t in tiles), 2.0),
    (lambda tiles, counts: sum(1 for c in counts if c >= 2) >= 4, 1.2),
    (lambda tiles, counts: not any(t >= 27 or t % 9 in (0, 8) for t in tiles), 1.1),
)


def opponent_tenpai_rate(turn):
    """单个对手在第 turn 巡已经听牌的概率（经验曲线）。"""
    return min(TENPAI_CAP, TENPAI_BASE + TENPAI_GROWTH * max(0, turn - 1))


def deal_probability(tile, hand_counts, visible, turn, num_opponents=3,
                     model=DEFAULT_MODEL, opponent_discards=None):
    """打出这张牌放铳的概率。

    单个对手放铳概率 = 危险度 × 对手听牌率；多个对手按独立事件合并。
    """
    danger = model.tile_danger(tile, visible, hand_counts, turn, opponent_discards)
    p_one = danger * opponent_tenpai_rate(turn)
    p_safe = 1.0 - p_one
    return 1.0 - p_safe ** max(1, num_opponents)


def estimate_win_points(state: BoardState, ruleset, win_tiles=None):
    """估计这手牌的期望和牌点数。

    * 已经听牌：把每个和牌张都真的算一遍分（``RuleSet.score``），
      再按剩余张数加权 —— 这一档是精确的。
    * 还没听牌：用规则的典型分值 × 牌型潜力系数 —— 这一档是启发式。
    """
    counts = state.counts
    if win_tiles:
        total = sum(win_tiles.values())
        acc = 0.0
        for t, left in win_tiles.items():
            probe = BoardState.from_dict(state.to_dict())
            probe.tiles = sorted(list(state.tiles) + [t])
            probe.agari_tile = t
            probe.is_tsumo = False
            res = ruleset.score(build_context(probe, t))
            acc += (res.points if res.ok else 0) * (left / total)
        if acc > 0:
            return acc, True

    base = float(ruleset.default_win_points)
    tiles = state.tiles
    for pred, mult in PROMISE_RULES:
        if tiles and pred(tiles, counts):
            base *= mult
            break
    return base, False


@dataclass
class DiscardOption:
    tile: int
    shanten: int
    ukeire: int
    win_prob: float
    deal_prob: float
    ev: float
    win_points: float
    deal_points: float
    danger: float
    tiles: Dict[int, int] = field(default_factory=dict)
    forced: bool = False
    note: str = ""

    def to_dict(self):
        return {
            "tile": self.tile,
            "name": TILE_NAMES[self.tile],
            "shanten": self.shanten,
            "ukeire": self.ukeire,
            "ukeire_tiles": {TILE_NAMES[t]: v for t, v in sorted(self.tiles.items())},
            "win_prob": round(self.win_prob, 4),
            "deal_prob": round(self.deal_prob, 4),
            "ev": round(self.ev, 3),
            "win_points": round(self.win_points, 2),
            "deal_points": round(self.deal_points, 2),
            "danger": round(self.danger, 3),
            "forced": self.forced,
            "note": self.note,
        }


# 听牌后平均还有多少张有效牌（用来估计"听牌 -> 和牌"这一段）
ASSUMED_TENPAI_WAITS = 10


def candidate_win_prob(ukeire, shanten_now, wall, rounds, unseen,
                       assumed_waits=ASSUMED_TENPAI_WAITS):
    """单个弃牌候选的和牌概率。

    把候选自己的"当前进张 K"和"还剩几级向听"塞进同一条逐巡 DP：

    * 还差 ``s`` 级：前面 ``s`` 级每级用 K 张进张推进；
    * 最后一级是听牌，用 ``assumed_waits`` 张待牌去命中。

    假设：每级进张近似不变（同 ``probability.win_probability_curve``），
    听牌后的待牌数用经验常数 ``ASSUMED_TENPAI_WAITS``。两者都是显式参数。
    """
    if ukeire <= 0:
        return 0.0
    if shanten_now <= 0:
        levels = [ukeire]
    else:
        levels = [ukeire] * int(shanten_now) + [max(1, int(assumed_waits))]
    chain = [{"level": i, "shanten": max(0, len(levels) - 1 - i), "ukeire": v}
             for i, v in enumerate(levels)]
    curve = win_probability_curve(chain, wall, rounds, unseen=unseen)
    return curve["win"][-1] if curve["win"] else 0.0


def analyse_discards(state: BoardState, ruleset=None, model=DangerModel(),
                     rounds=None, deal_points=None, opponent_discards=None):
    """对当前 14 张手牌逐张算 EV，返回按 EV 排序的候选列表。"""
    rs = get_ruleset(ruleset or state.ruleset)
    counts = state.counts

    if sum(counts) % 3 != 2:
        raise ValueError("分析弃牌需要 3n+2 张手牌（摸牌后 14 张），当前 %d 张"
                         % sum(counts))

    visible = state.visible_counts()
    wall = state.wall_size()
    unseen = unseen_total(counts, visible, len(state.melds))
    if rounds is None:
        rounds = max(3, wall // 4)

    # 允许的摸牌（四川定缺后不能摸缺门）
    allowed = None
    if state.deficiency_suit is not None and state.deficiency_suit < 3:
        allowed = set(range(NUM_TILE_TYPES)) - set(
            range(state.deficiency_suit * 9, state.deficiency_suit * 9 + 9))

    options = discard_options(counts, len(state.melds), visible, allowed=allowed)

    # 已经听牌的话，和牌张能精确算分
    tenpai_win_tiles = None
    for opt in options:
        if opt["shanten"] == 0 and not opt["forced"]:
            probe = list(counts)
            probe[opt["discard"]] -= 1
            tenpai_win_tiles = effective_tiles(probe, len(state.melds), visible)
            break

    win_points, exact_points = estimate_win_points(state, rs, tenpai_win_tiles)
    if deal_points is None:
        deal_points = float(rs.default_deal_points)

    out = []
    for opt in options:
        tile = opt["discard"]
        k = opt["ukeire"]
        win_prob = candidate_win_prob(k, opt["shanten"], wall, rounds, unseen)

        danger = model.tile_danger(tile, visible, counts, state.turn, opponent_discards)
        p_deal = deal_probability(tile, counts, visible, state.turn,
                                  model=model, opponent_discards=opponent_discards)
        ev = expected_value(win_prob, win_points, p_deal, deal_points)

        note = ""
        if opt["forced"]:
            note = "定缺牌，必须打"
        elif opt["shanten"] == 0 and k > 0:
            note = "打后听牌"

        out.append(DiscardOption(
            tile=tile, shanten=opt["shanten"], ukeire=k,
            win_prob=win_prob, deal_prob=p_deal, ev=ev,
            win_points=win_points, deal_points=deal_points,
            danger=danger, tiles=opt["tiles"], forced=opt["forced"], note=note,
        ))

    out.sort(key=lambda o: (not o.forced, -o.ev))
    return out


def best_discard(state: BoardState, ruleset=None, **kw):
    opts = analyse_discards(state, ruleset, **kw)
    return opts[0] if opts else None


def judge(state: BoardState, best: DiscardOption = None, ruleset=None):
    """给出攻守结论：进攻 / 弃和 / 看情况。"""
    rs = get_ruleset(ruleset or state.ruleset)
    if best is None:
        best = best_discard(state, rs)
    if best is None:
        return {"advice": "无可用弃牌", "ratio": 0.0}
    decision = attack_defense_judge(
        best.win_prob, best.win_points, best.deal_prob, best.deal_points,
        threshold=1.0,
    )
    if decision.should_push:
        advice = "进攻"
    elif decision.ratio > 0.6:
        advice = "可以打，但留意危险牌"
    else:
        advice = "弃和，优先打安全牌"
    return {
        "advice": advice,
        "ratio": round(decision.ratio, 3) if decision.ratio != float("inf") else None,
        "attack": round(decision.attack, 3),
        "defense": round(decision.defense, 3),
        "reason": decision.reason,
    }
