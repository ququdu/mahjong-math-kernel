# -*- coding: utf-8 -*-
"""期望值体系——视频第 13~20、24~27、45 条方程的落地。

核心就是一个三情形加权：

    EV = P(和牌) × 和牌得分 − P(放铳) × 放铳失分 + P(流局) × 0

在它之上再做：

* ``attack_defense_judge``  押引判据：收益 / 风险 比超过阈值就进攻
* ``equilibrium_push_prob`` 和了放铳均衡点：边际收益 = 边际风险
* ``placement_probabilities`` 期待顺位：把点数换算成最终名次概率
* ``integral_ev``           全巡目期望收益的折现积分

参数都是显式的：平均和牌点、平均放铳点、危险度、巡目衰减，
想按自己的桌风调就改参数，不用改代码。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .probability import turn_value


# ---------------------------------------------------------------------------
#  三情形期望值
# ---------------------------------------------------------------------------

def expected_value(win_prob, avg_win_points, deal_prob, avg_deal_points,
                   draw_prob=None, draw_value=0.0):
    """EV = P(和) * 得分 - P(铳) * 失分 + P(流局) * 流局价值"""
    if draw_prob is None:
        draw_prob = max(0.0, 1.0 - win_prob - deal_prob)
    return (win_prob * avg_win_points
            - deal_prob * avg_deal_points
            + draw_prob * draw_value)


def score_expectation(win_prob, avg_score, deal_prob, avg_loss, draw_prob=0.0):
    """第 16 / 45 条：和牌 / 放铳 / 流局 三情形的加权期望。"""
    return expected_value(win_prob, avg_score, deal_prob, avg_loss, draw_prob)


def riichi_ev(win_prob, avg_win_points, deal_prob, avg_deal_points,
              riichi_stick=1000.0, extra_win=0.0, tenpai_bonus=0.0):
    """第 17 条：立直（报听）期望值 = 和牌收益 + 供托 - 成本。

    中国麻将没有立直，但"报听/听牌宣言"的变体可以用同一个式子：
    ``riichi_stick`` 当作宣言成本，``extra_win`` 当作宣言带来的番数加成。
    """
    return (win_prob * (avg_win_points + extra_win + riichi_stick)
            - deal_prob * avg_deal_points
            - riichi_stick
            + tenpai_bonus)


def expected_ukeire_value(ukeire_dist: Dict[int, int], wall):
    """第 6 条：各摸牌情形下有效牌数的加权平均（按剩余张数加权）。"""
    total = sum(ukeire_dist.values())
    if total <= 0:
        return 0.0
    return sum(k * (v / total) for k, v in ukeire_dist.items())


def tile_efficiency(ukeire_total, wall):
    """第 4 条：牌效率 = 有效牌张数 / 牌山剩余张数（下一巡直接命中率）。"""
    if wall <= 0:
        return 0.0
    return ukeire_total / wall


# ---------------------------------------------------------------------------
#  押引判断
# ---------------------------------------------------------------------------

@dataclass
class PushDecision:
    attack: float
    defense: float
    ratio: float
    should_push: bool
    reason: str


def attack_defense_judge(win_prob, avg_win_points, deal_prob, avg_deal_points,
                         threshold=1.0):
    """第 15 / 24 条：押引判据。

    进攻收益 = P(和) × 和牌点；风险 = P(铳) × 放铳失分。
    收益 / 风险 > 阈值 就进攻。
    """
    attack = win_prob * avg_win_points
    defense = deal_prob * avg_deal_points
    if defense <= 0:
        return PushDecision(attack, defense, float("inf"), attack > 0,
                            "没有放铳风险")
    ratio = attack / defense
    push = ratio > threshold
    return PushDecision(
        attack, defense, ratio, push,
        "收益/风险 = %.2f %s 阈值 %.2f" % (ratio, ">" if push else "<=", threshold),
    )


def equilibrium_push_prob(avg_win_points, avg_deal_points):
    """第 26 条：和了放铳均衡点。

    令 P(和)×和牌点 = P(铳)×失分（把 P(铳) 写成 P(和) 的比例），
    得到"放铳概率最多能忍受到多少"的临界值：::

        P(铳) / P(和) <= 平均和牌点 / 平均放铳点

    返回临界比值。
    """
    if avg_deal_points <= 0:
        return float("inf")
    return avg_win_points / avg_deal_points


def equilibrium_check(win_prob, avg_win_points, deal_prob, avg_deal_points):
    """第 26 条：直接判断当前概率是否落在均衡点以内。"""
    limit = equilibrium_push_prob(avg_win_points, avg_deal_points)
    if win_prob <= 0:
        return {"limit": limit, "actual": float("inf"), "balanced": False}
    actual = deal_prob / win_prob
    return {"limit": limit, "actual": actual, "balanced": actual <= limit}


# ---------------------------------------------------------------------------
#  巡目价值 / 折现
# ---------------------------------------------------------------------------

def turn_value_ev(turn, base_ev, decay=0.90):
    """第 25 条：随巡目指数衰减的局面价值。"""
    return base_ev * turn_value(turn, decay)


def integral_ev(rate_fn, rounds, discount=0.9):
    """第 27 条：全巡目期望收益的离散积分 sum_t rate(t) * discount^t。"""
    return sum(rate_fn(t) * (discount ** t) for t in range(1, int(rounds) + 1))


# ---------------------------------------------------------------------------
#  期待顺位（第 14 / 20 条）
# ---------------------------------------------------------------------------

PLACEMENT_VALUES = {1: 1.0, 2: 0.35, 3: -0.35, 4: -1.0}


def placement_probabilities(scores, mu=None, sigma=None, samples=4000, seed=7):
    """把当前点数换算成最终名次概率。

    模型：每家的最终点数 ~ 正态(当前点数 + 期望变动, sigma)，独立抽样后排名。
    这是一个显式声明的近似（真实局面里各家点数强相关），但足够做攻守权衡，
    而且参数只有一个 ``sigma``，好调。

    返回 ``[{"place": {1: p1, 2: p2, 3: p3, 4: p4}, "expected_place": 2.1}, ...]``
    """
    n = len(scores)
    if mu is None:
        mu = [0.0] * n
    if sigma is None:
        # 以 25000 点起手、单局波动约 8000 点估计
        sigma = [max(500.0, 0.32 * max(1.0, abs(sum(scores)) / max(1, n))) for _ in range(n)]

    rng = random.Random(seed)
    counts = [dict() for _ in range(n)]

    for _ in range(samples):
        final = []
        for i in range(n):
            v = scores[i] + mu[i] + rng.gauss(0.0, sigma[i])
            final.append((v, i))
        final.sort(key=lambda x: -x[0])
        for place, (_, i) in enumerate(final, start=1):
            counts[i][place] = counts[i].get(place, 0) + 1

    out = []
    for i in range(n):
        place_probs = {p: counts[i].get(p, 0) / samples for p in range(1, n + 1)}
        exp_place = sum(p * v for p, v in place_probs.items())
        out.append({"place": place_probs, "expected_place": exp_place})
    return out


def placement_ev(scores, hero=0, mu=None, values=None, samples=4000, seed=7):
    """第 14 条：当前场况下最终顺位的期望值（默认 1/2/3/4 名 = 1/0.35/-0.35/-1）。"""
    if values is None:
        values = PLACEMENT_VALUES
    probs = placement_probabilities(scores, mu, samples=samples, seed=seed)
    me = probs[hero]
    return sum(values[p] * q for p, q in me["place"].items())


def placement_ev_delta(scores, hero=0, delta=None, samples=3000, seed=7):
    """比较"维持现状"和"给定变动"两种情况的顺位期望差，用于攻守决策。"""
    base = placement_ev(scores, hero, samples=samples, seed=seed)
    mu = [0.0] * len(scores)
    for i, d in (delta or {}).items():
        mu[i] = d
    after = placement_ev(scores, hero, mu=mu, samples=samples, seed=seed)
    return {"before": base, "after": after, "delta": after - base}


# ---------------------------------------------------------------------------
#  综合：一手牌的完整 EV
# ---------------------------------------------------------------------------

def hand_ev(win_prob, deal_prob, avg_win_points, avg_deal_points,
            decay_turn=None, decay=0.90):
    """把上面几样拼成一手牌的总期望。"""
    ev = expected_value(win_prob, avg_win_points, deal_prob, avg_deal_points)
    if decay_turn is not None:
        ev *= turn_value(decay_turn, decay)
    return ev
