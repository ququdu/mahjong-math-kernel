# -*- coding: utf-8 -*-
"""实时悬浮窗：置顶小窗，牌一变就更新建议。

    python desktop/overlay.py
    python desktop/overlay.py --interval 0.4 --ruleset gb

设计要点（都是为了避免"实时"变成"实时卡"）：

* 截屏 + 识别 + 计算全在**后台线程**跑，Tk 主线程只负责把结果画出来，
  所以窗口永远能拖动、永远不白屏。
* 画面没变就整条流水线跳过（只花一次截屏 + 一次哈希）。
* 新结果没算完之前，继续显示上一次的建议，不会闪空。
* 窗口可以按 Esc 关、F8 暂停、鼠标按住任意位置拖动。
"""

from __future__ import annotations

import argparse
import os
import queue
import sys
import time
import traceback

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox, ttk
except ImportError:  # pragma: no cover
    print("需要 tkinter 才能运行悬浮窗", file=sys.stderr)
    raise

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mahjong_kernel.tiles import TILE_NAMES                     # noqa: E402
from vision.capture import Capturer, list_backends              # noqa: E402
from vision.live import LiveConfig, LiveLoop, LiveResult, LiveSession  # noqa: E402
from vision.pack import Layout, TemplatePack, default_layout_path, default_pack_path  # noqa: E402


def pick_font():
    prefer = ["Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
              "Hiragino Sans GB", "SimHei"]
    try:
        fams = set(tkfont.families())
    except Exception:
        fams = set()
    for name in prefer:
        if name in fams:
            return name
    return "TkDefaultFont"


SHANTEN_COLOR = {0: "#12805c", -1: "#12805c"}


