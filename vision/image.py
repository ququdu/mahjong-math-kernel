# -*- coding: utf-8 -*-
"""图像基础：加载、裁剪、缩放、灰度化。

只处理**磁盘上的图片文件**。这里刻意没有截屏功能——本项目的定位是
离线分析，不做屏幕抓取（见 DISCLAIMER.md）。

只依赖 Pillow + numpy（都是现成的）；不装 OpenCV 也能跑。
装了 OpenCV 也不会自动用它——匹配走的是 numpy 向量化，够快。
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import numpy as np

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def require_pil():
    if Image is None:
        raise RuntimeError(
            "需要 Pillow 才能处理图片：pip install pillow")
    return Image


def load_image(path) -> "np.ndarray":
    """读图 -> RGB uint8 数组 (H, W, 3)。"""
    if isinstance(path, np.ndarray):
        return path
    if Image is None:
        raise RuntimeError("需要 Pillow 才能读图：pip install pillow")
    with Image.open(path) as im:
        return np.array(im.convert("RGB"))


def to_float_rgb(arr) -> "np.ndarray":
    """任意输入 -> float32 RGB (H, W, 3)，取值 0..1。

    灰度输入会被复制成三通道，这样匹配器只需要处理一种形状。
    """
    a = np.asarray(arr)
    if a.dtype == np.uint8:
        a = a.astype(np.float32) / 255.0
    else:
        a = a.astype(np.float32)
        if a.size and float(np.nanmax(a)) > 1.5:
            a = a / 255.0
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    elif a.shape[2] == 1:
        a = np.repeat(a, 3, axis=2)
    elif a.shape[2] > 3:
        a = a[..., :3]
    return a


def to_gray(arr) -> "np.ndarray":
    """RGB -> 灰度 float32（0..1）"""
    arr = np.asarray(arr)
    if arr.ndim == 2:
        return arr.astype(np.float32) / 255.0
    rgb = arr[..., :3].astype(np.float32) / 255.0
    return (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])


def crop(arr, x, y, w, h):
    """裁剪，越界部分用 0 补齐（而不是报错）。"""
    arr = np.asarray(arr)
    H, W = arr.shape[:2]
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(W, int(x) + int(w)), min(H, int(y) + int(h))
    if x1 <= x0 or y1 <= y0:
        shape = (max(1, int(h)), max(1, int(w))) + arr.shape[2:]
        return np.zeros(shape, dtype=arr.dtype)
    return arr[y0:y1, x0:x1]


def resize(arr, size: Tuple[int, int]):
    """缩放到 (w, h)，用双线性。没有 Pillow 时退化为最近邻。"""
    w, h = int(size[0]), int(size[1])
    arr = np.asarray(arr)
    if arr.ndim == 2:
        h0, w0 = arr.shape
    else:
        h0, w0 = arr.shape[:2]
    if (w, h) == (w0, h0):
        return arr
    if Image is not None:
        mode = "L" if arr.ndim == 2 else "RGB"
        im = Image.fromarray((arr * 255).astype(np.uint8) if arr.dtype != np.uint8 else arr,
                             mode=mode)
        return np.array(im.resize((w, h), Image.BILINEAR))
    # 最近邻兜底
    yi = (np.arange(h) * h0 // h).clip(0, h0 - 1)
    xi = (np.arange(w) * w0 // w).clip(0, w0 - 1)
    return arr[yi][:, xi]


def split_row(arr, region, count=None):
    """把一条横排区域切成若干等宽小格。

    region 需要 x / y / cell_w / cell_h / pitch / count。
    ``count`` 给定时覆盖 region.count。
    """
    n = int(count if count is not None else region.get("count", 0))
    cw = int(region["cell_w"])
    ch = int(region["cell_h"])
    pitch = float(region.get("pitch") or cw)
    x0 = float(region["x"])
    y0 = float(region["y"])
    cells = []
    for i in range(max(0, n)):
        cx = int(round(x0 + i * pitch))
        cells.append(crop(arr, cx, int(round(y0)), cw, ch))
    return cells


def save_image(arr, path):
    require_pil()
    a = np.asarray(arr)
    if a.dtype != np.uint8:
        a = np.clip(a * 255.0, 0, 255).astype(np.uint8)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    Image.fromarray(a).save(path)


