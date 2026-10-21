# -*- coding: utf-8 -*-
"""算分统一入口：把 ``BoardState`` 变成 ``ScoreContext``，再交给规则集。"""

from __future__ import annotations

from typing import Optional

from .hand import BoardState
from .rulesets import ScoreContext, ScoreResult, get_ruleset
from .tiles import NUM_TILE_TYPES


def build_context(state: BoardState, win_tile=None) -> ScoreContext:
    counts = state.counts

    if win_tile is None:
        win_tile = state.agari_tile
    if win_tile is None:
        # 没有指定和牌张时不猜，交给调用方；番种里与和牌张相关的会退化
        win_tile = -1

    visible = state.visible_counts() if state.visible else [0] * NUM_TILE_TYPES

    return ScoreContext(
        counts=counts,
        melds=list(state.melds),
        win_tile=int(win_tile),
        is_tsumo=state.is_tsumo,
        seat_wind=state.seat_wind,
        round_wind=state.round_wind,
        is_dealer=state.is_dealer,
        visible=visible,
        flowers=state.flowers,
        is_last_tile=bool(state.flags.get("is_last_tile")),
        is_after_kan=bool(state.flags.get("is_after_kan")),
        is_chankan=bool(state.flags.get("is_chankan")),
        deficiency_suit=state.deficiency_suit,
    )


def score_state(state: BoardState, ruleset=None) -> ScoreResult:
    rs = get_ruleset(ruleset or state.ruleset)
    ctx = build_context(state)
    total = sum(ctx.counts) + 3 * len(ctx.melds)
    if total % 3 != 2:
        return ScoreResult(
            ok=False, ruleset=rs.key,
            notes=["手牌张数不对：%d 张暗牌 + %d 副露，凑不成 3n+2"
                   % (sum(ctx.counts), len(ctx.melds))],
        )
    return rs.score(ctx)


def explain_score(state: BoardState, ruleset=None) -> dict:
    rs = get_ruleset(ruleset or state.ruleset)
    ctx = build_context(state)
    result = rs.score(ctx)
    return result.to_dict()
