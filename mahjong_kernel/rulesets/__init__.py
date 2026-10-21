# -*- coding: utf-8 -*-
"""规则集注册表。

加一套新规则只要 ``register(MyRuleSet())``，引擎、API、界面全部自动支持。
"""

from __future__ import annotations

from typing import Dict, List

from .base import FanItem, FanSet, RuleSet, ScoreContext, ScoreResult
from .custom import CustomRuleSet, from_json
from .gb import GBRuleSet, fan_table
from .guangdong import GuangdongRuleSet
from .sichuan import ChangshaRuleSet, SichuanRuleSet

_REGISTRY = {}


def register(ruleset: RuleSet, replace=False):
    key = ruleset.key
    if key in _REGISTRY and not replace:
        raise ValueError("规则 %r 已经注册过了" % key)
    _REGISTRY[key] = ruleset
    return ruleset


def get_ruleset(key=None):
    """按 key 取规则；key 为空时返回默认规则（国标）。传入 RuleSet 实例则原样返回。"""
    if isinstance(key, RuleSet):
        return key
    if key in (None, "", "default"):
        key = "gb"
    rs = _REGISTRY.get(str(key).strip().lower())
    if rs is None:
        raise KeyError(
            "未知规则 %r，可用：%s" % (key, ", ".join(sorted(_REGISTRY)))
        )
    return rs


def list_rulesets() -> List[Dict]:
    return [rs.to_dict() for rs in _REGISTRY.values()]


def register_custom(config) -> RuleSet:
    """注册一套 JSON 自定义规则（dict / JSON 文本 / 文件路径）。"""
    rs = config if isinstance(config, CustomRuleSet) else from_json(config)
    return register(rs, replace=True)


register(GBRuleSet())
register(SichuanRuleSet())
register(ChangshaRuleSet())
register(GuangdongRuleSet())

__all__ = [
    "RuleSet", "ScoreContext", "ScoreResult", "FanItem", "FanSet",
    "register", "get_ruleset", "list_rulesets", "register_custom",
    "fan_table", "from_json",
]
