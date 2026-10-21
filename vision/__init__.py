# -*- coding: utf-8 -*-
"""截图识别层。

    from vision import TemplatePack, Layout, recognize
    pack = TemplatePack.load("vision_data/templates.npz")
    layout = Layout.load("vision_data/layout.json")
    result = recognize(load_image("shot.png"), pack, layout)

第一次用需要先标定（学模板 + 标位置）：

    python -m vision.calibrate

它只依赖 Pillow + numpy，不装 OpenCV 也能跑。
"""

from __future__ import annotations

__all__ = [
    "TemplatePack", "Layout", "Region", "Matcher",
    "load_image", "save_image", "grab_screen",
    "recognize", "to_request", "infer_meld",
    "default_pack_path", "default_layout_path",
    "Capturer", "frame_key", "list_backends",
    "LiveSession", "LiveLoop", "LiveConfig", "LiveResult",
]

from .image import grab_screen, load_image, save_image
from .match import Matcher
from .pack import (
    Layout, Region, TemplatePack, default_layout_path, default_pack_path,
)
from .capture import Capturer, frame_key, list_backends
from .live import LiveConfig, LiveLoop, LiveResult, LiveSession
from .recognize import infer_meld, recognize, to_request
