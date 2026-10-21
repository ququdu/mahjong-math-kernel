# -*- coding: utf-8 -*-
"""桌面版（tkinter）：一个窗口把内核的全部结果摊开。

    python desktop/app.py

窗口分左右：左边填牌和场况，右边五个页签看结果（概览 / 番种 / 弃牌 /
概率曲线 / 方程对照）。所有计算都在本进程里直接调内核，不起服务、不联网。
"""

from __future__ import annotations

import os
import sys
import time
import traceback

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover
    print("需要 tkinter 才能运行桌面版", file=sys.stderr)
    raise

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mahjong_kernel import Engine, __version__          # noqa: E402
from mahjong_kernel.protocol import EQUATIONS, EQUATION_KINDS  # noqa: E402
from mahjong_kernel.tiles import TILE_NAMES             # noqa: E402

KIND_CN = {"chi": "吃", "pon": "碰", "minkan": "明杠", "ankan": "暗杠", "kakan": "加杠"}
HONOR = {"东": 27, "南": 28, "西": 29, "北": 30, "白": 31, "发": 32, "中": 33}
SUIT_BASE = {"m": 0, "w": 0, "万": 0, "p": 9, "t": 9, "筒": 9, "饼": 9,
             "s": 18, "条": 18, "索": 18, "z": 27, "字": 27}

EXAMPLES = [
    ("国标 · 听牌", dict(ruleset="gb", hand="123m456p789s11z235m", turn=5,
                         agari="", deficiency="")),
    ("国标 · 已和牌", dict(ruleset="gb", hand="123m456p789s111z22z", turn=1,
                           agari="2z", deficiency="")),
    ("十三幺", dict(ruleset="gb", hand="19m19p19s12345677z", turn=1,
                    agari="7z", deficiency="")),
    ("四川 · 定缺", dict(ruleset="sichuan", hand="123m456m789m234p55s", turn=3,
                         agari="", deficiency="s")),
    ("广东 · 推倒和", dict(ruleset="guangdong", hand="11122233344455m", turn=1,
                           agari="5m", deficiency="")),
]


def pick_font(root):
    """挑一个能显示中文的字体。"""
    prefer = ["Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
              "Hiragino Sans GB", "Source Han Sans SC", "SimHei", "SimSun"]
    try:
        families = set(tkfont.families(root))
    except Exception:
        families = set()
    for name in prefer:
        if name in families:
            return name
    return "TkDefaultFont"


def parse_meld_tile(text):
    """'5z' / '3m' / '东' -> 0..33"""
    text = (text or "").strip()
    if text in HONOR:
        return HONOR[text]
    if len(text) >= 2 and text[0].isdigit():
        rank = int(text[0])
        suit = text[1].lower()
        base = SUIT_BASE.get(suit)
        if base is None or not 1 <= rank <= 9:
            return None
        if base == 27:
            return 26 + rank if rank <= 7 else None
        return base + rank - 1
    return None


