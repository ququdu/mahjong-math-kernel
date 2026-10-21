# -*- coding: utf-8 -*-
"""安全度模型——视频第 21~23 条方程（振听判据 / 危险度 / 守备效率）。

**和中国麻将的现实对齐**：国标、四川、广东都没有日麻那种"振听"规则
（打过的牌别人依然可以和），所以"现物 = 绝对安全"在这里不成立。
真正靠得住的只有一条：**四张都在场上，这张牌不可能在别人手里**。

所以这里的安全度由这几件事决定：

1. 还能剩几张（壁）：剩 0 张 = 绝对安全，剩 1 张明显更安全
2. 牌的本身位置：中张 4~6 最危险，2/8 次之，1/9 与字牌较安全
3. 巡目：越晚对手越可能已经听牌，整体抬升
4. 筋：只给很小的折扣（没有振听兜底，筋的可靠性大打折扣）

全部参数都在 ``DangerModel`` 里，可以按你的桌风改。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from .tiles import (
    HAKU, NUM_TILE_TYPES, Z_START, is_honor, is_yaochu,
)


# 基础危险度：中张最危险，幺九和字牌最安全
def _base_danger(tile):
    if tile >= Z_START:
        return 0.20
    r = tile % 9 + 1
    if r in (1, 9):
        return 0.22
    if r in (2, 8):
        return 0.34
    if r in (3, 7):
        return 0.44
    return 0.55          # 4 5 6


@dataclass
class DangerModel:
    """危险度模型的全部参数（都可调）。"""

    late_turn: int = 6
    late_growth: float = 0.10      # 每多一巡，危险度乘 (1 + growth)
    suji_discount: float = 0.85    # 筋牌折扣（无振听，折扣很小）
    honor_decay: float = 0.75      # 字牌已见越多越安全
    max_danger: float = 1.0

    def remaining(self, tile, visible, hand=None):
        seen = visible[tile] if visible else 0
        mine = hand[tile] if hand else 0
        return max(0, 4 - seen - mine)

    def tile_danger(self, tile, visible=None, hand=None, turn=1,
                    opponent_discards: Optional[Iterable[int]] = None,
                    opponent_riichi_like=False):
        """单张牌对某个对手的危险度，0 表示安全，1 表示最危险。"""
        left = self.remaining(tile, visible, hand)
        if left <= 0:
            return 0.0
        base = _base_danger(tile)

        # 剩余张数：剩 1 张时明显更安全
        base *= {1: 0.55, 2: 0.80, 3: 0.95, 4: 1.0}[left]

        if is_honor(tile):
            seen = (visible[tile] if visible else 0)
            base *= self.honor_decay ** max(0, seen)

        if turn > self.late_turn:
            base *= 1.0 + self.late_growth * (turn - self.late_turn)
        if opponent_riichi_like:
            base *= 1.25

        if opponent_discards and tile < Z_START:
            r = tile % 9 + 1
            # 筋：对手打过 r-3 / r+3 的同花色牌
            suit = tile // 9
            for d in opponent_discards:
                if d >= Z_START or d // 9 != suit:
                    continue
                dr = d % 9 + 1
                if abs(dr - r) == 3:
                    base *= self.suji_discount
                    break

        return min(self.max_danger, max(0.0, base))

    def danger_map(self, visible=None, hand=None, turn=1,
                   opponent_discards=None, opponent_riichi_like=False):
        """整副牌的危险度表 {tile: danger}（只对还能摸到的牌有意义）。"""
        return {
            t: self.tile_danger(t, visible, hand, turn,
                                opponent_discards, opponent_riichi_like)
            for t in range(NUM_TILE_TYPES)
        }


DEFAULT_MODEL = DangerModel()


# ---------------------------------------------------------------------------
#  振听（日麻扩展保留；中国麻将没有这条规则，但有些变体有"过水"限制）
# ---------------------------------------------------------------------------

def is_furiten(waits, own_discards):
    """待牌与自己的弃牌有交集 -> 振听（仅日麻 / 少数变体适用）。"""
    return bool(set(waits) & set(own_discards))


# ---------------------------------------------------------------------------
#  守备效率
# ---------------------------------------------------------------------------

def safe_tiles(hand_counts, model=DEFAULT_MODEL, threshold=0.25, **kw):
    """手牌里"安全牌"的牌种列表。"""
    out = []
    for t in range(NUM_TILE_TYPES):
        if hand_counts[t] <= 0:
            continue
        if model.tile_danger(t, hand=hand_counts, **kw) < threshold:
            out.append(t)
    return out


def defense_efficiency(hand_counts, model=DEFAULT_MODEL, threshold=0.25, **kw):
    """守备效率 = 手牌中安全牌张数 / 手牌总张数。"""
    total = sum(hand_counts)
    if total <= 0:
        return 0.0
    safe = sum(hand_counts[t] for t in safe_tiles(hand_counts, model, threshold, **kw))
    return safe / total


def safest_discard(hand_counts, model=DEFAULT_MODEL, **kw):
    """最安全的弃牌（危险度最低；同分时优先丢只剩 1 张的孤张）。"""
    best = None
    for t in range(NUM_TILE_TYPES):
        if hand_counts[t] <= 0:
            continue
        d = model.tile_danger(t, hand=hand_counts, **kw)
        cand = (d, -hand_counts[t], -t)
        if best is None or cand < best[0]:
            best = (cand, t)
    return best[1] if best else None


# ---------------------------------------------------------------------------
#  放铳期望损失
# ---------------------------------------------------------------------------

def expected_deal_loss(hand_counts, points_per_deal=8.0, model=DEFAULT_MODEL, **kw):
    """打出某张牌的期望失点 = 危险度 × 平均放铳点数。"""
    return {
        t: model.tile_danger(t, hand=hand_counts, **kw) * points_per_deal
        for t in range(NUM_TILE_TYPES)
        if hand_counts[t] > 0
    }
