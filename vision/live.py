# -*- coding: utf-8 -*-
"""实时模式：盯着屏幕上的一小块区域，牌一变就重算并给出建议。

流水线就四步，每一步都有"没变就退出"的短路：

    ┌──────────┐   指纹一样?   ┌──────────┐   手牌一样?  ┌──────────┐
    │ 截 ROI   │ ───是──▶ 丢弃 │ 识别牌面 │ ───是──▶ 丢弃 │ 算期望值 │
    └──────────┘               └──────────┘              └──────────┘

真正的开销分布（本机实测）::

    截屏（GDI，ROI 600×68）   3~19 ms      ← 每帧都做
    识别（14 格 × 34 模板）    7 ms         ← 只有画面变了才做
    analyze（冷，手牌变了）   170~300 ms   ← 只有手牌变了才做
    analyze（热，同手牌）      2 ms

所以闲着的时候每帧只花一次截屏 + 一次哈希；动手那一刻才掏那 200 毫秒。
实时循环建议跑在后台线程里，UI 线程只负责显示上一次的结果——这样永远不卡。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .capture import BBox, Capturer, frame_key
from .pack import Layout, TemplatePack
from .recognize import recognize, to_request

DEFAULTS = {
    "ruleset": "gb",
    "turn": 1,
    "wall": None,
    "min_score": 0.35,
    "expect_hand": None,
    "interval": 0.35,
}


@dataclass
class LiveConfig:
    ruleset: str = "gb"
    turn: int = 1
    wall: Optional[int] = None
    min_score: float = 0.35
    expect_hand: Optional[int] = None
    interval: float = 0.35

    @classmethod
    def from_dict(cls, d):
        cfg = cls()
        for k in DEFAULTS:
            if d and d.get(k) is not None:
                setattr(cfg, k, d[k])
        return cfg


@dataclass
class LiveResult:
    changed: bool
    partial: bool = False        # True = 只出了结论，弃牌排序还在算
    reason: str = ""
    hand: str = ""
    tiles: List[int] = field(default_factory=list)
    melds: List[Dict] = field(default_factory=list)
    report: Optional[Dict] = None
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)
    timings: Dict[str, float] = field(default_factory=dict)
    frame_key: str = ""

    def to_dict(self):
        return {
            "changed": self.changed,
            "partial": self.partial,
            "reason": self.reason,
            "hand": self.hand,
            "tiles": list(self.tiles),
            "melds": list(self.melds),
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "timings": dict(self.timings),
            "report": self.report,
        }

    # -- 给界面用的便捷属性 ------------------------------------------

    @property
    def shanten(self):
        return (self.report or {}).get("shanten")

    @property
    def advice(self):
        return (self.report or {}).get("advice") or {}

    def top_discards(self, n=3):
        return ((self.report or {}).get("discards") or [])[:n]


class LiveSession:
    """一次会话 = 一块屏幕区域 + 一套模板包/版面 + 一个引擎。"""

    def __init__(self, capturer, pack: TemplatePack, layout: Layout,
                 config: Optional[LiveConfig] = None, engine=None):
        self.capturer = capturer
        self.pack = pack
        self.layout = layout
        self.config = config or LiveConfig()
        self.bbox = layout.roi()
        if self.bbox is None:
            raise ValueError("版面里没有手牌区：先标定一次（vision.calibrate）")
        self._local_layout = layout.shifted(self.bbox[0], self.bbox[1])

        if engine is None:
            from mahjong_kernel import Engine
            engine = Engine()
        self.engine = engine

        self._last_frame_key = None
        self._last_hand_key = None
        self.last_result: Optional[LiveResult] = None
        self._pending_request: Optional[Dict] = None
        self._pending_meta: Optional[Dict] = None
        self._lock = threading.Lock()

    # -- 单次轮询 -------------------------------------------------------

    def poll(self, force: bool = False) -> LiveResult:
        t_start = time.perf_counter()
        frame = self.capturer.grab(self.bbox)
        t_cap = (time.perf_counter() - t_start) * 1000

        key = frame_key(frame)
        if not force and key == self._last_frame_key:
            return LiveResult(changed=False, reason="画面没变", frame_key=key,
                              timings={"capture": round(t_cap, 2)})
        self._last_frame_key = key

        t0 = time.perf_counter()
        try:
            res = recognize(frame, self.pack, self._local_layout,
                            min_score=self.config.min_score,
                            expect_hand=self.config.expect_hand)
        except Exception as exc:  # noqa: BLE001
            return LiveResult(changed=False, reason="识别失败: %s" % exc, frame_key=key,
                              timings={"capture": round(t_cap, 2)})
        t_rec = (time.perf_counter() - t0) * 1000

        hand_key = (tuple(res["tiles"]),
                    tuple(sorted((m["kind"], m["tile"]) for m in res.get("melds") or [])))
        if not force and hand_key == self._last_hand_key:
            return LiveResult(
                changed=False, reason="手牌没变", frame_key=key,
                tiles=res["tiles"], melds=res.get("melds") or [],
                confidence=res["confidence"], warnings=res["warnings"],
                timings={"capture": round(t_cap, 2), "recognize": round(t_rec, 2)})
        self._last_hand_key = hand_key

        if not res["tiles"]:
            return LiveResult(changed=False, reason="没识别出手牌", frame_key=key,
                              warnings=res["warnings"],
                              timings={"capture": round(t_cap, 2),
                                       "recognize": round(t_rec, 2)})

        t0 = time.perf_counter()
        request = to_request(res, ruleset=self.config.ruleset, turn=self.config.turn,
                             wall_remaining=self.config.wall)
        try:
            report = self.engine.analyze(request, lite=True)
        except Exception as exc:  # noqa: BLE001
            return LiveResult(changed=False, reason="计算出错: %s" % exc, frame_key=key,
                              warnings=res["warnings"])
        t_ana = (time.perf_counter() - t0) * 1000

        self._pending_request = request
        self._pending_meta = {"tiles": res["tiles"], "melds": res.get("melds") or [],
                              "confidence": res["confidence"],
                              "warnings": res["warnings"], "frame_key": key,
                              "t_cap": t_cap, "t_rec": t_rec}

        result = LiveResult(
            changed=True, partial=True, reason="ok",
            hand=report.get("hand", ""),
            tiles=res["tiles"], melds=res.get("melds") or [],
            report=report, confidence=res["confidence"],
            warnings=res["warnings"], frame_key=key,
            timings={"capture": round(t_cap, 2), "recognize": round(t_rec, 2),
                     "analyze_lite": round(t_ana, 2),
                     "total": round((time.perf_counter() - t_start) * 1000, 1)},
        )
        with self._lock:
            self.last_result = result
        return result

    def refine(self) -> Optional[LiveResult]:
        """把上一次 ``poll()`` 的手牌做完整分析（含逐张弃牌 EV 排序）。

        没有待补的手牌时返回 None。耗时 0.2~0.7 秒，所以放在结果已经显示
        之后再算——界面先有结论，再补排序。
        """
        with self._lock:
            request = self._pending_request
            meta = self._pending_meta
            self._pending_request = None
            self._pending_meta = None
        if request is None or meta is None:
            return None

        t0 = time.perf_counter()
        try:
            report = self.engine.analyze(request)
        except Exception as exc:  # noqa: BLE001
            return LiveResult(changed=False, reason="补算出错: %s" % exc,
                              warnings=meta["warnings"])
        t_ana = (time.perf_counter() - t0) * 1000

        result = LiveResult(
            changed=True, partial=False, reason="ok",
            hand=report.get("hand", ""),
            tiles=meta["tiles"], melds=meta["melds"],
            report=report, confidence=meta["confidence"],
            warnings=meta["warnings"], frame_key=meta["frame_key"],
            timings={"capture": round(meta["t_cap"], 2),
                     "recognize": round(meta["t_rec"], 2),
                     "analyze": round(t_ana, 2),
                     "total": round((time.perf_counter() - t0) * 1000, 1)},
        )
        with self._lock:
            self.last_result = result
        return result

    def close(self):
        try:
            self.capturer.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
#  后台循环
# ---------------------------------------------------------------------------

class LiveLoop:
    """把 ``poll()`` 塞进后台线程，结果通过回调送回 UI 线程。

    回调有三个：``on_result``（手牌变了）、``on_idle``（每轮都调，可用来刷
    "已运行 xx 秒"）、``on_error``。回调都在**工作线程**里执行，UI 调用方
    自己负责扔进队列。
    """

    def __init__(self, session: LiveSession,
                 on_result: Callable[[LiveResult], None],
                 on_idle: Optional[Callable[[LiveResult], None]] = None,
                 on_error: Optional[Callable[[Exception], None]] = None,
                 on_tick: Optional[Callable[[], None]] = None,
                 on_refined: Optional[Callable[[LiveResult], None]] = None):
        self.session = session
        self.on_result = on_result
        self.on_refined = on_refined
        self.on_idle = on_idle
        self.on_error = on_error
        self.on_tick = on_tick
        self._stop = threading.Event()
        self._thread = None
        self.paused = False
        self.frames = 0
        self.changes = 0
        self._t0 = None
        self.last_error = None

    # -- 控制 -----------------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._t0 = time.perf_counter()
        self._thread = threading.Thread(target=self._run, name="mahjong-live",
                                        daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def pause(self, value=True):
        self.paused = bool(value)

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    @property
    def fps(self):
        if not self._t0 or not self.frames:
            return 0.0
        elapsed = max(1e-6, time.perf_counter() - self._t0)
        return self.frames / elapsed

    # -- 线程体 ---------------------------------------------------------

    def _run(self):
        interval = max(0.05, float(self.session.config.interval))
        while not self._stop.is_set():
            if self.paused:
                self._stop.wait(0.15)
                continue
            try:
                res = self.session.poll()
            except Exception as exc:  # noqa: BLE001
                self.last_error = exc
                if self.on_error:
                    try:
                        self.on_error(exc)
                    except Exception:
                        pass
                self._stop.wait(0.5)
                continue
            self.frames += 1
            if res.changed:
                self.changes += 1
                if self.on_result:
                    self.on_result(res)
                if self.on_refined and res.partial:
                    refined = self.session.refine()
                    if refined is not None and not self._stop.is_set():
                        self.on_refined(refined)
            elif self.on_idle:
                self.on_idle(res)
            if self.on_tick:
                try:
                    self.on_tick()
                except Exception:
                    pass
            self._stop.wait(interval)
