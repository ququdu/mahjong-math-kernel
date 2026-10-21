# -*- coding: utf-8 -*-
"""标定工具：一次学会模板，一次标出位置，之后丢截图就能识别。

    python -m vision.calibrate

用法（三步）
------------
1. **打开截图**：随便一张能看清手牌的截图（同一款游戏、同一个窗口大小）。
2. **框手牌区**：在图上拖一个矩形框住手牌那一排，把「格子数」填成实际张数。
   然后在下面的输入框里输入这排牌（比如 ``123m456p789s11z22z``），
   点「学习模板」——工具会把这 14 格拆出来，按你写的牌名存成模板。
   换个花色再来一两张，34 张很快就齐了（也可以直接导入一张 34 张的牌谱图）。
3. **存模板包 + 存版面**：存到 ``vision_data/`` 下，以后 ``recognize`` 直接用。

提示：格子宽高和间距要贴着实际牌面调，框到牌的内侧（不要带背景边框）识别最准。
"""

from __future__ import annotations

import os
import sys
import traceback

import numpy as np

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover
    tk = None

from .image import load_image, split_row, to_float_rgb
from .match import parse_tile_string
from .pack import Layout, Region, TemplatePack, default_layout_path, default_pack_path
from .recognize import infer_meld, recognize
from .pack import TILE_NAMES


