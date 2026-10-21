# -*- coding: utf-8 -*-
"""截图识别层。

    from vision import TemplatePack, Layout, recognize
    pack = TemplatePack.load("vision_data/templates.npz")
    layout = Layout.load("vision_data/layout.json")
    result = recognize(load_image("shot.png"), pack, layout)

输入是**你自己提供的截图文件**——手牌截个图存下来，再丢进来算。
不做屏幕抓取、不做实时监听（原因见 DISCLAIMER.md）。

第一次用需要先标定（学模板 + 标位置）：

    python -m vision.calibrate

它只依赖 Pillow + numpy，不装 OpenCV 也能跑。
"""

from __future__ import annotations

__all__ = [
    "TemplatePack", "Layout", "Region", "Matcher",
    "load_image", "save_image",
    "recognize", "to_request", "infer_meld",
    "default_pack_path", "default_layout_path",
]

from .image import load_image, save_image
from .match import Matcher
from .pack import (
    Layout, Region, TemplatePack, default_layout_path, default_pack_path,
)
from .recognize import infer_meld, recognize, to_request
