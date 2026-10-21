# -*- coding: utf-8 -*-
"""概率模型——视频里第 2/3/5/6/9/10/11/12/25/33~40 条方程的落地。

这里分两类东西，写清楚免得混：

**精确的（组合数学直接算）**
    ``hypergeometric_at_least_one``  从 N 张里摸 n 张，至少命中 1 张 K 张有效牌
    ``hypergeometric_pmf``           命中恰好 k 张的概率
    ``expected_draws``               首次命中的期望摸牌数 = N / K

**模型（有假设，参数可调）**
    ``advance_chain``                逐巡推进的马尔可夫链：向听 -> 向听 -> 和牌
    ``turn_win_rate``                瞬时和牌强度 h(t) = h0 * exp(-λt)
    ``expr_decay_win_curve``         一阶动力学 p(t) = 1 - exp(-λt)
    ``ippatsu_probability`` 等       偶然役的经验概率

链条模型的假设都写在函数注释里，参数暴露出来，谁不同意就自己调。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

from .shanten import shanten
from .tiles import NUM_TILE_TYPES, Z_START
from .ukeire import effective_tiles, ukeire_total

# 4 人麻将：一"巡"里别人摸 3 张，自己摸 1 张
DRAWS_PER_ROUND = 4


# ---------------------------------------------------------------------------
#  超几何分布（精确）
# ---------------------------------------------------------------------------

def hypergeometric_at_least_one(total, hits, draws):
    """从 total 张牌里摸 draws 张，至少摸到 1 张 hits 张有效牌的概率。

    P = 1 - C(total-hits, draws) / C(total, draws)

    用连乘避免大组合数，数值稳定。
    """
    if total <= 0 or hits <= 0 or draws <= 0:
        return 0.0
    draws = min(draws, total)
    if total - hits < draws:
        return 1.0
    miss = 1.0
    for i in range(draws):
        miss *= (total - hits - i) / (total - i)
    return 1.0 - miss


def hypergeometric_pmf(total, hits, draws, k):
    """恰好摸到 k 张有效牌的概率。"""
    if k < 0 or k > min(hits, draws) or draws > total:
        return 0.0
    return (_comb(hits, k) * _comb(total - hits, draws - k)) / _comb(total, draws)


def _comb(n, k):
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


def hypergeometric_mean(total, hits, draws):
    """命中张数的期望 = draws * hits / total"""
    if total <= 0:
        return 0.0
    return draws * hits / total


def expected_draws(total, hits):
    """首次摸到有效牌的期望摸牌数（几何分布均值）= total / hits。"""
    if hits <= 0:
        return float("inf")
    return total / hits


# ---------------------------------------------------------------------------
#  进张链：向听逐级推进
# ---------------------------------------------------------------------------

def advance_chain(counts, open_melds=0, visible=None, max_levels=8,
                  allow_chiitoi=True, allow_kokushi=True):
    """把当前手牌一级一级往听牌推，记录每一级的进张数。

    做法：每级算出有效牌，挑"剩得最多"的那张完成这一级（并列时挑靠中间的），
    再打出进张最小的牌，然后继续。这样得到一条**合理路线**上的进张序列，
    用来跑概率链。

    为什么挑"剩得最多"而不是"下一级进张最大"：后者要对每张有效牌都算一遍
    进张，复杂度 34 倍，慢到没法交互。剩得最多是个便宜且稳的代理。

    返回 ``[{"level", "shanten", "ukeire", "tiles"}, ...]``。
    """
    counts = list(counts)
    if visible is None:
        visible = [0] * NUM_TILE_TYPES
    else:
        visible = list(visible)

    chain = []
    for _ in range(max(1, max_levels)):
        s = shanten(counts, open_melds, allow_chiitoi, allow_kokushi)
        eff = effective_tiles(counts, open_melds, visible, allow_chiitoi, allow_kokushi)
        chain.append({"level": len(chain), "shanten": s,
                      "ukeire": ukeire_total(eff), "tiles": eff})
        if s <= 0 or not eff:
            break
        if sum(counts) % 3 != 1:
            break          # 张数不合法（不是 3n+1），没法再往下推

        # 挑剩得最多的那张（并列时挑 3~7 这种更靠中间、更可能连上的）
        def rank(item):
            t, left = item
            pos = t % 9 if t < Z_START else 3
            centrality = min(pos + 1, 9 - pos) if t < Z_START else 4
            return (left, centrality, -t)

        draw_tile = max(eff.items(), key=rank)[0]
        counts[draw_tile] += 1
        _discard_worst(counts, open_melds, visible, allow_chiitoi, allow_kokushi)

    return chain


def _discard_worst(counts, open_melds, visible, allow_chiitoi, allow_kokushi):
    """从 14 张里丢出一张，让留下的 13 张最优（原地修改）。

    只看向听 + 连接度：``shanten`` 一次调用足够，**不再对每张候选都算一遍
    完整进张**。后者要对 34 张牌各跑 34 次递归（约 1200 次），实测占了
    ``analyze`` 冷启动七成时间，收益却只是让模拟路线更"漂亮"一点。
    """
    if sum(counts) % 3 != 2:
        return None
    base = shanten(counts, open_melds, allow_chiitoi, allow_kokushi)
    best = None
    for t in range(NUM_TILE_TYPES):
        if counts[t] == 0:
            continue
        counts[t] -= 1
        s = shanten(counts, open_melds, allow_chiitoi, allow_kokushi)
        conn = _connectivity(counts)
        counts[t] += 1
        cand = (s, -conn, -t)
        if best is None or cand < best[0]:
            best = (cand, t)
    if best is None:
        return None
    counts[best[1]] -= 1
    visible[best[1]] += 1
    return best[1]


def _connectivity(counts):
    """连接度：相邻牌越多越有结构。便宜的进张代理。"""
    score = 0
    for i in range(27):
        c = counts[i]
        if c == 0:
            continue
        pos = i % 9
        if pos > 0:
            score += c * counts[i - 1]
        if pos < 8:
            score += c * counts[i + 1]
        if pos < 7:
            score += c * counts[i + 2]
    return score


# ---------------------------------------------------------------------------
#  逐巡累积和牌概率（模型）
# ---------------------------------------------------------------------------

def win_probability_curve(chain, wall, rounds=None, draws_per_round=DRAWS_PER_ROUND,
                          unseen=None):
    """给定进张链和剩余牌山，逐巡算出累积和牌概率。

    模型假设（都写在这里，方便质疑）::

      * 牌山每巡少 ``draws_per_round`` 张，自己每巡摸 1 张；
      * 有效牌在"还没看到的牌"里均匀分布，所以单次摸牌命中率是
        **密度** ``K / unseen``（unseen = 全场还没看见的牌数，约 123 张）。
        不能用 ``K / 剩余牌山``：有效牌数 K 是按"所有没看到的牌"算的，
        两边的分母必须一致，否则命中率会被算高好几倍；
      * 摸到的非有效牌直接打出（不再回到牌山）；
      * 进张数在两级之间保持不变（只靠密度近似体现消耗）。

    返回 ``{"win": [...], "tenpai": [...], "turn_prob": [...]}``，
    第 i 项是"到第 i 巡为止"的累积概率。
    """
    if rounds is None:
        rounds = max(1, wall // draws_per_round)
    rounds = int(rounds)
    denom = float(unseen if unseen else wall)
    if denom <= 0:
        denom = 1.0

    win_cum = []
    tenpai_cum = []
    turn_prob = []

    # 每级的进张；链尾若还没听牌，按末级进张继续外推（显式假设）
    levels = [max(0, c["ukeire"]) for c in chain] or [0]
    start_shanten = chain[0]["shanten"] if chain else 8
    if chain and chain[-1]["shanten"] > 0:
        levels.extend([max(0, chain[-1]["ukeire"])] * chain[-1]["shanten"])
    if start_shanten < 0:
        return {"win": [1.0] * rounds, "tenpai": [1.0] * rounds,
                "turn_prob": [0.0] * rounds, "rounds": rounds}

    # 状态分布：state[i] = 处于第 i 级的概率（i == len(levels)-1 表示已听牌）
    n_levels = len(levels)
    state = [0.0] * n_levels
    state[0] = 1.0
    cum_win = 0.0
    cum_tenpai = 0.0

    for r in range(1, rounds + 1):
        remaining = wall - (r - 1) * draws_per_round
        if remaining <= 0:
            win_cum.append(cum_win)
            tenpai_cum.append(cum_tenpai)
            turn_prob.append(0.0)
            continue

        new_state = [0.0] * n_levels
        p_win_now = 0.0
        for lv in range(n_levels):
            p_here = state[lv]
            if p_here <= 0.0:
                continue
            k = levels[lv]
            if k <= 0:
                new_state[lv] += p_here
                continue
            # 密度模型：命中率 = 有效牌数 / 还没看见的牌数
            p_hit = min(1.0, k / float(denom)) if denom > 0 else 0.0
            if lv == n_levels - 1:
                # 已经听牌：命中就和牌
                p_win_now += p_here * p_hit
                new_state[lv] += p_here * (1.0 - p_hit)
            else:
                new_state[lv] += p_here * (1.0 - p_hit)
                new_state[lv + 1] += p_here * p_hit
        state = new_state

        cum_win += p_win_now
        cum_tenpai = 1.0 - state[0] if n_levels > 1 else 1.0
        win_cum.append(min(1.0, cum_win))
        tenpai_cum.append(min(1.0, max(cum_tenpai, cum_win)))
        turn_prob.append(p_win_now)

    return {
        "win": win_cum,
        "tenpai": tenpai_cum,
        "turn_prob": turn_prob,
        "rounds": rounds,
    }


def tenpai_probability_curve(chain, wall, rounds=None, draws_per_round=DRAWS_PER_ROUND,
                             unseen=None):
    curve = win_probability_curve(chain, wall, rounds, draws_per_round, unseen)
    return curve["tenpai"]


def draw_game_probability(win_prob):
    """流局概率 = 1 - 和牌概率（忽略途中流局等特殊结束）。"""
    return max(0.0, 1.0 - win_prob)


# ---------------------------------------------------------------------------
#  巡目强度 / 价值（一阶动力学，模型）
# ---------------------------------------------------------------------------

def turn_win_rate(turn, h0=0.35, lam=0.06):
    """瞬时和牌强度 h(t) = h0 * exp(-λt)。

    λ 越大衰减越快；这是经验曲线，不是从牌理推出来的。
    """
    return h0 * math.exp(-lam * max(0, turn))


def expr_decay_win_curve(rounds, lam=0.08, h0=1.0):
    """一阶动力学 dp/dt = -λp 的累积解 p(t) = h0 * (1 - exp(-λt))。"""
    return [h0 * (1.0 - math.exp(-lam * t)) for t in range(1, rounds + 1)]


def turn_value(turn, decay=0.90):
    """随巡目指数衰减的局面价值。"""
    return decay ** max(0, turn)


def integral_ev(rate_fn, rounds, discount=0.9):
    """全巡目期望收益的离散积分 sum_t rate(t) * discount^t。

    对应"期望值积分方程"：把每巡的瞬时收益按时间折现后累加。
    """
    total = 0.0
    for t in range(1, int(rounds) + 1):
        total += rate_fn(t) * (discount ** t)
    return total


# ---------------------------------------------------------------------------
#  偶然役 / 宝牌（经验参数，可调）
# ---------------------------------------------------------------------------

def ippatsu_probability(base_win_rate, window=0.25):
    """立直后一巡内和牌的条件概率（国标无立直，留给日麻扩展用）。"""
    return base_win_rate * window


def haitei_probability(turn, total_turns=18):
    """海底摸月：只在最后一巡成立。"""
    if turn >= total_turns:
        return 1.0 / max(1, total_turns)
    return 0.0


def rinshan_probability(kan_count=0, base=0.08, per_kan=0.5):
    """岭上开花概率的粗估：每多一个杠，概率按比例上升。"""
    return min(1.0, base * (1.0 + kan_count * per_kan))


def chankan_probability(opponent_kan_rate=0.03, tenpai_rate=0.4, match_rate=0.5):
    """抢杠：对手加杠 × 对手听牌 × 杠牌正好是你待牌。"""
    return opponent_kan_rate * tenpai_rate * match_rate


def dora_expectation(dora_count=0, avg_dora=0.3):
    """宝牌期望番数。"""
    return dora_count + avg_dora


def ura_dora_expectation(riichi=True, avg_ura=0.4):
    """里宝牌期望番数（仅立直有效）。"""
    return avg_ura if riichi else 0.0


# ---------------------------------------------------------------------------
#  一站式：从手牌算出整条概率曲线
# ---------------------------------------------------------------------------

def unseen_total(counts, visible=None, open_melds=0):
    """全场还没看到的牌数（有效牌数的分母）。"""
    seen = list(visible) if visible else [0] * NUM_TILE_TYPES
    total = 0
    for t in range(NUM_TILE_TYPES):
        left = 4 - counts[t] - seen[t]
        if left > 0:
            total += left
    return total


def analyse_probability(counts, open_melds=0, visible=None, wall=70,
                        rounds=None, draws_per_round=DRAWS_PER_ROUND,
                        allow_chiitoi=True, allow_kokushi=True):
    chain = advance_chain(counts, open_melds, visible, max_levels=14,
                          allow_chiitoi=allow_chiitoi, allow_kokushi=allow_kokushi)
    unseen = unseen_total(counts, visible, open_melds)
    curve = win_probability_curve(chain, wall, rounds, draws_per_round, unseen)
    return {
        "unseen": unseen,
        "chain": [
            {"level": c["level"], "shanten": c["shanten"], "ukeire": c["ukeire"]}
            for c in chain
        ],
        "curve": curve,
        "expected_draws": expected_draws(wall, chain[0]["ukeire"]) if chain else float("inf"),
        "draw_probability": draw_game_probability(curve["win"][-1] if curve["win"] else 0.0),
    }