class App:
    def __init__(self, root):
        self.root = root
        self.engine = Engine()
        self.melds = []
        self.report = None
        self.rulesets = []
        self.font_name = pick_font(root)
        self._chart_job = None

        root.title("麻将数学内核 · 桌面版 v%s" % __version__)
        root.geometry("1200x780")
        root.minsize(980, 620)
        self._setup_style()
        self._build()
        self._load_rulesets()
        self._apply_example(EXAMPLES[0][1])
        self.root.after(120, self.compute)

    # -- 样式 -----------------------------------------------------------

    def _setup_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        base = (self.font_name, 10)
        self.root.option_add("*Font", base)
        style.configure(".", font=base)
        style.configure("Head.TLabel", font=(self.font_name, 17, "bold"))
        style.configure("Sub.TLabel", foreground="#6b7789")
        style.configure("Big.TLabel", font=(self.font_name, 20, "bold"))
        style.configure("Card.TLabel", foreground="#6b7789")
        style.configure("Err.TLabel", foreground="#c0392b")
        style.configure("Ok.TLabel", foreground="#12805c")
        style.configure("Warn.TLabel", foreground="#b25b00")
        style.configure("TNotebook.Tab", padding=(14, 6))
        style.configure("Treeview", rowheight=24)

    # -- 布局 -----------------------------------------------------------

    def _build(self):
        head = ttk.Frame(self.root, padding=(14, 10, 14, 6))
        head.pack(fill="x")
        ttk.Label(head, text="麻将数学内核", style="Head.TLabel").pack(side="left")
        ttk.Label(head, text="桌面版 v%s · 国标 / 四川血战 / 长沙 / 广东推倒和"
                  % __version__, style="Sub.TLabel").pack(side="left", padx=12)

        body = ttk.Frame(self.root, padding=(14, 0, 14, 8))
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, width=350)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._build_input(left)

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self._build_output(right)

        status = ttk.Frame(self.root, padding=(14, 4, 14, 8))
        status.pack(fill="x")
        self.status = ttk.Label(status, text="就绪", style="Sub.TLabel")
        self.status.pack(side="left")
        self.timing = ttk.Label(status, text="", style="Sub.TLabel")
        self.timing.pack(side="right")

    def _build_input(self, parent):
        box = ttk.Frame(parent)
        box.pack(fill="x")

        ttk.Label(box, text="规则").pack(anchor="w")
        self.rule_var = tk.StringVar()
        self.rule_box = ttk.Combobox(box, textvariable=self.rule_var, state="readonly",
                                     values=[])
        self.rule_box.pack(fill="x", pady=(0, 8))
        self.rule_box.bind("<<ComboboxSelected>>", self._on_rule_change)

        ttk.Label(box, text="手牌（123m456p789s11z / 123万456筒 / 东东中）").pack(anchor="w")
        self.hand_var = tk.StringVar(value="123m456p789s11z235m")
        hand_entry = ttk.Entry(box, textvariable=self.hand_var,
                               font=(self.font_name, 14))
        hand_entry.pack(fill="x", pady=(0, 8))
        hand_entry.bind("<Return>", lambda e: self.compute())

        row = ttk.Frame(box)
        row.pack(fill="x")
        self._spin(row, "巡目", "turn", 1, 20, 5)
        self._spin(row, "牌山剩余", "wall", 0, 136, None, width=10)
        self._spin(row, "花牌", "flowers", 0, 8, 0)

        row2 = ttk.Frame(box)
        row2.pack(fill="x", pady=(6, 0))
        col = ttk.Frame(row2)
        col.pack(side="left", fill="x", expand=True)
        ttk.Label(col, text="和牌张").pack(anchor="w")
        self.agari_var = tk.StringVar()
        ttk.Entry(col, textvariable=self.agari_var, width=10).pack(fill="x")
        col2 = ttk.Frame(row2)
        col2.pack(side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Label(col2, text="定缺").pack(anchor="w")
        self.def_var = tk.StringVar(value="")
        self.def_box = ttk.Combobox(col2, textvariable=self.def_var, state="disabled",
                                    values=["", "万", "筒", "条"], width=8)
        self.def_box.pack(fill="x")

        row3 = ttk.Frame(box)
        row3.pack(fill="x", pady=(6, 0))
        col3 = ttk.Frame(row3)
        col3.pack(side="left", fill="x", expand=True)
        ttk.Label(col3, text="已见牌（手牌以外）").pack(anchor="w")
        self.visible_var = tk.StringVar()
        ttk.Entry(col3, textvariable=self.visible_var).pack(fill="x")
        self.tsumo_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="自摸", variable=self.tsumo_var,
                        command=self.compute).pack(side="left", padx=(8, 0), pady=(16, 0))

        ttk.Separator(box).pack(fill="x", pady=10)

        meld_head = ttk.Frame(box)
        meld_head.pack(fill="x")
        ttk.Label(meld_head, text="副露").pack(side="left")
        ttk.Button(meld_head, text="＋添加", width=8,
                   command=self._add_meld_dialog).pack(side="right")
        ttk.Button(meld_head, text="删除选中", width=9,
                   command=self._del_meld).pack(side="right", padx=4)
        self.meld_list = tk.Listbox(box, height=4, activestyle="none",
                                    font=(self.font_name, 10))
        self.meld_list.pack(fill="x", pady=(4, 0))

        ttk.Separator(box).pack(fill="x", pady=10)

        actions = ttk.Frame(box)
        actions.pack(fill="x")
        ttk.Button(actions, text="计算", command=self.compute).pack(
            side="left", fill="x", expand=True)
        ttk.Button(actions, text="清空", command=self._clear).pack(
            side="left", padx=6)
        ttk.Button(actions, text="复制结果", command=self._copy_report).pack(
            side="left")
        ttk.Button(box, text="从截图识别…", command=self._recognize_shot).pack(
            fill="x", pady=(8, 0))

        ttk.Label(box, text="示例", style="Sub.TLabel").pack(anchor="w", pady=(12, 4))
        ex = ttk.Frame(box)
        ex.pack(fill="x")
        for i, (label, payload) in enumerate(EXAMPLES):
            ttk.Button(ex, text=label, width=16,
                       command=lambda p=payload: self._apply_example(p)).grid(
                row=i // 2, column=i % 2, sticky="ew", padx=(0, 4), pady=2)
        ex.columnconfigure(0, weight=1)
        ex.columnconfigure(1, weight=1)

    def _spin(self, parent, label, key, lo, hi, default, width=7):
        wrap = ttk.Frame(parent)
        wrap.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Label(wrap, text=label).pack(anchor="w")
        var = tk.StringVar(value="" if default is None else str(default))
        sp = ttk.Spinbox(wrap, from_=lo, to=hi, textvariable=var, width=width,
                         command=self.compute)
        sp.pack(fill="x")
        sp.bind("<Return>", lambda e: self.compute())
        setattr(self, key + "_var", var)
        return sp

    def _build_output(self, parent):
        self.nb = ttk.Notebook(parent)
        self.nb.pack(fill="both", expand=True)

        self.tab_overview = ttk.Frame(self.nb, padding=12)
        self.tab_discard = ttk.Frame(self.nb, padding=12)
        self.tab_score = ttk.Frame(self.nb, padding=12)
        self.tab_curve = ttk.Frame(self.nb, padding=12)
        self.tab_eq = ttk.Frame(self.nb, padding=12)
        for frame, title in ((self.tab_overview, "概览"), (self.tab_discard, "弃牌建议"),
                             (self.tab_score, "番种点数"), (self.tab_curve, "概率曲线"),
                             (self.tab_eq, "方程对照")):
            self.nb.add(frame, text=title)
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._redraw_chart())

        self._build_overview(self.tab_overview)
        self._build_discards(self.tab_discard)
        self._build_score(self.tab_score)
        self._build_curve(self.tab_curve)
        self._build_equations(self.tab_eq)

    def _build_overview(self, parent):
        cards = ttk.Frame(parent)
        cards.pack(fill="x")
        self.card_labels = {}
        specs = [("shanten", "向听"), ("ukeire", "进张"), ("win", "和牌率"),
                 ("tenpai", "听牌率"), ("draws", "期望摸牌"), ("defense", "守备效率")]
        for i, (key, title) in enumerate(specs):
            card = ttk.Frame(cards, padding=(10, 8), relief="solid", borderwidth=1)
            card.grid(row=0, column=i, sticky="ew", padx=(0, 6))
            cards.columnconfigure(i, weight=1)
            ttk.Label(card, text=title, style="Card.TLabel").pack(anchor="w")
            v = ttk.Label(card, text="—", style="Big.TLabel")
            v.pack(anchor="w")
            self.card_labels[key] = v

        waits = ttk.LabelFrame(parent, text="待牌 / 有效牌", padding=8)
        waits.pack(fill="x", pady=(12, 0))
        self.waits_label = ttk.Label(waits, text="—", wraplength=760, justify="left")
        self.waits_label.pack(anchor="w")

        advice = ttk.LabelFrame(parent, text="攻守与打点", padding=8)
        advice.pack(fill="x", pady=(10, 0))
        self.advice_label = ttk.Label(advice, text="—", wraplength=760, justify="left")
        self.advice_label.pack(anchor="w")

        warns = ttk.LabelFrame(parent, text="提示", padding=8)
        warns.pack(fill="both", expand=True, pady=(10, 0))
        self.warn_text = tk.Text(warns, height=6, wrap="word", relief="flat",
                                 font=(self.font_name, 10))
        self.warn_text.pack(fill="both", expand=True)
        self.warn_text.tag_configure("warn", foreground="#b25b00")

    def _build_discards(self, parent):
        cols = ("tile", "shanten", "ukeire", "win", "deal", "ev", "note")
        heads = ("打", "向听", "进张", "和牌率", "放铳率", "期望值", "说明")
        widths = (60, 60, 70, 80, 80, 80, 300)
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=14)
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center" if c != "note" else "w")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.tree.tag_configure("best", background="#eef1fe")
        self.tree.tag_configure("forced", foreground="#c0392b")
        self.tree.bind("<<TreeviewSelect>>", self._on_discard_select)

        self.detail_label = ttk.Label(parent, text="", wraplength=760, justify="left")
        self.detail_label.pack(anchor="w", pady=(8, 0))

    def _build_score(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x")
        self.score_fan = ttk.Label(top, text="—", style="Big.TLabel")
        self.score_fan.pack(side="left")
        self.score_points = ttk.Label(top, text="", style="Sub.TLabel")
        self.score_points.pack(side="left", padx=10)

        cols = ("name", "fan", "detail")
        self.score_tree = ttk.Treeview(parent, columns=cols, show="headings", height=12)
        for c, h, w in zip(cols, ("番种", "番数", "说明"), (220, 70, 420)):
            self.score_tree.heading(c, text=h)
            self.score_tree.column(c, width=w, anchor="center" if c != "detail" else "w")
        self.score_tree.pack(fill="both", expand=True, pady=(10, 0))

    def _build_curve(self, parent):
        self.canvas = tk.Canvas(parent, background="#ffffff", highlightthickness=1,
                                highlightbackground="#e2e7f0")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.curve_note = ttk.Label(parent, text="", style="Sub.TLabel")
        self.curve_note.pack(anchor="w", pady=(6, 0))

    def _build_equations(self, parent):
        note = ttk.Label(
            parent,
            text="45 条方程里，18 条是组合数学直接算出来的（精确），18 条是有假设的"
                 "模型，9 条在国标/四川/广东里不存在。混在一起会让人误以为都是精确的。",
            wraplength=760, justify="left", style="Sub.TLabel")
        note.pack(anchor="w", pady=(0, 8))

        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        cols = ("id", "name", "impl", "kind")
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=18)
        for c, h, w in zip(cols, ("#", "方程", "实现", "类型"), (44, 240, 330, 80)):
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="w" if c == "impl" else "center")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vs.set)
        tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        tree.tag_configure("exact", foreground="#12805c")
        tree.tag_configure("model", foreground="#b25b00")
        tree.tag_configure("na", foreground="#8b96a8")
        for i, name, impl, kind, _note in EQUATIONS:
            tree.insert("", "end", values=(i, name, impl.replace("mahjong_kernel.", ""),
                                           EQUATION_KINDS[kind].split("（")[0]),
                        tags=(kind.replace("n/a", "na"),))

    # -- 数据 -----------------------------------------------------------

    def _load_rulesets(self):
        try:
            data = self.engine.rulesets()
            self.rulesets = data["rulesets"]
        except Exception as exc:
            self._set_status("读取规则失败: %s" % exc, error=True)
            self.rulesets = [{"key": "gb", "name": "国标麻将"}]
        labels = []
        self._rule_key_by_label = {}
        for rs in self.rulesets:
            label = rs["name"]
            labels.append(label)
            self._rule_key_by_label[label] = rs
        self.rule_box.configure(values=labels)
        self.rule_box.set(labels[0] if labels else "")

    def _current_ruleset(self):
        label = self.rule_var.get()
        return self._rule_key_by_label.get(label, {"key": "gb", "name": "国标麻将"})

    def _on_rule_change(self, _evt=None):
        rs = self._current_ruleset()
        if rs.get("requires_deficiency"):
            self.def_box.configure(state="readonly")
        else:
            self.def_box.configure(state="disabled")
            self.def_var.set("")
        self.compute()

    def _request(self):
        rs = self._current_ruleset()
        hand = self.hand_var.get().strip()
        if not hand:
            raise ValueError("请先填手牌")
        req = {
            "ruleset": rs.get("key", "gb"),
            "hand": hand,
            "turn": int(self.turn_var.get() or 1),
            "flowers": int(self.flowers_var.get() or 0),
            "is_tsumo": bool(self.tsumo_var.get()),
        }
        wall = self.wall_var.get().strip()
        if wall:
            req["wall_remaining"] = int(wall)
        if self.agari_var.get().strip():
            req["agari_tile"] = self.agari_var.get().strip()
        if self.visible_var.get().strip():
            req["visible"] = self.visible_var.get().strip()
        if self.def_var.get():
            req["deficiency_suit"] = {"万": "m", "筒": "p", "条": "s"}[self.def_var.get()]
        if self.melds:
            req["melds"] = [{"kind": m["kind"], "tile": m["tile"]} for m in self.melds]
        return req

    # -- 计算 -----------------------------------------------------------

    def compute(self):
        try:
            req = self._request()
        except Exception as exc:
            self._set_status(str(exc), error=True)
            return
        self._set_status("计算中…")
        self.root.update_idletasks()
        t0 = time.perf_counter()
        try:
            report = self.engine.analyze(req)
        except Exception as exc:
            self._set_status("算出错: %s" % exc, error=True)
            if os.environ.get("MAHJONG_DEBUG") == "1":
                traceback.print_exc()
            return
        elapsed = (time.perf_counter() - t0) * 1000
        self.report = report
        try:
            self._render(report)
        except Exception as exc:
            self._set_status("显示出错: %s" % exc, error=True)
            if os.environ.get("MAHJONG_DEBUG") == "1":
                traceback.print_exc()
            return
        self.timing.configure(text="%d ms" % round(elapsed))
        self._set_status("就绪 · %s" % report.get("ruleset", {}).get("name", ""))

    def _render(self, r):
        self._render_overview(r)
        self._render_discards(r)
        self._render_score(r)
        self._redraw_chart()

    def _render_overview(self, r):
        if r.get("agari_blocked"):
            text, style = "形状已成和牌", "Warn.TLabel"
        elif r["is_agari"]:
            text, style = "已和牌", "Ok.TLabel"
        elif r["shanten"] == 0:
            text, style = "听牌", "Ok.TLabel"
        else:
            text, style = "%d 向听" % r["shanten"], "Big.TLabel"
        self.card_labels["shanten"].configure(text=text, style=style)
        self.card_labels["ukeire"].configure(text=str(r.get("ukeire", 0)))

        prob = r.get("probability") or {}
        self.card_labels["win"].configure(
            text="%.1f%%" % (prob.get("win_final", 0) * 100))
        self.card_labels["tenpai"].configure(
            text="%.1f%%" % (prob.get("tenpai_final", 0) * 100))
        draws = prob.get("expected_draws")
        self.card_labels["draws"].configure(
            text="—" if draws is None else "%.1f" % draws)
        safety = r.get("safety") or {}
        self.card_labels["defense"].configure(
            text="%.0f%%" % (safety.get("defense_efficiency", 0) * 100)
            if safety else "—")

        waits = r.get("waits") or {}
        if waits:
            self.waits_label.configure(
                text="  ".join("%s×%d" % (k, v) for k, v in waits.items()))
        else:
            self.waits_label.configure(
                text="已经和牌，没有待牌" if r["is_agari"] else "—")

        parts = []
        adv = r.get("advice")
        if adv:
            parts.append("建议：%s（%s）" % (adv["advice"], adv.get("reason", "")))
        score = r.get("score")
        if score and score.get("ok"):
            parts.append("打点：%d 番 / %d 点（%s）" % (
                score["fan"], score["points"],
                " + ".join("%s%d" % (i["name"], i["fan"]) for i in score["fan_items"])))
        elif score and score.get("notes"):
            parts.append("打点：%s" % "；".join(score["notes"]))
        self.advice_label.configure(text="\n".join(parts) or "—")

        self.warn_text.configure(state="normal")
        self.warn_text.delete("1.0", "end")
        lines = list(r.get("warnings") or [])
        self.warn_text.insert("end", "\n".join(lines) if lines else "（没有需要注意的地方）",
                              "warn" if lines else "")
        self.warn_text.configure(state="disabled")

    def _render_discards(self, r):
        self.tree.delete(*self.tree.get_children())
        self.discard_rows = {}
        for idx, d in enumerate(r.get("discards") or []):
            tags = []
            if d.get("forced"):
                tags.append("forced")
            elif idx == 0:
                tags.append("best")
            iid = self.tree.insert("", "end", tags=tuple(tags), values=(
                d["name"],
                "听牌" if d["shanten"] == 0 else d["shanten"],
                d["ukeire"],
                "%.1f%%" % (d["win_prob"] * 100),
                "%.1f%%" % (d["deal_prob"] * 100),
                "%.2f" % d["ev"],
                d.get("note", ""),
            ))
            self.discard_rows[iid] = d
        if not (r.get("discards") or []):
            self.detail_label.configure(
                text="需要 14 张手牌（摸牌后）才能给弃牌建议"
                     if not r["is_agari"] else "已经和牌，看「番种点数」页签")
        else:
            first = self.tree.get_children()
            if first:
                self.tree.selection_set(first[0])

    def _on_discard_select(self, _evt=None):
        sel = self.tree.selection()
        if not sel or not hasattr(self, "discard_rows"):
            return
        d = self.discard_rows.get(sel[0])
        if not d:
            return
        tiles = d.get("ukeire_tiles") or {}
        detail = "打出 %s 后：向听 %s，进张 %d 张，和牌率 %.1f%%，放铳率 %.1f%%，期望值 %.2f" % (
            d["name"], "听牌" if d["shanten"] == 0 else "%d 向听" % d["shanten"],
            d["ukeire"], d["win_prob"] * 100, d["deal_prob"] * 100, d["ev"])
        if tiles:
            detail += "\n有效牌：" + "  ".join("%s×%d" % (k, v) for k, v in tiles.items())
        self.detail_label.configure(text=detail)

    def _render_score(self, r):
        self.score_tree.delete(*self.score_tree.get_children())
        s = r.get("score")
        if not s:
            self.score_fan.configure(text="—", style="Big.TLabel")
            self.score_points.configure(
                text="想算番：把和牌张填上，或让手牌刚好 14 张和牌形")
            return
        if not s.get("ok"):
            self.score_fan.configure(text="不能和", style="Err.TLabel")
            self.score_points.configure(text="；".join(s.get("notes") or []))
            return
        self.score_fan.configure(text="%d 番" % s["fan"], style="Ok.TLabel")
        pay = s.get("payments") or {}
        extra = "%d 点" % s["points"]
        if "each" in pay:
            extra += "（自摸每家 %d）" % pay["each"]
        self.score_points.configure(text=extra)
        for item in s.get("fan_items") or []:
            self.score_tree.insert("", "end", values=(
                item["name"], item["fan"], item.get("detail", "")))

    # -- 曲线 -----------------------------------------------------------

    def _on_canvas_resize(self, _evt=None):
        if self._chart_job:
            self.root.after_cancel(self._chart_job)
        self._chart_job = self.root.after(120, self._redraw_chart)

    def _redraw_chart(self):
        self._chart_job = None
        c = self.canvas
        if c is None:
            return
        c.delete("all")
        prob = (self.report or {}).get("probability")
        w = max(200, c.winfo_width())
        h = max(160, c.winfo_height())
        if not prob or not prob.get("win_by_turn"):
            c.create_text(16, 20, anchor="w", fill="#8b96a8", text="没有概率数据")
            self.curve_note.configure(text="")
            return

        pad_l, pad_r, pad_t, pad_b = 48, 16, 18, 34
        iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
        win = prob["win_by_turn"]
        ten = prob.get("tenpai_by_turn") or []
        n = len(win)
        xs = [pad_l + (iw * i / (n - 1) if n > 1 else 0) for i in range(n)]
        ys = [pad_t + (1 - v) * ih for v in win]

        for tick in (0, 0.25, 0.5, 0.75, 1.0):
            y = pad_t + (1 - tick) * ih
            c.create_line(pad_l, y, pad_l + iw, y, fill="#e6eaf3")
            c.create_text(pad_l - 6, y, anchor="e", fill="#8b96a8",
                          text="%d%%" % round(tick * 100), font=(self.font_name, 8))
        for i in range(0, n, 3):
            c.create_text(xs[i], pad_t + ih + 14, fill="#8b96a8",
                          text="巡%d" % (i + 1), font=(self.font_name, 8))

        if ten and len(ten) == n:
            pts = []
            for i, v in enumerate(ten):
                pts.extend((xs[i], pad_t + (1 - v) * ih))
            c.create_line(*pts, fill="#c9a227", width=2, smooth=False)
        pts = []
        for i, v in enumerate(win):
            pts.extend((xs[i], pad_t + (1 - v) * ih))
        c.create_line(*pts, fill="#3554d1", width=3, smooth=False)
        for i in range(0, n, 3):
            c.create_oval(xs[i] - 3, ys[i] - 3, xs[i] + 3, ys[i] + 3,
                          fill="#3554d1", outline="")

        c.create_line(w - 150, 8, w - 136, 8, fill="#3554d1", width=3)
        c.create_text(w - 130, 8, anchor="w", fill="#1b2330", text="和牌率",
                      font=(self.font_name, 9))
        c.create_line(w - 78, 8, w - 64, 8, fill="#c9a227", width=2)
        c.create_text(w - 58, 8, anchor="w", fill="#1b2330", text="听牌率",
                      font=(self.font_name, 9))

        self.curve_note.configure(
            text="未见面牌 %s 张 · 累计和牌率 %.1f%% · 流局概率 %.1f%%" % (
                prob.get("unseen", "—"), prob.get("win_final", 0) * 100,
                prob.get("draw_probability", 0) * 100))

    # -- 副露 -----------------------------------------------------------

    def _add_meld_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("添加副露")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)

        body = ttk.Frame(dlg, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="类型").pack(anchor="w")
        kind_var = tk.StringVar(value="pon")
        ttk.Combobox(body, textvariable=kind_var, state="readonly",
                     values=["chi", "pon", "minkan", "ankan", "kakan"]).pack(fill="x")
        ttk.Label(body, text="牌（顺子填起始牌，如 3m 表示 345m）").pack(
            anchor="w", pady=(8, 0))
        tile_var = tk.StringVar()
        entry = ttk.Entry(body, textvariable=tile_var)
        entry.pack(fill="x")
        entry.focus_set()
        err = ttk.Label(body, text="", style="Err.TLabel")
        err.pack(anchor="w", pady=(6, 0))

        def ok():
            tile = parse_meld_tile(tile_var.get())
            if tile is None:
                err.configure(text="看不懂这张牌")
                return
            self.melds.append({"kind": kind_var.get(), "tile": tile,
                               "label": tile_var.get().strip()})
            dlg.destroy()
            self._refresh_melds()
            self.compute()

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="添加", command=ok).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="取消", command=dlg.destroy).pack(side="left", padx=6)
        entry.bind("<Return>", lambda e: ok())
        dlg.wait_window()

    def _del_meld(self):
        sel = self.meld_list.curselection()
        if not sel:
            return
        del self.melds[sel[0]]
        self._refresh_melds()
        self.compute()

    def _refresh_melds(self):
        self.meld_list.delete(0, "end")
        if not self.melds:
            self.meld_list.insert("end", "（没有副露）")
            return
        for m in self.melds:
            self.meld_list.insert("end", "%s %s（%s）" % (
                KIND_CN.get(m["kind"], m["kind"]),
                m["label"] if "label" in m else TILE_NAMES[m["tile"]],
                TILE_NAMES[m["tile"]]))

    # -- 其它 -----------------------------------------------------------

    def _apply_example(self, payload):
        label = next((lb for lb, p in EXAMPLES if p is payload), None)
        if label:
            self._rule_label_for_key(payload["ruleset"])
        self.hand_var.set(payload.get("hand", ""))
        self.turn_var.set(str(payload.get("turn", 1)))
        self.agari_var.set(payload.get("agari", ""))
        self.def_var.set({"m": "万", "p": "筒", "s": "条", "": ""}.get(
            payload.get("deficiency", ""), ""))
        self.wall_var.set("")
        self.visible_var.set("")
        self.tsumo_var.set(False)
        self.melds = []
        self._refresh_melds()
        self._on_rule_change()

    def _rule_label_for_key(self, key):
        for label, rs in self._rule_key_by_label.items():
            if rs.get("key") == key:
                self.rule_box.set(label)
                return

    def _clear(self):
        for var in (self.hand_var, self.agari_var, self.visible_var, self.wall_var):
            var.set("")
        self.def_var.set("")
        self.tsumo_var.set(False)
        self.melds = []
        self._refresh_melds()
        self.report = None
        for lb in self.card_labels.values():
            lb.configure(text="—", style="Big.TLabel")
        self.waits_label.configure(text="—")
        self.advice_label.configure(text="—")
        self.tree.delete(*self.tree.get_children())
        self.score_tree.delete(*self.score_tree.get_children())
        self.detail_label.configure(text="")
        self.canvas.delete("all")
        self.curve_note.configure(text="")
        self._set_status("就绪")

    def _copy_report(self):
        if not self.report:
            self._set_status("还没有结果可以复制", error=True)
            return
        r = self.report
        lines = []
        lines.append("手牌: %s" % r.get("hand", ""))
        s = r.get("shanten", 0)
        lines.append("向听: %s" % ("已和牌" if s < 0 else ("听牌" if s == 0 else "%d 向听" % s)))
        if r.get("waits"):
            lines.append("待牌: " + ", ".join("%s×%d" % (k, v) for k, v in r["waits"].items()))
        lines.append("进张: %d 张" % r.get("ukeire", 0))
        prob = r.get("probability") or {}
        if prob:
            lines.append("和牌率: %.1f%% / 听牌率 %.1f%%" % (
                prob.get("win_final", 0) * 100, prob.get("tenpai_final", 0) * 100))
        score = r.get("score")
        if score and score.get("ok"):
            lines.append("番种: " + " + ".join(
                "%s%d" % (i["name"], i["fan"]) for i in score["fan_items"]))
            lines.append("打点: %d 番 / %d 点" % (score["fan"], score["points"]))
        if r.get("advice"):
            lines.append("攻守: %s（%s）" % (r["advice"]["advice"], r["advice"].get("reason", "")))
        if r.get("discards"):
            lines.append("弃牌建议:")
            for d in r["discards"][:8]:
                lines.append("  打 %-4s 向听 %d 进张 %-3d 和牌率 %.1f%% 放铳率 %.1f%% 期望值 %.2f" % (
                    d["name"], d["shanten"], d["ukeire"],
                    d["win_prob"] * 100, d["deal_prob"] * 100, d["ev"]))
        for w in r.get("warnings") or []:
            lines.append("提示: " + w)
        text = "\n".join(lines)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._set_status("结果已复制到剪贴板")

    def _recognize_shot(self):
        """选一张截图，用本地模板包/版面识别，再把结果填回输入区。"""
        path = filedialog.askopenfilename(
            title="选择截图",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.webp"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            from vision import (Layout, TemplatePack, default_layout_path,
                                default_pack_path, load_image, recognize)
        except ImportError as exc:
            self._set_status("识别需要 vision 包（Pillow + numpy）：%s" % exc, error=True)
            return
        pack_path = default_pack_path()
        layout_path = default_layout_path()
        if not os.path.exists(pack_path) or not os.path.exists(layout_path):
            self._set_status("还没有标定：先运行 python -m vision.cli calibrate", error=True)
            return
        try:
            res = recognize(load_image(path), TemplatePack.load(pack_path),
                            Layout.load(layout_path))
        except Exception as exc:
            self._set_status("识别失败：%s" % exc, error=True)
            return
        if not res.get("tiles"):
            self._set_status("没识别出手牌：%s" % "；".join(res.get("warnings") or []),
                             error=True)
            return
        from mahjong_kernel.tiles import counts_to_str, to_counts
        self.hand_var.set(counts_to_str(to_counts(res["tiles"])))
        self.melds = [{"kind": m["kind"], "tile": m["tile"],
                       "label": TILE_NAMES[m["tile"]]} for m in res.get("melds") or []]
        self._refresh_melds()
        self.compute()
        note = "识别完成（置信度 %.2f）" % res["confidence"]
        if res.get("warnings"):
            note += "，%d 条提示" % len(res["warnings"])
        self._set_status(note, bool(res.get("warnings")))

    def _set_status(self, text, error=False):
        self.status.configure(text=text, style="Err.TLabel" if error else "Sub.TLabel")


def selftest():
    """不等人操作，直接把窗口建起来跑两轮计算再销毁。"""
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    root.update()
    errors = []

    checks = [
        dict(ruleset="gb", hand="123m456p789s11z235m", turn=5),
        dict(ruleset="sichuan", hand="123m456m789m234p55s", deficiency_suit="s", turn=3),
    ]
    for req in checks:
        try:
            report = app.engine.analyze(req)
        except Exception as exc:
            errors.append("analyze(%r) 抛异常: %s" % (req, exc))
            continue
        if not isinstance(report.get("shanten"), int):
            errors.append("shanten 不是整数: %r" % (report.get("shanten"),))
        if req["ruleset"] == "gb" and not report.get("discards"):
            errors.append("国标 14 张手牌没给弃牌建议")
        try:
            app._render(report)
        except Exception as exc:
            errors.append("渲染失败: %s" % exc)
            traceback.print_exc()

    try:
        app.compute()
    except Exception as exc:
        errors.append("compute() 失败: %s" % exc)

    root.destroy()
    if errors:
        print("SELFTEST FAILED")
        for e in errors:
            print("  - " + e)
        return 1
    print("SELFTEST OK")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return selftest()
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
