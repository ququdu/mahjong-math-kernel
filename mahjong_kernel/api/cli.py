# -*- coding: utf-8 -*-
"""命令行界面。

    python -m mahjong_kernel.api.cli analyze "123m456p789s11z235m" --ruleset gb
    python -m mahjong_kernel.api.cli score   "123m456p789s111z22z" --win 2z
    python -m mahjong_kernel.api.cli discard "123m456p789s11z235m"
    python -m mahjong_kernel.api.cli prob    "123m456p7s11z23s" --wall 60
    python -m mahjong_kernel.api.cli ev      "123m456p7s11z23s" --scores 25000,25000,25000,25000
    python -m mahjong_kernel.api.cli rulesets
    python -m mahjong_kernel.api.cli equations
    python -m mahjong_kernel.api.cli serve --port 8765
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from .. import __version__
from ..engine import Engine
from ..protocol import EQUATION_KINDS, EQUATIONS, PROTOCOL_VERSION


def _split_ints(text):
    if not text:
        return None
    out = []
    for part in str(text).replace("，", ",").split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    return out or None


def _build(args) -> Dict[str, Any]:
    req: Dict[str, Any] = {
        "ruleset": args.ruleset,
        "hand": args.hand,
        "turn": args.turn,
        "is_tsumo": args.tsumo,
    }
    if args.wall is not None:
        req["wall_remaining"] = args.wall
    if args.melds:
        melds = []
        for spec in args.melds:
            kind, _, tile = spec.partition(":")
            from ..tiles import parse_tiles
            tiles = parse_tiles(tile)
            if not tiles:
                raise SystemExit("副露格式应为 kind:牌，例如 pon:5z")
            melds.append({"kind": kind, "tile": tiles[0]})
        req["melds"] = melds
    if args.visible:
        req["visible"] = args.visible
    if args.discards:
        req["self_discards"] = args.discards
    if args.win:
        req["agari_tile"] = args.win
    if args.deficiency:
        req["deficiency_suit"] = args.deficiency
    if args.seat_wind:
        req["seat_wind"] = args.seat_wind
    if args.round_wind:
        req["round_wind"] = args.round_wind
    if args.flowers:
        req["flowers"] = args.flowers
    if args.scores:
        req["scores"] = _split_ints(args.scores)
    if args.hero is not None:
        req["hero"] = args.hero
    return req


def _print(obj, as_json):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return
    if not obj.get("ok", True):
        print("✗ 算不了：")
        for n in obj.get("notes") or [obj.get("error", "未知错误")]:
            print("   - %s" % n)
        return

    if "rulesets" in obj:
        print("%-12s %-20s %-8s %-10s %s" % ("key", "名称", "起和番", "底分/张数", "说明"))
        for r in obj["rulesets"]:
            print("%-12s %-20s %-8d %-10s %s" % (
                r["key"], r["name"], r.get("min_fan", 0),
                "%s / %s" % (r.get("base_points", 0), r.get("tile_count", "")),
                r.get("description", "")))
        return

    if ("ruleset" in obj and "hand" not in obj and "version" not in obj
            and isinstance(obj.get("ruleset"), dict) and "key" in obj["ruleset"]):
        r = obj["ruleset"]
        print("已注册规则: %s (%s)  起和 %d 番  底分 %d" % (
            r["name"], r["key"], r.get("min_fan", 0), r.get("base_points", 0)))
        return

    if obj.get("hand"):
        print("手牌  : %s" % obj["hand"])
    if "fan" in obj and "points" in obj and "shanten" not in obj:
        print("番数  : %d 番    点数: %d" % (obj["fan"], obj["points"]))
        print("番种  : %s" % " + ".join(
            "%s%d" % (i["name"], i["fan"]) for i in obj.get("fan_items") or []))
        if obj.get("payments"):
            print("支付  : %s" % obj["payments"])
        for n in obj.get("notes") or []:
            print("说明  : %s" % n)
        return
    if "shanten" in obj:
        s = obj["shanten"]
        if obj.get("agari_blocked"):
            tag = "形状已成和牌（规则上不能和）"
        elif s < 0:
            tag = "已和牌"
        else:
            tag = "听牌" if s == 0 else "%d 向听" % s
        print("向听  : %s" % tag)
    if obj.get("waits"):
        print("待牌  : %s" % ", ".join("%s×%d" % (k, v) for k, v in obj["waits"].items()))
    if obj.get("ukeire"):
        print("进张  : %d 张   效率 %.3f" % (obj["ukeire"], obj.get("efficiency", 0)))
    prob = obj.get("probability")
    if prob:
        print("和牌率: 到末巡 %.1f%%   听牌率 %.1f%%   期望摸牌 %.1f 巡" % (
            prob["win_final"] * 100, prob["tenpai_final"] * 100,
            prob.get("expected_draws") or 0))
    score = obj.get("score")
    if score and score.get("ok"):
        print("番点  : %d 番 / %d 点" % (score["fan"], score["points"]))
        print("  番种: %s" % " + ".join(
            "%s%d" % (i["name"], i["fan"]) for i in score["fan_items"]))
    elif score:
        print("番点  : %s" % ("；".join(score.get("notes") or ["不能和"])))
    adv = obj.get("advice")
    if adv:
        print("攻守  : %s（%s）" % (adv["advice"], adv.get("reason", "")))
    discards = obj.get("discards")
    if discards:
        print("\n弃牌建议（按期望值排序）:")
        print("  %-4s %-4s %-6s %-8s %-8s %-8s %s" % (
            "打", "向听", "进张", "和牌率", "放铳率", "期望值", "说明"))
        for d in discards[:8]:
            print("  %-4s %-4d %-6d %-8s %-8s %-8.2f %s" % (
                d["name"], d["shanten"], d["ukeire"],
                "%5.1f%%" % (d["win_prob"] * 100),
                "%5.1f%%" % (d["deal_prob"] * 100),
                d["ev"], d.get("note", "")))
    elif "discards" in obj and "advice" in obj:
        print("\n弃牌建议:")
        for d in obj["discards"][:8]:
            print("  打 %-4s 向听 %d 进张 %-3d 和牌率 %5.1f%% 期望值 %.2f" % (
                d["name"], d["shanten"], d["ukeire"], d["win_prob"] * 100, d["ev"]))
    if "ev" in obj and "should_push" in obj:
        print("期望值: %.2f   收益/风险 %.2f   %s" % (
            obj["ev"], obj["ratio"] or 0,
            "建议进攻" if obj["should_push"] else "建议弃和"))
    if "win_by_turn" in obj:
        print("逐巡和牌率: " + " ".join("%.1f%%" % (v * 100) for v in obj["win_by_turn"]))
    if obj.get("safety"):
        sf = obj["safety"]
        safe = sf.get("safest_discard")
        print("守备  : 安全牌占比 %.0f%%   最安全弃牌 %s" % (
            sf["defense_efficiency"] * 100,
            safe["name"] if safe else "无"))
    for w in obj.get("warnings") or []:
        print("⚠ %s" % w)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="mahjong-kernel", description="麻将数学内核 v%s" % __version__)
    ap.add_argument("--json", action="store_true", help="输出原始 JSON")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("hand", help="手牌，如 123m456p789s11z")
        p.add_argument("--ruleset", "-r", default="gb",
                       help="gb / sichuan / changsha / guangdong")
        p.add_argument("--turn", type=int, default=1)
        p.add_argument("--wall", type=int, default=None, help="牌山剩余张数")
        p.add_argument("--melds", nargs="*", default=None,
                       help="副露，如 pon:5z ankan:1z")
        p.add_argument("--visible", default=None, help="手牌之外已见的牌")
        p.add_argument("--discards", default=None, help="自己的弃牌")
        p.add_argument("--tsumo", action="store_true", help="是否自摸")
        p.add_argument("--win", default=None, help="和牌张")
        p.add_argument("--deficiency", default=None, help="四川定缺 m/p/s")
        p.add_argument("--seat-wind", dest="seat_wind", default=None)
        p.add_argument("--round-wind", dest="round_wind", default=None)
        p.add_argument("--flowers", type=int, default=0)
        p.add_argument("--scores", default=None, help="四家点数，逗号分隔")
        p.add_argument("--hero", type=int, default=None)
        # 允许把 --json 写在子命令后面（不覆盖顶层已给的值）
        p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    common(sub.add_parser("analyze", help="一屏报告"))
    common(sub.add_parser("score", help="算番与点数"))
    common(sub.add_parser("discard", help="只算弃牌"))
    common(sub.add_parser("prob", help="只算概率曲线"))
    common(sub.add_parser("ev", help="只算期望值"))

    for name, help_text in (("rulesets", "列出规则集"),
                            ("equations", "列出 45 条方程与实现对照")):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    rec = sub.add_parser("recognize", help="识别截图（需要先标定模板包与版面）")
    rec.add_argument("image", help="截图路径")
    rec.add_argument("--pack", default=None, help="模板包路径")
    rec.add_argument("--layout", default=None, help="版面路径")
    rec.add_argument("--analyze", action="store_true", help="识别完直接算一遍")
    rec.add_argument("--ruleset", "-r", default="gb")
    rec.add_argument("--turn", type=int, default=1)
    rec.add_argument("--wall", type=int, default=None)
    rec.add_argument("--min-score", dest="min_score", type=float, default=0.35)
    rec.add_argument("--expect", type=int, default=None)
    rec.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    cal = sub.add_parser("calibrate", help="打开截图标定工具")
    cal.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    srv = sub.add_parser("serve", help="启动 HTTP 服务")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8765)
    srv.add_argument("--quiet", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd is None:
        ap.print_help()
        return 0

    if args.cmd == "serve":
        from .server import serve
        serve(args.host, args.port, args.quiet)
        return 0

    if args.cmd in ("recognize", "calibrate"):
        # 截图识别是独立的 vision 包，这里只是给个统一入口，按需导入
        import os
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            from vision import cli as vision_cli
        except ImportError as exc:
            print("✗ 截图识别需要 vision 包（需要 Pillow 和 numpy）：%s" % exc,
                  file=sys.stderr)
            return 2
        if args.cmd == "calibrate":
            return vision_cli.main(["calibrate"])
        argv = ["recognize", args.image]
        if args.pack:
            argv += ["--pack", args.pack]
        if args.layout:
            argv += ["--layout", args.layout]
        if args.analyze:
            argv += ["--analyze", "--ruleset", args.ruleset,
                     "--turn", str(args.turn)]
            if args.wall is not None:
                argv += ["--wall", str(args.wall)]
        argv += ["--min-score", str(args.min_score)]
        if args.expect is not None:
            argv += ["--expect", str(args.expect)]
        if args.json:
            argv.append("--json")
        return vision_cli.main(argv)

    engine = Engine()

    if args.cmd == "rulesets":
        _print(engine.rulesets(), args.json)
        return 0

    if args.cmd == "equations":
        if args.json:
            print(json.dumps([{"id": i, "name": n, "impl": impl, "kind": k, "note": note}
                              for i, n, impl, k, note in EQUATIONS],
                             ensure_ascii=False, indent=2))
            return 0
        print("45 条方程 -> 实现对照（v%s，协议 %s）\n" % (__version__, PROTOCOL_VERSION))
        for i, name, impl, kind, note in EQUATIONS:
            print("#%02d [%s] %s" % (i, EQUATION_KINDS[kind], name))
            print("    实现: %s" % impl)
            print("    说明: %s" % note)
        return 0

    req = _build(args)
    try:
        if args.cmd == "analyze":
            out = engine.analyze(req)
        elif args.cmd == "score":
            out = engine.score(req)
        elif args.cmd == "discard":
            out = engine.discard(req)
        elif args.cmd == "prob":
            out = engine.probability(req)
        elif args.cmd == "ev":
            out = engine.ev(req)
        else:
            raise SystemExit("未知命令 %s" % args.cmd)
    except (ValueError, KeyError) as exc:
        print("✗ %s" % exc, file=sys.stderr)
        return 2

    _print(out, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
