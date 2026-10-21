# -*- coding: utf-8 -*-
"""蒙特卡洛仿真——用来交叉验证 ``probability.py`` 里的链式模型。

两个层次的仿真：

``simulate_chain``  在"进张链"上跑仿真。快（纯抽牌 + 集合判断），
                    用来验证逐巡 DP 的实现没写错。

``simulate_hand``   用真实引擎跑仿真：每巡真的去摸牌、真的算向听、
                    真的挑弃牌。慢 10~100 倍，但它是"另一个方法算同一件事"，
                    和解析解对得上才说明模型可信。
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from .shanten import shanten
from .tiles import NUM_TILE_TYPES, Z_START
from .ukeire import effective_tiles, ukeire_total

DRAWS_PER_ROUND = 4


def _wall_tiles(counts, visible):
    """按剩余张数构造牌山（每个元素一张牌）。"""
    wall = []
    for t in range(NUM_TILE_TYPES):
        left = 4 - counts[t] - visible[t]
        if left > 0:
            wall.extend([t] * left)
    return wall


# ---------------------------------------------------------------------------
#  链模型仿真（快）
# ---------------------------------------------------------------------------

def simulate_chain(chain, wall, rounds=None, trials=2000, seed=None,
                   draws_per_round=DRAWS_PER_ROUND, unseen=None):
    """在进张链上抽样，返回 (和牌率, 听牌率)。"""
    if not chain:
        return 0.0, 0.0
    rng = random.Random(seed)
    if rounds is None:
        rounds = max(1, wall // draws_per_round)
    denom = float(unseen if unseen else wall) or 1.0

    levels = [max(0, c["ukeire"]) for c in chain]
    n_levels = len(levels)
    wins = 0
    tenpais = 0

    for _ in range(trials):
        lv = 0
        won = False
        for r in range(1, rounds + 1):
            remaining = wall - (r - 1) * draws_per_round
            if remaining <= 0:
                break
            k = levels[lv]
            if k <= 0:
                continue
            hit = rng.random() < (k / denom)
            if not hit:
                continue
            if lv == n_levels - 1:
                won = True
                break
            lv += 1
        if won:
            wins += 1
        if lv >= n_levels - 1:
            tenpais += 1
    return wins / trials, tenpais / trials


# ---------------------------------------------------------------------------
#  真实引擎仿真（慢但独立）
# ---------------------------------------------------------------------------

def simulate_hand(counts, open_melds=0, visible=None, wall=70, rounds=None,
                  trials=30, seed=None, draws_per_round=DRAWS_PER_ROUND,
                  allow_chiitoi=True, allow_kokushi=True, policy="fast"):
    """用真实向听引擎跑仿真（独立于解析模型的第二条路）。

    每轮：从牌山抽一张 → 向听下降就留下并弃牌，否则直接打掉。
    对手不做建模（只消耗牌山张数）。

    ``policy``：

    * ``"fast"``（默认）弃牌看"连接度"这个便宜代理，跑得快，但比最优打差，
      所以结果会系统性低于解析解；
    * ``"ukeire"`` 弃牌时真的算进张取最大，慢 10~20 倍，但接近最优打法。

    两条路的差距就是"打牌策略的代价"，不是模型算错。
    返回 ``{"win_rate", "tenpai_rate", "avg_win_turn", "trials", "policy"}``。
    """
    counts0 = list(counts)
    if visible is None:
        visible = [0] * NUM_TILE_TYPES
    visible = list(visible)
    rng = random.Random(seed)
    if rounds is None:
        rounds = max(1, wall // draws_per_round)

    wins = 0
    tenpais = 0
    win_turns = []

    def sh(c):
        return shanten(c, open_melds, allow_chiitoi, allow_kokushi)

    def drop(c):
        if policy == "ukeire":
            _drop_best_ukeire(c, sh, open_melds, visible)
        else:
            _drop_isolated(c, sh)

    for _ in range(trials):
        hand = list(counts0)
        pool = _wall_tiles(hand, visible)
        rng.shuffle(pool)
        won = False
        for r in range(1, rounds + 1):
            # 别人先摸 3 张（只影响牌山）
            for _ in range(draws_per_round - 1):
                if pool:
                    pool.pop()
            if not pool:
                break
            t = pool.pop()
            hand[t] += 1
            if sh(hand) < 0:
                won = True
                win_turns.append(r)
                break
            drop(hand)
        if won:
            wins += 1
        elif sh(hand) == 0:
            tenpais += 1

    return {
        "win_rate": wins / trials,
        "tenpai_rate": tenpais / trials,
        "avg_win_turn": (sum(win_turns) / len(win_turns)) if win_turns else None,
        "trials": trials,
        "policy": policy,
    }


def _connectivity(hand):
    """手牌连接度：相邻牌越多越"有结构"。用来替代真正的进张计算（便宜）。"""
    score = 0
    for i in range(NUM_TILE_TYPES):
        c = hand[i]
        if c == 0 or i >= Z_START:
            continue
        pos = i % 9
        if pos > 0:
            score += c * hand[i - 1]
        if pos < 8:
            score += c * hand[i + 1]
        if pos < 7:
            score += c * hand[i + 2]
        if pos > 1:
            score += c * hand[i - 2]
    return score


def _drop_isolated(hand, sh):
    """从 14 张里丢一张：先保证向听最小，再保留连接度最高的形状。

    注意：这里用的是"连接度"这个便宜代理，不是真正的最优进张。
    所以 ``simulate_hand`` 的结果会系统性低于解析解——差距就是
    "随手打的代价"，不是模型算错了。
    """
    best = None
    for t in range(NUM_TILE_TYPES):
        if hand[t] == 0:
            continue
        hand[t] -= 1
        s = sh(hand)
        conn = _connectivity(hand)
        hand[t] += 1
        cand = (s, -conn, -t)
        if best is None or cand < best[0]:
            best = (cand, t)
    if best is not None:
        hand[best[1]] -= 1


def _drop_best_ukeire(hand, sh, open_melds=0, visible=None):
    """弃牌时真的比进张（慢，但接近最优打法）。"""
    best = None
    for t in range(NUM_TILE_TYPES):
        if hand[t] == 0:
            continue
        hand[t] -= 1
        s = sh(hand)
        u = ukeire_total(effective_tiles(hand, open_melds, visible))
        hand[t] += 1
        cand = (s, -u, -t)
        if best is None or cand < best[0]:
            best = (cand, t)
    if best is not None:
        hand[best[1]] -= 1