class Calibrator(tk.Frame if tk else object):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        master.title("麻将截图识别 · 标定工具")
        master.geometry("1100x780")

        self.image = None          # np.ndarray RGB
        self.photo = None
        self.scale = 1.0
        self.drag_start = None
        self.drag_rect = None
        self.region = Region(x=0, y=0, cell_w=40, cell_h=56, pitch=42, count=14)
        self.melds = []
        self.pack = self._load_or_new_pack()
        self.layout = self._load_or_new_layout()

        self._build_ui()
        self._refresh_pack_info()
        self._refresh_region_info()

    # -- 载入已有数据 ---------------------------------------------------

    def _load_or_new_pack(self):
        path = default_pack_path()
        if os.path.exists(path):
            try:
                return TemplatePack.load(path)
            except Exception:
                pass
        return TemplatePack(size=(40, 56))

    def _load_or_new_layout(self):
        path = default_layout_path()
        if os.path.exists(path):
            try:
                return Layout.load(path)
            except Exception:
                pass
        return Layout()

    # -- 界面 -----------------------------------------------------------

    def _build_ui(self):
        top = ttk.Frame(self.master, padding=(10, 8))
        top.pack(fill="x")
        ttk.Button(top, text="打开截图", command=self.open_image).pack(side="left")
        ttk.Button(top, text="重新加载模板包", command=self.reload_pack).pack(side="left", padx=6)
        self.status = ttk.Label(top, text="先打开一张截图", foreground="#666")
        self.status.pack(side="left", padx=12)

        body = ttk.Frame(self.master)
        body.pack(fill="both", expand=True, padx=10)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, background="#1f2430", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        right = ttk.Frame(body, width=330)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        # --- 区域设置 ---
        box = ttk.LabelFrame(right, text="区域", padding=8)
        box.pack(fill="x")
        self.vars = {}
        for i, (key, label) in enumerate([("x", "X"), ("y", "Y"),
                                          ("cell_w", "格子宽"), ("cell_h", "格子高"),
                                          ("pitch", "间距"), ("count", "格子数")]):
            row = ttk.Frame(box)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label, width=8).pack(side="left")
            var = tk.StringVar(value=str(getattr(self.region, key)))
            self.vars[key] = var
            sp = ttk.Spinbox(row, from_=0, to=2000, textvariable=var, width=8,
                             command=self.apply_region_vars)
            sp.pack(side="left")
            sp.bind("<Return>", lambda e: self.apply_region_vars())
            sp.bind("<FocusOut>", lambda e: self.apply_region_vars())

        row = ttk.Frame(box)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="设为主手牌区", command=self.use_as_hand).pack(side="left")
        ttk.Button(row, text="添加为副露区", command=self.use_as_meld).pack(side="left", padx=6)

        # --- 学习模板 ---
        learn = ttk.LabelFrame(right, text="学习模板", padding=8)
        learn.pack(fill="x", pady=8)
        ttk.Label(learn, text="输入这一排的牌（如 123m456p789s11z22z）",
                  wraplength=300).pack(anchor="w")
        self.tiles_var = tk.StringVar()
        entry = ttk.Entry(learn, textvariable=self.tiles_var)
        entry.pack(fill="x", pady=4)
        entry.bind("<Return>", lambda e: self.learn())
        ttk.Button(learn, text="学习模板（从当前区域切格）",
                   command=self.learn).pack(fill="x")
        self.pack_info = ttk.Label(learn, text="", foreground="#666", wraplength=300)
        self.pack_info.pack(anchor="w", pady=(6, 0))

        # --- 试识别 ---
        test = ttk.LabelFrame(right, text="试识别", padding=8)
        test.pack(fill="x")
        ttk.Button(test, text="用当前版面识别这张图", command=self.try_recognize).pack(fill="x")
        self.result_text = tk.Text(test, height=7, wrap="word", font=("Consolas", 9))
        self.result_text.pack(fill="x", pady=(6, 0))

        # --- 保存 ---
        save = ttk.LabelFrame(right, text="保存", padding=8)
        save.pack(fill="x", pady=8)
        ttk.Button(save, text="保存模板包", command=self.save_pack).pack(fill="x")
        ttk.Button(save, text="保存版面", command=self.save_layout).pack(fill="x", pady=(6, 0))
        ttk.Button(save, text="保存模板包 + 版面", command=self.save_both).pack(fill="x", pady=(6, 0))
        self.save_info = ttk.Label(save, text=self._paths_text(), foreground="#666",
                                   wraplength=300)
        self.save_info.pack(anchor="w", pady=(6, 0))

    def _paths_text(self):
        return "模板包: %s\n版面: %s" % (default_pack_path(), default_layout_path())

    # -- 图像显示 -------------------------------------------------------

    def open_image(self):
        path = filedialog.askopenfilename(
            title="选择截图",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.webp"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self.image = to_float_rgb(load_image(path))
        except Exception as exc:
            messagebox.showerror("读图失败", str(exc))
            return
        self.render_canvas()
        self.set_status("已载入 %s  (%d×%d)" % (
            os.path.basename(path), self.image.shape[1], self.image.shape[0]))

    def render_canvas(self):
        if self.image is None:
            return
        from PIL import Image
        cw = max(200, self.canvas.winfo_width())
        ch = max(200, self.canvas.winfo_height())
        h, w = self.image.shape[:2]
        self.scale = min(cw / float(w), ch / float(h), 1.0)
        disp = Image.fromarray((self.image * 255).astype(np.uint8))
        disp = disp.resize((max(1, int(w * self.scale)), max(1, int(h * self.scale))),
                           Image.BILINEAR)
        from PIL import ImageTk
        self.photo = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.draw_region()

    def draw_region(self):
        if self.image is None:
            return
        self.canvas.delete("region")
        s = self.scale
        r = self.region
        x0, y0 = r.x * s, r.y * s
        for i in range(r.count):
            x = x0 + i * r.pitch * s
            self.canvas.create_rectangle(
                x, y0, x + r.cell_w * s, y0 + r.cell_h * s,
                outline="#4ade80" if i % 2 == 0 else "#22d3ee", width=1, tags="region")
        self.canvas.create_text(x0, y0 - 8, anchor="w",
                                text="手牌区 %d 格" % r.count,
                                fill="#facc15", tags="region")

    # -- 鼠标框选 -------------------------------------------------------

    def on_press(self, ev):
        self.drag_start = (ev.x, ev.y)
        if self.drag_rect:
            self.canvas.delete(self.drag_rect)
        self.drag_rect = self.canvas.create_rectangle(
            ev.x, ev.y, ev.x, ev.y, outline="#f472b6", width=2)

    def on_drag(self, ev):
        if self.drag_start and self.drag_rect:
            self.canvas.coords(self.drag_rect, self.drag_start[0], self.drag_start[1],
                               ev.x, ev.y)

    def on_release(self, ev):
        if not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = ev.x, ev.y
        self.drag_start = None
        if self.drag_rect:
            self.canvas.delete(self.drag_rect)
            self.drag_rect = None
        s = self.scale or 1.0
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        w = (right - left) / s
        h = (bottom - top) / s
        if w < 8 or h < 8:
            return
        count = max(1, self.region.count)
        cell_w = max(8, int(round(w / count)))
        self.region.x = int(round(left / s))
        self.region.y = int(round(top / s))
        self.region.cell_w = cell_w
        self.region.cell_h = max(8, int(round(h)))
        self.region.pitch = w / count
        self._refresh_region_info()
        self.draw_region()
        self.set_status("已框选：%d×%d，%d 格，间距 %.1f" % (
            self.region.cell_w, self.region.cell_h, self.region.count, self.region.pitch))

    def apply_region_vars(self):
        try:
            for key, var in self.vars.items():
                setattr(self.region, key, type(getattr(self.region, key))(float(var.get())))
        except (TypeError, ValueError):
            return
        self.draw_region()

    def _refresh_region_info(self):
        for key, var in self.vars.items():
            var.set(str(getattr(self.region, key)))

    def use_as_hand(self):
        self.layout.hand = Region(**{
            "x": self.region.x, "y": self.region.y,
            "cell_w": self.region.cell_w, "cell_h": self.region.cell_h,
            "pitch": self.region.pitch, "count": self.region.count})
        self.set_status("手牌区已设置（%d 格）" % self.region.count)

    def use_as_meld(self):
        self.layout.melds.append(Region(**{
            "x": self.region.x, "y": self.region.y,
            "cell_w": self.region.cell_w, "cell_h": self.region.cell_h,
            "pitch": self.region.pitch, "count": self.region.count}))
        self.set_status("已添加第 %d 个副露区（%d 格）" % (
            len(self.layout.melds), self.region.count))

    # -- 学习 -----------------------------------------------------------

    def learn(self):
        if self.image is None:
            messagebox.showwarning("还没图", "先打开一张截图")
            return
        text = self.tiles_var.get().strip()
        if not text:
            messagebox.showwarning("缺牌名", "输入这一排的牌，例如 123m456p789s11z22z")
            return
        try:
            tiles = parse_tile_string(text)
        except ValueError as exc:
            messagebox.showerror("看不懂", str(exc))
            return
        self.apply_region_vars()
        cells = split_row(self.image, self.region.to_dict(), count=len(tiles))
        if len(cells) != len(tiles):
            messagebox.showerror("格子数不对",
                                 "解析出 %d 张牌，但切出 %d 个格子" % (len(tiles), len(cells)))
            return
        for tile, cell in zip(tiles, cells):
            self.pack.add(tile, cell)
            self.pack.size = (self.region.cell_w, self.region.cell_h)
        self._refresh_pack_info()
        self.set_status("已学习 %d 张，模板包共 %d 张" % (len(tiles), len(self.pack)))

    def reload_pack(self):
        self.pack = self._load_or_new_pack()
        self._refresh_pack_info()
        self.set_status("模板包已重新加载：%d 张" % len(self.pack))

    def _refresh_pack_info(self):
        cov = self.pack.coverage()
        missing = cov["missing"]
        text = "已学 %d / 34 张" % cov["learned"]
        if missing:
            text += "\n缺：" + " ".join(missing)
        self.pack_info.config(text=text)

    # -- 试识别 ---------------------------------------------------------

    def try_recognize(self):
        if self.image is None:
            return
        try:
            self.pack.size = (self.region.cell_w, self.region.cell_h)
            self.layout.hand = Region(**{
                "x": self.region.x, "y": self.region.y,
                "cell_w": self.region.cell_w, "cell_h": self.region.cell_h,
                "pitch": self.region.pitch, "count": self.region.count})
            res = recognize(self.image, self.pack, self.layout)
        except Exception as exc:
            self.result_text.delete("1.0", "end")
            self.result_text.insert("1.0", "识别失败：%s" % exc)
            return
        lines = []
        lines.append("手牌: %s" % " ".join(TILE_NAMES[t] for t in res["tiles"]))
        lines.append("置信度: %.3f" % res["confidence"])
        for m in res["melds"]:
            lines.append("副露: %s %s" % (m["kind"], TILE_NAMES[m["tile"]]))
        for w in res["warnings"]:
            lines.append("⚠ " + w)
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", "\n".join(lines))

    # -- 保存 -----------------------------------------------------------

    def save_pack(self):
        try:
            self.pack.save(default_pack_path())
            self.set_status("模板包已保存：%s" % default_pack_path())
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def save_layout(self):
        try:
            if self.layout.hand is None:
                self.use_as_hand()
            self.layout.save(default_layout_path())
            self.set_status("版面已保存：%s" % default_layout_path())
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def save_both(self):
        self.save_layout()
        self.save_pack()

    def set_status(self, text, error=False):
        self.status.config(text=text, foreground="#c0392b" if error else "#666")


def main(argv=None):
    if tk is None:
        print("需要 tkinter 才能运行标定工具", file=sys.stderr)
        return 1
    root = tk.Tk()
    app = Calibrator(root)
    app.pack(fill="both", expand=True)
    root.mainloop()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
