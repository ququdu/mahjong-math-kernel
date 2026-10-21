# -*- coding: utf-8 -*-
"""麻将数学内核（Mahjong Math Kernel）。

一个纯 Python、零外部依赖的计算内核：向听 / 进张 / 番种 / 点数 / 概率 /
期望值 / 安全度全部算得出来，并通过同一套 JSON 协议对外服务。

设计原则
--------
1. **内核与界面解耦**：内核只认 ``BoardState`` 和 ``dict``，不认 tkinter、
   不认 HTTP、不认截图。谁都能接。
2. **规则可插拔**：国标、四川血战、广东推倒和都是 ``RuleSet`` 的实现，
   加规则 = 加一个文件。
3. **精确优先，近似标清楚**：向听、进张、番种、点数、超几何概率是精确推导；
   危险度、巡目衰减、顺位期望是显式声明的启发式模型，参数可调。

快速开始
--------
>>> from mahjong_kernel import Engine
>>> engine = Engine()
>>> engine.analyze({"ruleset": "gb", "hand": "123m456p789s111z9z"})["shanten"]
0
"""

from __future__ import annotations

__version__ = "1.0.0"

_LAZY = {
    "Engine": ("mahjong_kernel.engine", "Engine"),
    "BoardState": ("mahjong_kernel.hand", "BoardState"),
    "Meld": ("mahjong_kernel.meld", "Meld"),
    "RuleSet": ("mahjong_kernel.rulesets", "RuleSet"),
    "get_ruleset": ("mahjong_kernel.rulesets", "get_ruleset"),
    "list_rulesets": ("mahjong_kernel.rulesets", "list_rulesets"),
}

__all__ = sorted(_LAZY)


def __getattr__(name):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError("module %r has no attribute %r" % (__name__, name))
    import importlib

    module = importlib.import_module(target[0])
    value = getattr(module, target[1])
    globals()[name] = value
    return value


def __dir__():
    return __all__