class Overlay:
    def __init__(self, root, session: LiveSession, backend_name="", interval=0.35):
        self.root = root
        self.session = session
        self.font = pick_font()
        self.queue = queue.Queue()
        self.last: LiveResult = None
        self.paused = False
        self._drag = None

        root.title("麻将实时建议")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-alpha", 0.94)
        except tk.TclError:
            pass
        root.configure(bg="#1b2330")

        self._build(backend_name, interval)
        self.loop = LiveLoop(
            session,
            on_result=lambda res: self.queue.put(("result", res)),
            on_idle=lambda res: self.queue.put(("idle", res)),
            on_error=lambda exc: self.queue.put(("error", exc)),
            on_refined=lambda res: self.queue.put(("refined", res)),
        )
        self._place_default()
        root.bind("<Escape>", lambda e: self.quit())
        root.bind("<F8>", lambda e: self.toggle_pause())
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.loop.start()
        self._drain()

    # -- 界面 -----------------------------------------------------------

    def _build(self, backend_name, interval):
        f = self.font
        pad = tk.Frame(self.root, bg="#1b2330", padx=10, pady=8)
        pad.pack(fill="both", expand=True)

        bar = tk.Frame(pad, bg="#1b2330")
        bar.pack(fill="x")
        title = tk.Label(bar, text="麻将内核 · 实时", bg="#1b2330", fg="#e8ecf6",
                         font=(f, 10, "bold"))
        title.pack(side="left")
        self.state_label = tk.Label(bar, text="启动中…", bg="#1b2330", fg="#8b96a8",
                                    font=(f, 9))
        self.state_label.pack(side="left", padx=8)
        close = tk.Label(bar, text="✕", bg="#1b2330", fg="#8b96a8",
                         font=(f, 11, "bold"), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.quit())
        self.pause_label = tk.Label(bar, text="⏸", bg="#1b2330", fg="#8b96a8",
                                    font=(f, 11, "bold"), cursor="hand2")
        self.pause_label.pack(side="right", padx=6)
        self.pause_label.bind("<Button-1>", lambda e: self.toggle_pause())

        self.hand_label = tk.Label(pad, text="（等待识别）", bg="#1b2330", fg="#c8d2e6",
                                   font=(f, 13), anchor="w", justify="left")
        self.hand_label.pack(fill="x", pady=(6, 2))

        stats = tk.Frame(pad, bg="#1b2330")
        stats.pack(fill="x")
        self.shanten_label = tk.Label(stats, text="—", bg="#1b2330", fg="#e8ecf6",
                                      font=(f, 20, "bold"))
        self.shanten_label.pack(side="left")
        self.detail_label = tk.Label(stats, text="", bg="#1b2330", fg="#8b96a8",
                                     font=(f, 9), justify="left", anchor="w")
        self.detail_label.pack(side="left", padx=10)

        self.rows_frame = tk.Frame(pad, bg="#1b2330")
        self.rows_frame.pack(fill="x", pady=(6, 0))
        self.rows = []
        for _ in range(3):
            r = tk.Label(self.rows_frame, text="", bg="#1b2330", fg="#c8d2e6",
                         font=(f, 10), anchor="w", justify="left")
            r.pack(fill="x")
            self.rows.append(r)

        self.advice_label = tk.Label(pad, text="", bg="#1b2330", fg="#f0c246",
                                     font=(f, 10, "bold"), anchor="w", justify="left")
        self.advice_label.pack(fill="x", pady=(4, 0))

        self.foot = tk.Label(pad, text="后端 %s · 每 %.2fs 轮询 · Esc 退出 / F8 暂停"
                             % (backend_name or "?", interval),
                             bg="#1b2330", fg="#5d6a80", font=(f, 8), anchor="w",
                             justify="left")
        self.foot.pack(fill="x", pady=(6, 0))

        for widget in (pad, bar, stats, self.hand_label, self.detail_label,
                       self.advice_label, self.rows_frame, self.foot):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

    def _place_default(self):
        self.root.update_idletasks()
        w = max(320, self.root.winfo_reqwidth())
        h = max(150, self.root.winfo_reqheight())
        sw = self.root.winfo_screenwidth()
        self.root.geometry("%dx%d+%d+%d" % (w, h, max(0, sw - w - 40), 80))

    def _start_drag(self, ev):
        self._drag = (ev.x_root - self.root.winfo_x(), ev.y_root - self.root.winfo_y())

    def _on_drag(self, ev):
        if not self._drag:
            return
        dx, dy = self._drag
        self.root.geometry("+%d+%d" % (ev.x_root - dx, ev.y_root - dy))

    # -- 交互 -----------------------------------------------------------

    def toggle_pause(self):
        self.paused = not self.paused
        self.loop.pause(self.paused)
        self.pause_label.config(text="▶" if self.paused else "⏸",
                                fg="#f0c246" if self.paused else "#8b96a8")
        self.state_label.config(text="已暂停" if self.paused else "运行中")

    def quit(self):
        try:
            self.loop.stop()
        finally:
            self.session.close()
            self.root.destroy()

    # -- 渲染 -----------------------------------------------------------

    def _drain(self):
        dirty_hand = False
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "result":
                    self.last = payload
                    dirty_hand = True
                elif kind == "refined":
                    self.last = payload
                    dirty_hand = True
                elif kind == "idle":
                    if payload.reason == "画面没变":
                        self.state_label.config(text="监看中")
                    elif payload.reason:
                        self.state_label.config(text=payload.reason)
                elif kind == "error":
                    self.state_label.config(text="出错：%s" % payload)
            if dirty_hand:
                self._render(self.last)
            self._render_footer()
        except queue.Empty:
            pass
        except Exception as exc:  # noqa: BLE001
            self.state_label.config(text="显示异常：%s" % exc)
        if self.root.winfo_exists():
            self.root.after(80, self._drain)

    def _render(self, res: LiveResult):
        if res is None:
            return
        report = res.report or {}
        hand = report.get("hand_cn") or " ".join(TILE_NAMES[t] for t in res.tiles)
        self.hand_label.config(text=hand or "（没识别出来）")

        s = report.get("shanten")
        if s is None:
            self.shanten_label.config(text="—", fg="#8b96a8")
        elif s < 0:
            self.shanten_label.config(text="已和牌", fg="#12805c")
        elif s == 0:
            self.shanten_label.config(text="听牌", fg="#12805c")
        else:
            self.shanten_label.config(text="%d 向听" % s,
                                      fg="#f0c246" if s <= 2 else "#e8ecf6")

        prob = report.get("probability") or {}
        bits = []
        if report.get("ukeire"):
            bits.append("进张 %d" % report["ukeire"])
        if prob.get("win_final"):
            bits.append("和牌率 %.0f%%" % (prob["win_final"] * 100))
        if prob.get("expected_draws"):
            bits.append("期望 %.1f 巡" % prob["expected_draws"])
        if res.confidence and res.confidence < 0.9:
            bits.append("置信 %.2f" % res.confidence)
        self.detail_label.config(text=" · ".join(bits) or "—")

        waits = report.get("waits") or {}
        if waits:
            self.detail_label.config(text=(" · ".join(bits) + "\n待牌 "
                                          + " ".join("%s×%d" % (k, v)
                                                      for k, v in list(waits.items())[:8])))

        top = res.top_discards(3)
        if not top and res.partial:
            # 结论已经出来了，排序还在补算——保留上一次的排序，别清空
            if not res.warnings:
                self.state_label.config(text="补算排序…")
            adv = report.get("advice") or {}
            if adv:
                self.advice_label.config(
                    text="%s（排序补算中…）" % adv.get("advice", ""))
            return

        for i, label in enumerate(self.rows):
            if i < len(top):
                d = top[i]
                mark = "▶" if i == 0 else " "
                label.config(
                    text="%s 打 %-3s  %-4s 进张%-3d 和牌%3.0f%% 铳%3.0f%% EV %6.2f" % (
                        mark, d["name"],
                        "听牌" if d["shanten"] == 0 else ("%d向听" % d["shanten"]),
                        d["ukeire"], d["win_prob"] * 100, d["deal_prob"] * 100, d["ev"]),
                    fg="#8fe3b8" if i == 0 else "#c8d2e6")
            else:
                label.config(text="", fg="#c8d2e6")

        adv = report.get("advice") or {}
        text = adv.get("advice", "")
        if adv.get("ratio") is not None:
            text += "（收益/风险 %.1f）" % adv["ratio"]
        score = report.get("score") or {}
        if score.get("ok"):
            text += " · %d 番 %d 点" % (score["fan"], score["points"])
        self.advice_label.config(text=text or "—")

        warn = res.warnings or []
        if warn:
            self.state_label.config(text=warn[0][:28])
        elif not self.paused:
            self.state_label.config(text="运行中")

    def _render_footer(self):
        fps = self.loop.fps
        t = (self.last.timings if self.last else {})
        parts = ["后端 %s" % getattr(self.session.capturer, "backend_name", "?"),
                 "%.1f 帧/秒" % fps,
                 "变化 %d 次" % self.loop.changes]
        if t.get("analyze"):
            parts.append("算 %.0fms" % t["analyze"])
        if t.get("recognize"):
            parts.append("认 %.0fms" % t["recognize"])
        parts.append("Esc 退出")
        self.foot.config(text=" · ".join(parts))


