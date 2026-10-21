# -*- coding: utf-8 -*-
"""快速截屏。

为什么不用 ``PIL.ImageGrab.grab(bbox=...)``：它在 Windows 上**先把整屏抓下来
再裁**，抓一个 400×120 的小区域也要 50 毫秒以上，做实时的会卡住。

这里按「快 -> 慢」三级降级：

1. ``mss``      装了就用，跨平台，最快（约 2~5 ms）
2. ``gdi``      Windows 原生 BitBlt + GetDIBits，只抓目标区域（约 2~8 ms）
3. ``pil``      Pillow 的 ImageGrab，兜底（约 50~130 ms）

对外只有一个 ``Capturer.grab()``，返回 RGB uint8 数组；另外给一个
``frame_key()`` 用来判断"这一帧和上一帧一样吗"，一样就整条流水线跳过。
"""

from __future__ import annotations

import hashlib
import sys
from typing import Optional, Tuple

import numpy as np

BBox = Tuple[int, int, int, int]     # (x, y, w, h)


def frame_key(arr) -> str:
    """一帧的指纹：只用来看"有没有变"，不要求密码学强度。"""
    h = hashlib.blake2b(np.ascontiguousarray(arr).tobytes(), digest_size=8)
    return h.hexdigest()


# ---------------------------------------------------------------------------
#  mss 后端
# ---------------------------------------------------------------------------

class _MssBackend:
    name = "mss"

    def __init__(self):
        import mss  # noqa: F401
        self._sct = mss.mss()

    def grab(self, bbox: BBox):
        x, y, w, h = bbox
        shot = self._sct.grab({"left": int(x), "top": int(y),
                               "width": int(w), "height": int(h)})
        arr = np.frombuffer(shot.rgb, dtype=np.uint8)
        return arr.reshape((int(h), int(w), 3))

    def close(self):
        try:
            self._sct.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
#  Windows GDI 后端（不依赖第三方包）
# ---------------------------------------------------------------------------

class _GdiBackend:
    name = "gdi"

    # 常量
    SRCCOPY = 0x00CC0020
    BI_RGB = 0
    DIB_RGB_COLORS = 0
    CAPTUREBLT = 0x40000000

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wt = wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD),
                        ("biWidth", wintypes.LONG),
                        ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD),
                        ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG),
                        ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                        ("bmiColors", wintypes.DWORD * 3)]

        self.BITMAPINFO = BITMAPINFO
        self.BITMAPINFOHEADER = BITMAPINFOHEADER

        self.user32.GetDC.restype = wintypes.HDC
        self.user32.GetDC.argtypes = [wintypes.HWND]
        self.user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self.gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self.gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        self.gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        self.gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self.gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self.gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self.gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self.gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.HDC,
                                      ctypes.c_int, ctypes.c_int, wintypes.DWORD]
        self.gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP,
                                         wintypes.UINT, wintypes.UINT,
                                         ctypes.c_void_p, ctypes.POINTER(BITMAPINFO),
                                         wintypes.UINT]

        self._cache_bmp = None
        self._cache_size = None
        self._cache_dc = None
        self._screen_dc = None

    def _ensure(self, w, h):
        c = self.ctypes
        if self._screen_dc is None:
            self._screen_dc = self.user32.GetDC(None)
        if self._cache_size == (w, h) and self._cache_bmp:
            return
        if self._cache_bmp:
            self.gdi32.DeleteObject(self._cache_bmp)
            self.gdi32.DeleteDC(self._cache_dc)
        self._cache_dc = self.gdi32.CreateCompatibleDC(self._screen_dc)
        self._cache_bmp = self.gdi32.CreateCompatibleBitmap(self._screen_dc, int(w), int(h))
        self.gdi32.SelectObject(self._cache_dc, self._cache_bmp)
        self._cache_size = (w, h)

    def grab(self, bbox: BBox):
        c = self.ctypes
        x, y, w, h = (int(v) for v in bbox)
        if w <= 0 or h <= 0:
            raise ValueError("截图区域宽高必须为正: %r" % (bbox,))
        self._ensure(w, h)

        if not self.gdi32.BitBlt(self._cache_dc, 0, 0, w, h, self._screen_dc,
                                 x, y, self.SRCCOPY | self.CAPTUREBLT):
            raise OSError("BitBlt 失败（错误码 %d）" % c.get_last_error())

        bi = self.BITMAPINFO()
        bi.bmiHeader.biSize = c.sizeof(self.BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = w
        bi.bmiHeader.biHeight = -h           # 负值 = 自上而下，省一次翻转
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bi.bmiHeader.biCompression = self.BI_RGB

        buf = c.create_string_buffer(w * h * 4)
        if self.gdi32.GetDIBits(self._cache_dc, self._cache_bmp, 0, h,
                                buf, c.byref(bi), self.DIB_RGB_COLORS) == 0:
            raise OSError("GetDIBits 失败（错误码 %d）" % c.get_last_error())

        rgba = np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 4))
        return np.ascontiguousarray(rgba[..., 2::-1])   # BGRA -> RGB

    def close(self):
        try:
            if self._cache_bmp:
                self.gdi32.DeleteObject(self._cache_bmp)
            if self._cache_dc:
                self.gdi32.DeleteDC(self._cache_dc)
            if self._screen_dc:
                self.user32.ReleaseDC(None, self._screen_dc)
        except Exception:
            pass
        self._cache_bmp = self._cache_dc = self._screen_dc = None
        self._cache_size = None


