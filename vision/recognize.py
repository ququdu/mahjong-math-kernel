# -*- coding: utf-8 -*-
"""截图 -> 牌面 -> 内核请求。

识别只做三件事：按版面切格子、逐格比模板、把结果拼成牌。

拼成请求的那一步单独放（``to_request``），因为它要调用内核的牌表示；
这样"识别"本身还是纯粹的图像 + 小整数，方便单独替换成别的识别器
（比如以后接 OCR 或神经网络）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

from .image import split_row
from .match import Matcher
from .pack import TILE_NAMES, Layout, TemplatePack


def _region_cells(arr, region):
    from .pack import Region

    reg = region if isinstance(region, Region) else Region.from_dict(region)
    return split_row(arr, reg.to_dict(), count=reg.count)


def infer_meld(tiles: Sequence[int]) -> Optional[Dict]:
    """从牌面反推副露类型。

    * 4 张相同 -> 杠（光看图分不出明杠/暗杠，默认按明杠）
    * 3 张相同 -> 碰
    * 3 张连号同花色 -> 吃
    """
    tiles = list(tiles)
    if len(tiles) == 4 and len(set(tiles)) == 1:
        return {"kind": "minkan", "tile": tiles[0], "guessed": True}
    if len(tiles) == 3 and len(set(tiles)) == 1:
        return {"kind": "pon", "tile": tiles[0], "guessed": True}
    if len(tiles) == 3 and len(set(tiles)) == 3:
        s = sorted(tiles)
        if s[0] < 27 and s[0] // 9 == s[2] // 9 and s[2] - s[0] == 2:
            return {"kind": "chi", "tile": s[0], "guessed": True}
    return None


def recognize(arr, pack: TemplatePack, layout: Layout,
              min_score: float = 0.35, blank_score: float = 0.55,
              expect_hand: Optional[int] = None) -> Dict:
    """识别一张截图。

    返回::

        {
          "ok": bool,
          "tiles": [int, ...],          # 手牌索引
          "melds": [{kind, tile}...],
          "detail": {"hand": [...], "melds": [[...]]},
          "warnings": [...],
          "confidence": float,          # 最低格分数（越低越不确定）
        }
    """
    if layout.hand is None:
        raise ValueError("版面里没有手牌区：先标定一次（见 vision/calibrate.py）")

    matcher = pack.matcher()
    warnings: List[str] = []

    hand_cells = _region_cells(arr, layout.hand)
    tiles, hand_detail = matcher.classify_blank_aware(
        hand_cells, blank_score=blank_score, min_score=min_score)

    bad = [(d["best"], d["score"]) for d in hand_detail if d["tile"] is not None
           and not d["ok"]]
    for best, score in bad:
        warnings.append("手牌有一格不太确定：最像 %s（%.2f）" % (TILE_NAMES[best], score))

    if expect_hand is not None and len(tiles) != expect_hand:
        warnings.append("识别出手牌 %d 张，预期 %d 张" % (len(tiles), expect_hand))

    melds = []
    meld_detail = []
    for i, region in enumerate(layout.melds):
        cells = _region_cells(arr, region)
        mt, md = matcher.classify_blank_aware(cells, blank_score=blank_score,
                                              min_score=min_score)
        meld_detail.append(md)
        parsed = infer_meld(mt)
        if parsed is None:
            if mt:
                warnings.append("副露 #%d 看不出是什么牌型：%s" % (
                    i + 1, " ".join(TILE_NAMES[t] for t in mt)))
        else:
            melds.append(parsed)

    confidences = [d["score"] for d in hand_detail if d["tile"] is not None]
    confidence = min(confidences) if confidences else 0.0

    return {
        "ok": len(tiles) > 0,
        "tiles": tiles,
        "melds": melds,
        "detail": {"hand": hand_detail, "melds": meld_detail},
        "warnings": warnings,
        "confidence": round(confidence, 4),
    }


def to_request(result: Dict, ruleset: str = "gb", turn: int = 1, **extra) -> Dict:
    """把识别结果转成引擎请求（这一步才需要内核的牌表示）。"""
    from mahjong_kernel.tiles import counts_to_str, to_counts

    counts = to_counts(result["tiles"])
    req = {
        "ruleset": ruleset,
        "hand": counts_to_str(counts),
        "tiles": list(result["tiles"]),
        "melds": [{"kind": m["kind"], "tile": m["tile"]} for m in result.get("melds") or []],
        "turn": turn,
    }
    for k, v in (extra or {}).items():
        if v is not None:
            req[k] = v
    return req