# ---------------------------------------------------------------------------
#  启动
# ---------------------------------------------------------------------------

def build_session(args):
    pack_path = args.pack or default_pack_path()
    layout_path = args.layout or default_layout_path()
    if not os.path.exists(pack_path):
        raise SystemExit("没有模板包：%s\n先跑 python -m vision.cli calibrate" % pack_path)
    if not os.path.exists(layout_path):
        raise SystemExit("没有版面：%s\n先跑 python -m vision.cli calibrate" % layout_path)
    pack = TemplatePack.load(pack_path)
    layout = Layout.load(layout_path)
    if layout.roi() is None:
        raise SystemExit("版面里没有手牌区，重新标定一次")
    capturer = Capturer(backend=args.backend)
    cfg = LiveConfig(ruleset=args.ruleset, turn=args.turn, wall=args.wall,
                     interval=args.interval)
    return LiveSession(capturer, pack, layout, cfg), capturer.backend_name


def main(argv=None):
    ap = argparse.ArgumentParser(description="麻将实时悬浮窗")
    ap.add_argument("--pack", default=None)
    ap.add_argument("--layout", default=None)
    ap.add_argument("--ruleset", default="gb")
    ap.add_argument("--turn", type=int, default=1)
    ap.add_argument("--wall", type=int, default=None)
    ap.add_argument("--interval", type=float, default=0.35, help="轮询间隔（秒）")
    ap.add_argument("--backend", default="auto",
                    help="截屏后端：auto / %s" % " / ".join(list_backends() or ["pil"]))
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        session, backend_name = build_session(args)
    except SystemExit:
        raise
    except Exception as exc:
        print("启动失败：%s" % exc, file=sys.stderr)
        return 1

    root = tk.Tk()
    app = Overlay(root, session, backend_name, args.interval)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.quit()
    return 0


def selftest():
    """不开真窗口跑完整个实时链路。"""
    from vision import synth

    errors = []
    pack = TemplatePack(size=(synth.TILE_W, synth.TILE_H))
    for t, img in synth.make_templates().items():
        pack.add(t, img)
    layout = synth.layout_for(count=14)
    roi = layout.roi()

    class FakeCapturer:
        backend_name = "fake"

        def __init__(self):
            self.frames = 0
            self.set([0, 1, 2, 4, 9, 10, 11, 18, 19, 20, 27, 27, 33, 33])

        def set(self, tiles):
            self.full = synth.make_screenshot(tiles, canvas=(900, 120))

        def grab(self, bbox=None):
            self.frames += 1
            x, y, w, h = bbox or roi
            return self.full[y:y + h, x:x + w].copy()

        def close(self):
            pass

    cap = FakeCapturer()
    session = LiveSession(cap, pack, layout, LiveConfig(turn=5, wall=60))
    r1 = session.poll()
    if not r1.changed or not r1.report:
        errors.append("首次没有产出结果")
    r2 = session.poll()
    if r2.changed:
        errors.append("画面没变还在重算")
    cap.set([0, 1, 2, 4, 9, 10, 11, 18, 19, 20, 27, 27, 32, 33])
    r3 = session.poll()
    if not r3.changed or not r3.report:
        errors.append("换牌后没有产出结果")
    if r1.report and r3.report and r1.report["hand"] == r3.report["hand"]:
        errors.append("换牌后手牌没变")
    session.close()

    if errors:
        print("SELFTEST FAILED")
        for e in errors:
            print("  - " + e)
        return 1
    print("SELFTEST OK: 首次 %.0fms，不变跳过，换牌 %.0fms" % (
        r1.timings.get("total", 0), r3.timings.get("total", 0)))
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