# ---------------------------------------------------------------------------
#  Pillow 兜底
# ---------------------------------------------------------------------------

class _PilBackend:
    name = "pil"

    def __init__(self):
        from PIL import ImageGrab  # noqa: F401
        self._grab = ImageGrab.grab

    def grab(self, bbox: BBox):
        x, y, w, h = (int(v) for v in bbox)
        im = self._grab(bbox=(x, y, x + w, y + h))
        return np.array(im.convert("RGB"))

    def close(self):
        pass


_BACKENDS = {"mss": _MssBackend, "gdi": _GdiBackend, "pil": _PilBackend}


def _make_backend(prefer="auto"):
    order = ["mss", "gdi", "pil"] if prefer in ("auto", None) else [prefer]
    errors = []
    for name in order:
        cls = _BACKENDS.get(name)
        if cls is None:
            continue
        if name == "gdi" and not sys.platform.startswith("win"):
            continue
        try:
            return cls()
        except Exception as exc:  # noqa: BLE001
            errors.append("%s: %s" % (name, exc))
    raise RuntimeError("没有可用的截屏后端（%s）" % ("; ".join(errors) or "未知"))


class Capturer:
    """按区域抓屏。``grab()`` 返回 RGB uint8 (H, W, 3)。"""

    def __init__(self, bbox: Optional[BBox] = None, backend: str = "auto"):
        self.bbox = bbox
        self.backend = _make_backend(backend)
        self._last_key = None
        self._last_frame = None

    @property
    def backend_name(self):
        return self.backend.name

    def grab(self, bbox: Optional[BBox] = None):
        box = bbox or self.bbox
        if box is None:
            raise ValueError("没有指定截图区域")
        return self.backend.grab(box)

    def grab_changed(self, bbox: Optional[BBox] = None):
        """抓一帧，返回 (frame, key, changed)。

        ``changed`` 为 False 时调用方可以直接跳过后面所有步骤——
        这是实时模式下省 CPU 的关键：画面没变就什么都不做。
        """
        frame = self.grab(bbox)
        key = frame_key(frame)
        changed = key != self._last_key
        if changed:
            self._last_key = key
            self._last_frame = frame
        return frame, key, changed

    def close(self):
        self.backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def list_backends():
    """当前机器上哪些后端可用（给界面显示用）。"""
    out = []
    for name in ("mss", "gdi", "pil"):
        if name == "gdi" and not sys.platform.startswith("win"):
            continue
        try:
            be = _BACKENDS[name]()
            be.close()
            out.append(name)
        except Exception:
            pass
    return out
