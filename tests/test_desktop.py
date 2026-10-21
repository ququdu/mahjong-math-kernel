# -*- coding: utf-8 -*-
"""桌面版冒烟测试：能建窗口、能算、能渲染、能销毁。

没有图形环境时自动跳过（服务器 / CI 常见）。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pytest

tk = pytest.importorskip("tkinter")


def _tk_available():
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _tk_available(), reason="没有可用的图形环境")


def test_desktop_selftest():
    sys.path.insert(0, os.path.join(ROOT, "desktop"))
    import importlib

    mod = importlib.import_module("app")
    assert mod.selftest() == 0


def test_desktop_parses_meld_tiles():
    sys.path.insert(0, os.path.join(ROOT, "desktop"))
    import importlib

    mod = importlib.import_module("app")
    assert mod.parse_meld_tile("5z") == 31
    assert mod.parse_meld_tile("3m") == 2
    assert mod.parse_meld_tile("东") == 27
    assert mod.parse_meld_tile("7z") == 33
    assert mod.parse_meld_tile("9z") is None
    assert mod.parse_meld_tile("xx") is None
