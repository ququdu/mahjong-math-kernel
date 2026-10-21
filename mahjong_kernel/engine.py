# -*- coding: utf-8 -*-
"""内核门面：一个类把全部能力包成 JSON。

对外只有这一层：

    engine = Engine()
    engine.analyze({...})     # 一屏报告
    engine.score({...})       # 只算番/点
    engine.discard({...})     # 只算弃牌
    engine.probability({...}) # 只算概率
    engine.ev({...})          # 只算期望值

输入输出都是普通 dict，界面、CLI、HTTP、截图识别都走这里，
所以"换一个前端"不需要碰内核一行代码。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import __version__
from .ev import attack_defense_judge, expected_value, placement_ev
from .hand import BoardState
from .meld import Meld
from .probability import (
    advance_chain, analyse_probability, draw_game_probability,
    expected_draws, unseen_total, win_probability_curve,
)
from .rulesets import get_ruleset, list_rulesets, register_custom
from .safety import DEFAULT_MODEL, DangerModel, defense_efficiency, safest_discard
from .score import build_context, score_state
from .shanten import shanten
from .strategy import analyse_discards, estimate_win_points, judge
from .tiles import NUM_TILE_TYPES, TILE_NAMES, TILE_NAMES_CN, counts_to_str
from .ukeire import effective_tiles, ukeire_total


def _tile_map(tiles: Dict[int, int]) -> Dict[str, int]:
    return {TILE_NAMES[t]: v for t, v in sorted(tiles.items())}


def _label(tile):
    return {"index": tile, "name": TILE_NAMES[tile], "cn": TILE_NAMES_CN[tile]}


class Engine:
    """麻将计算内核。线程安全（除规则注册外无状态）。"""

    def __init__(self, ruleset: str = "gb", danger_model: Optional[DangerModel] = None):
        self.default_ruleset = ruleset
        self.danger_model = danger_model or DEFAULT_MODEL

    # -- 内部 -----------------------------------------------------------

    def _state(self, request: Dict[str, Any]) -> BoardState:
        data = dict(request or {})
        data.setdefault("ruleset", self.default_ruleset)
        if isinstance(data.get("melds"), list):
            data["melds"] = [
                m if isinstance(m, Meld) else m for m in data["melds"]
            ]
        return BoardState.from_dict(data)

    def _validate(self, state: BoardState):
        warnings = []
        total = state.total_size
        if total % 3 not in (1, 2):
            warnings.append("牌数 %d 不合法（应是 3n+1 或 3n+2）" % total)
        counts = state.counts
        for t in range(NUM_TILE_TYPES):
            if counts[t] > 4:
                warnings.append("%s 手里有 %d 张，超过 4 张" % (TILE_NAMES[t], counts[t]))
        for t in state.melds:
            if t.tile < 0 or t.tile >= NUM_TILE_TYPES:
                warnings.append("副露牌索引越界: %d" % t.tile)
        rs = get_ruleset(state.ruleset)
        if not rs.has_honors and any(counts[i] for i in range(27, 34)):
            warnings.append("%s 没有字牌" % rs.name)
        return warnings

    # -- 分析 -----------------------------------------------------------

    def analyze(self, request: Dict[str, Any], lite: bool = False) -> Dict[str, Any]:
        """一屏报告：向听 / 听牌 / 进张 / 概率 / 番点 / 弃牌建议 / 攻守。

        ``lite=True`` 跳过逐张弃牌分析（那一步占了冷启动八成时间）。
        实时模式先用它出结论，再补完整排序。
        """
        state = self._state(request)
        rs = get_ruleset(state.ruleset)
        warnings = self._validate(state)

        counts = state.counts
        total = state.total_size
        visible = state.visible_counts()
        wall = state.wall_size()
        unseen = unseen_total(counts, visible, len(state.melds))

        s = shanten(counts, len(state.melds),
                    allow_chiitoi=not state.melds,
                    allow_kokushi=not state.melds and rs.has_honors)

        report: Dict[str, Any] = {
            "ok": True,
            "version": __version__,
            "ruleset": rs.to_dict(),
            "state": state.to_dict(),
            "hand": counts_to_str(counts),
            "hand_cn": " ".join(TILE_NAMES_CN[t] for t in state.tiles),
            "melds": [{"kind": m.kind, "tile": m.tile, "name": TILE_NAMES[m.tile]}
                      for m in state.melds],
            "shanten": s,
            "is_tenpai": s == 0,
            "is_agari": s < 0,
            "wall": wall,
            "unseen": unseen,
            "warnings": warnings,
            "waits": {},
            "ukeire": 0,
            "efficiency": 0.0,
            "discards": [],
            "advice": None,
            "safety": None,
            "probability": None,
            "score": None,
        }

        # --- 形状上和了：先算分；如果规则上不能和（定缺、番不足…）继续按普通手牌分析 ---
        if s < 0 and total % 3 == 2:
            result = score_state(state, rs)
            report["score"] = result.to_dict()
            if result.ok:
                return report
            report["is_agari"] = False
            report["agari_blocked"] = True
            warnings.extend(result.notes)

        # --- 弃牌分析（14 张）---
        work_counts = list(counts)
        if total % 3 == 2 and not lite:
            options = analyse_discards(state, rs, model=self.danger_model)
            report["discards"] = [o.to_dict() for o in options]
            if options:
                best = options[0]
                report["advice"] = judge(state, best, rs)
                work_counts = list(counts)
                work_counts[best.tile] -= 1

        # --- 听牌 / 进张（13 张形）---
        if sum(work_counts) % 3 == 1:
            eff = effective_tiles(work_counts, len(state.melds), visible)
            report["waits"] = _tile_map(eff)
            report["ukeire"] = ukeire_total(eff)
            report["efficiency"] = (report["ukeire"] / unseen) if unseen else 0.0
            report["shanten_after_best"] = shanten(
                work_counts, len(state.melds),
                allow_chiitoi=not state.melds,
                allow_kokushi=not state.melds and rs.has_honors)

        # --- 概率曲线 ---
        chain = advance_chain(work_counts, len(state.melds), visible, max_levels=14)
        curve = win_probability_curve(chain, wall, unseen=unseen)
        report["probability"] = {
            "chain": [{"level": c["level"], "shanten": c["shanten"],
                       "ukeire": c["ukeire"]} for c in chain],
            "rounds": curve["rounds"],
            "win_by_turn": [round(v, 4) for v in curve["win"]],
            "tenpai_by_turn": [round(v, 4) for v in curve["tenpai"]],
            "win_final": round(curve["win"][-1], 4) if curve["win"] else 0.0,
            "tenpai_final": round(curve["tenpai"][-1], 4) if curve["tenpai"] else 0.0,
            "draw_probability": round(
                draw_game_probability(curve["win"][-1] if curve["win"] else 0.0), 4),
            "expected_draws": (None if not chain or chain[0]["ukeire"] <= 0
                               else round(expected_draws(unseen, chain[0]["ukeire"]), 2)),
            "unseen": unseen,
        }

        # --- 守备 ---
        if total % 3 == 2:
            report["safety"] = {
                "defense_efficiency": round(
                    defense_efficiency(counts, self.danger_model, turn=state.turn), 4),
                "safest_discard": (
                    None if (t := safest_discard(counts, self.danger_model,
                                                 visible=visible, turn=state.turn)) is None
                    else _label(t)),
            }

        # --- 立直/和牌期望（若有）---
        return report

    # -- 只算分 ---------------------------------------------------------

    def score(self, request: Dict[str, Any]) -> Dict[str, Any]:
        state = self._state(request)
        rs = get_ruleset(state.ruleset)
        result = score_state(state, rs)
        out = result.to_dict()
        out["version"] = __version__
        return out

    # -- 只算弃牌 -------------------------------------------------------

    def discard(self, request: Dict[str, Any]) -> Dict[str, Any]:
        state = self._state(request)
        rs = get_ruleset(state.ruleset)
        options = analyse_discards(state, rs, model=self.danger_model)
        return {
            "ok": True,
            "version": __version__,
            "ruleset": rs.key,
            "hand": counts_to_str(state.counts),
            "discards": [o.to_dict() for o in options],
            "advice": judge(state, options[0] if options else None, rs),
        }

    # -- 只算概率 -------------------------------------------------------

    def probability(self, request: Dict[str, Any]) -> Dict[str, Any]:
        state = self._state(request)
        rs = get_ruleset(state.ruleset)
        visible = state.visible_counts()
        data = analyse_probability(
            state.counts, len(state.melds), visible,
            wall=state.wall_size(),
            allow_chiitoi=not state.melds,
            allow_kokushi=not state.melds and rs.has_honors,
        )
        return {
            "ok": True,
            "version": __version__,
            "ruleset": rs.key,
            "hand": counts_to_str(state.counts),
            "chain": data["chain"],
            "unseen": data["unseen"],
            "wall": state.wall_size(),
            "win_by_turn": [round(v, 4) for v in data["curve"]["win"]],
            "tenpai_by_turn": [round(v, 4) for v in data["curve"]["tenpai"]],
            "win_final": round(data["curve"]["win"][-1], 4) if data["curve"]["win"] else 0.0,
            "draw_probability": round(data["draw_probability"], 4),
            "expected_draws": (None if data["expected_draws"] == float("inf")
                               else round(data["expected_draws"], 2)),
        }

    # -- 只算期望值 -----------------------------------------------------

    def ev(self, request: Dict[str, Any]) -> Dict[str, Any]:
        state = self._state(request)
        rs = get_ruleset(state.ruleset)
        win_prob = request.get("win_prob")
        deal_prob = request.get("deal_prob")
        win_points = request.get("win_points")
        deal_points = request.get("deal_points")
        threshold = float(request.get("threshold", 1.0))

        if win_prob is None or deal_prob is None:
            # 从手牌推算
            try:
                opts = analyse_discards(state, rs, model=self.danger_model)
            except ValueError:
                opts = []
            if opts:
                best = opts[0]
                win_prob = best.win_prob
                deal_prob = best.deal_prob
                win_points = win_points if win_points is not None else best.win_points
                deal_points = deal_points if deal_points is not None else best.deal_points
        if win_prob is None:
            win_prob = 0.0
        if deal_prob is None:
            deal_prob = 0.0
        if win_points is None:
            win_points = float(rs.default_win_points)
        if deal_points is None:
            deal_points = float(rs.default_deal_points)

        decision = attack_defense_judge(win_prob, win_points, deal_prob,
                                        deal_points, threshold)
        out = {
            "ok": True,
            "version": __version__,
            "ruleset": rs.key,
            "ev": round(expected_value(win_prob, win_points, deal_prob, deal_points), 3),
            "win_prob": round(win_prob, 4),
            "deal_prob": round(deal_prob, 4),
            "win_points": round(win_points, 2),
            "deal_points": round(deal_points, 2),
            "attack": round(decision.attack, 3),
            "defense": round(decision.defense, 3),
            "ratio": (None if decision.ratio == float("inf")
                      else round(decision.ratio, 3)),
            "should_push": decision.should_push,
            "reason": decision.reason,
        }

        scores = request.get("scores")
        if scores and len(scores) > 1:
            hero = int(request.get("hero", 0))
            probs = None
            try:
                from .ev import placement_probabilities
                probs = placement_probabilities(scores, samples=1200)
            except Exception:
                probs = None
            out["placement"] = {
                "expected_ev": round(placement_ev(scores, hero, samples=1200), 4),
                "probabilities": (None if probs is None else
                                  [{"place": {str(k): round(v, 3) for k, v in p["place"].items()},
                                    "expected_place": round(p["expected_place"], 3)}
                                   for p in probs]),
            }
        return out

    # -- 规则表 ---------------------------------------------------------

    def rulesets(self) -> Dict[str, Any]:
        return {"ok": True, "version": __version__, "rulesets": list_rulesets()}

    def register_custom(self, config) -> Dict[str, Any]:
        rs = register_custom(config)
        return {"ok": True, "ruleset": rs.to_dict()}
