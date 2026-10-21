# -*- coding: utf-8 -*-
"""概率模型 / 蒙特卡洛 / 期望值 / 安全度 / 选牌决策 的回归测试。"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from mahjong_kernel import probability as P
from mahjong_kernel import safety
from mahjong_kernel.ev import (
    attack_defense_judge, equilibrium_check, expected_value, placement_ev,
    placement_probabilities,
)
from mahjong_kernel.hand import BoardState
from mahjong_kernel.simulate import simulate_chain, simulate_hand
from mahjong_kernel.strategy import analyse_discards, judge
from mahjong_kernel.tiles import counts_to_str, parse_tiles, to_counts


def random_hand13(seed):
    rnd = random.Random(seed)
    pool = []
    for t in range(34):
        pool.extend([t] * 4)
    rnd.shuffle(pool)
    return to_counts(sorted(pool[:13]))


# ---------------------------------------------------------------------------
#  超几何分布（精确）
# ---------------------------------------------------------------------------

def test_hypergeometric_matches_bruteforce():
    # 15 张牌里 4 张是"有效牌"，摸 3 张
    total, hits, draws = 15, 4, 3
    brute = 0
    universe = [1] * hits + [0] * (total - hits)
    rnd = random.Random(1)
    samples = 20000
    for _ in range(samples):
        pick = rnd.sample(range(total), draws)
        if any(universe[i] for i in pick):
            brute += 1
    est = brute / samples
    exact = P.hypergeometric_at_least_one(total, hits, draws)
    assert abs(est - exact) < 0.05
    assert abs(exact - (1 - math.comb(total - hits, draws) / math.comb(total, draws))) < 1e-12


def test_hypergeometric_edges():
    assert P.hypergeometric_at_least_one(10, 0, 3) == 0.0
    assert P.hypergeometric_at_least_one(10, 3, 0) == 0.0
    assert P.hypergeometric_at_least_one(10, 10, 1) == 1.0
    assert P.hypergeometric_at_least_one(10, 3, 100) == 1.0


def test_hypergeometric_monotone():
    prev = -1.0
    for k in range(1, 12):
        v = P.hypergeometric_at_least_one(40, k, 5)
        assert v > prev
        prev = v


def test_hypergeometric_pmf_sums_to_one():
    total, hits, draws = 20, 5, 4
    s = sum(P.hypergeometric_pmf(total, hits, draws, k) for k in range(0, hits + 1))
    assert abs(s - 1.0) < 1e-9


def test_expected_draws():
    assert P.expected_draws(70, 7) == 10.0
    assert P.expected_draws(70, 0) == float("inf")
    assert abs(P.hypergeometric_mean(70, 7, 3) - 0.3) < 1e-9


# ---------------------------------------------------------------------------
#  进张链 / 逐巡曲线
# ---------------------------------------------------------------------------

def test_advance_chain_reaches_tenpai():
    counts = random_hand13(11)
    chain = P.advance_chain(counts, max_levels=14)
    assert chain
    assert chain[-1]["shanten"] == 0, "链条没推到听牌: %s" % [
        (c["shanten"], c["ukeire"]) for c in chain]


def test_curve_monotone_and_bounded():
    counts = random_hand13(12)
    chain = P.advance_chain(counts, max_levels=14)
    curve = P.win_probability_curve(chain, wall=70, rounds=18,
                                    unseen=P.unseen_total(counts))
    win = curve["win"]
    assert all(0.0 <= v <= 1.0 for v in win)
    assert all(win[i] <= win[i + 1] + 1e-12 for i in range(len(win) - 1))
    tenpai = curve["tenpai"]
    assert all(tenpai[i] >= win[i] - 1e-9 for i in range(len(win)))


def test_more_ukeire_means_higher_win_probability():
    chain_a = [{"shanten": 0, "ukeire": 4}]
    chain_b = [{"shanten": 0, "ukeire": 12}]
    a = P.win_probability_curve(chain_a, 70, 18, unseen=100)["win"][-1]
    b = P.win_probability_curve(chain_b, 70, 18, unseen=100)["win"][-1]
    assert b > a


def test_unseen_total():
    counts = to_counts(parse_tiles("123m456p789s11z22z"))
    # 13 张在手，剩 136-13 = 123 张没看见
    assert P.unseen_total(counts) == 123
    visible = to_counts(parse_tiles("1z1z"))
    assert P.unseen_total(counts, visible) == 121


def test_analytic_matches_chain_monte_carlo():
    """解析 DP 和链式蒙特卡洛必须对得上（两者算同一件事）。"""
    for seed in (1, 2, 3):
        counts = random_hand13(seed)
        chain = P.advance_chain(counts, max_levels=9)
        if not chain or chain[0]["shanten"] < 0:
            continue
        unseen = P.unseen_total(counts)
        curve = P.win_probability_curve(chain, wall=70, rounds=18, unseen=unseen)
        levels = [max(0, c["ukeire"]) for c in chain]
        if chain[-1]["shanten"] > 0:
            levels.extend([max(0, chain[-1]["ukeire"])] * chain[-1]["shanten"])
        mc, _ = simulate_chain([{"ukeire": v} for v in levels], 70, rounds=18,
                               trials=4000, seed=99, unseen=unseen)
        assert abs(curve["win"][-1] - mc) < 0.03, (
            counts_to_str(counts), curve["win"][-1], mc)


def test_simulate_hand_runs():
    counts = random_hand13(21)
    r = simulate_hand(counts, wall=70, rounds=10, trials=3, seed=1)
    assert 0.0 <= r["win_rate"] <= 1.0
    assert r["policy"] == "fast"


def test_draw_probability_complements_win():
    assert abs(P.draw_game_probability(0.3) - 0.7) < 1e-12
    assert P.draw_game_probability(1.2) == 0.0


def test_turn_value_and_decay():
    assert P.turn_value(0) == 1.0
    assert P.turn_value(10) < P.turn_value(5)
    curve = P.expr_decay_win_curve(10, lam=0.1)
    assert len(curve) == 10
    assert all(0 < v < 1 for v in curve)
    assert all(curve[i] < curve[i + 1] for i in range(9))


def test_event_probabilities_sane():
    assert 0.0 <= P.rinshan_probability(0) <= 1.0
    assert P.rinshan_probability(2) > P.rinshan_probability(0)
    assert 0.0 <= P.chankan_probability() <= 1.0
    assert P.haitei_probability(17) == 0.0
    assert P.haitei_probability(18) > 0.0


# ---------------------------------------------------------------------------
#  期望值
# ---------------------------------------------------------------------------

def test_expected_value_formula():
    ev = expected_value(0.3, 100.0, 0.1, 200.0)
    assert abs(ev - (0.3 * 100 - 0.1 * 200)) < 1e-12
    ev2 = expected_value(0.3, 100.0, 0.1, 200.0, draw_prob=0.6, draw_value=10.0)
    assert abs(ev2 - (0.3 * 100 - 0.1 * 200 + 0.6 * 10)) < 1e-12


def test_attack_defense_judge():
    d = attack_defense_judge(0.4, 100.0, 0.05, 100.0, threshold=1.0)
    assert d.should_push and d.ratio == pytest.approx(8.0)
    d2 = attack_defense_judge(0.02, 100.0, 0.4, 100.0, threshold=1.0)
    assert not d2.should_push


def test_equilibrium():
    r = equilibrium_check(0.2, 100.0, 0.05, 200.0)
    assert r["limit"] == pytest.approx(0.5)
    assert r["balanced"] is True       # 0.05/0.2 = 0.25 <= 0.5
    r2 = equilibrium_check(0.2, 100.0, 0.2, 100.0)
    assert r2["balanced"] is True      # 恰好等于均衡点
    r3 = equilibrium_check(0.2, 100.0, 0.3, 100.0)
    assert r3["balanced"] is False


def test_placement_probabilities_sum_to_one():
    probs = placement_probabilities([25000, 25000, 25000, 25000], samples=800)
    for p in probs:
        assert abs(sum(p["place"].values()) - 1.0) < 1e-9
        assert abs(p["expected_place"] - 2.5) < 0.25


def test_placement_ev_ranks_better_score_higher():
    strong = placement_ev([50000, 20000, 15000, 15000], hero=0, samples=800)
    weak = placement_ev([15000, 20000, 15000, 50000], hero=0, samples=800)
    assert strong > weak


# ---------------------------------------------------------------------------
#  安全度
# ---------------------------------------------------------------------------

def test_danger_bounds_and_wall():
    model = safety.DangerModel()
    hand = to_counts(parse_tiles("1234m567p89s1z"))
    for t in range(34):
        d = model.tile_danger(t, hand=hand, turn=5)
        assert 0.0 <= d <= 1.0
    # 四张都露在场上 -> 绝对安全
    visible = [0] * 34
    visible[4] = 4
    assert model.tile_danger(4, visible=visible, turn=10) == 0.0


def test_danger_ordering():
    model = safety.DangerModel()
    honor = model.tile_danger(27, turn=5)          # 东
    terminal = model.tile_danger(0, turn=5)        # 1m
    middle = model.tile_danger(4, turn=5)          # 5m
    assert middle > terminal > honor


def test_danger_grows_late():
    model = safety.DangerModel()
    early = model.tile_danger(4, turn=2)
    late = model.tile_danger(4, turn=15)
    assert late > early


def test_defense_efficiency():
    hand = to_counts(parse_tiles("1m9m1p9p1s9s1z2z3z4z5z6z7z"))
    eff = safety.defense_efficiency(hand, turn=8)
    assert 0.0 <= eff <= 1.0
    # 全是幺九字牌，安全牌比例应当很高
    assert eff > 0.5


def test_furiten_judge():
    waits = {0, 3}
    assert safety.is_furiten(waits, [0]) is True
    assert safety.is_furiten(waits, [5]) is False


# ---------------------------------------------------------------------------
#  选牌决策
# ---------------------------------------------------------------------------

def test_analyse_discards_requires_full_hand():
    st = BoardState.from_dict({"hand": "123m456p789s11z22z", "ruleset": "gb"})
    with pytest.raises(ValueError):
        analyse_discards(st)


def test_analyse_discards_orders_by_ev():
    st = BoardState.from_dict({
        "hand": "123m456p789s11z234m", "ruleset": "gb",
        "turn": 5, "wall_remaining": 60,
    })
    opts = analyse_discards(st)
    assert opts
    evs = [o.ev for o in opts]
    assert evs == sorted(evs, reverse=True)


def test_tenpai_discard_wins_listed():
    st = BoardState.from_dict({
        "hand": "123m456p789s11z234m", "ruleset": "gb",
        "turn": 5, "wall_remaining": 60,
    })
    opts = analyse_discards(st)
    tenpai_opts = [o for o in opts if o.shanten == 0]
    assert tenpai_opts
    # 听牌选项的 win_prob 应当明显高于非听牌选项
    assert max(o.win_prob for o in tenpai_opts) > 0.3


def test_judge_returns_advice():
    st = BoardState.from_dict({
        "hand": "123m456p789s11z234m", "ruleset": "gb",
        "turn": 4, "wall_remaining": 62,
    })
    r = judge(st)
    assert r["advice"] in ("进攻", "可以打，但留意危险牌", "弃和，优先打安全牌")


def test_deficiency_forces_discard():
    st = BoardState.from_dict({
        "hand": "123m456m789m234p55s", "ruleset": "sichuan",
        "deficiency_suit": "s", "turn": 3, "wall_remaining": 70,
    })
    opts = analyse_discards(st)
    assert opts[0].forced is True
    assert opts[0].tile // 9 == 2      # 定缺条子，必须先打条子
