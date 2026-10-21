# -*- coding: utf-8 -*-
"""截图识别命令行。

    python -m vision.cli recognize 截图.png                 # 只识别
    python -m vision.cli recognize 截图.png --analyze        # 识别完直接算
    python -m vision.cli recognize 截图.png --ruleset sichuan --turn 5 --analyze
    python -m vision.cli calibrate                           # 打开标定工具
    python -m vision.cli selftest                            # 合成图自测

输入永远是**你手上的一张图片文件**，程序不抓屏、不监听游戏窗口。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .pack import TILE_NAMES, Layout, TemplatePack, default_layout_path, default_pack_path


def _load(path_pack, path_layout):
    pack_path = path_pack or default_pack_path()
    layout_path = path_layout or default_layout_path()
    if not os.path.exists(pack_path):
        raise SystemExit(
            "还没有模板包：%s\n先跑 `python -m vision.cli calibrate` 学一遍模板。"
            % pack_path)
    if not os.path.exists(layout_path):
        raise SystemExit(
            "还没有版面：%s\n先跑 `python -m vision.cli calibrate` 标一次位置。"
            % layout_path)
    return TemplatePack.load(pack_path), Layout.load(layout_path)


def cmd_recognize(args):
    from .image import load_image
    from .recognize import recognize, to_request

    pack, layout = _load(args.pack, args.layout)
    img = load_image(args.image)
    res = recognize(img, pack, layout, min_score=args.min_score,
                    expect_hand=args.expect)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("手牌  : %s" % " ".join(TILE_NAMES[t] for t in res["tiles"]))
        print("置信度: %.3f" % res["confidence"])
        for m in res["melds"]:
            print("副露  : %s %s" % (m["kind"], TILE_NAMES[m["tile"]]))
        for w in res["warnings"]:
            print("⚠ %s" % w)

    if args.analyze:
        from mahjong_kernel import Engine
        req = to_request(res, ruleset=args.ruleset, turn=args.turn,
                         wall_remaining=args.wall)
        report = Engine().analyze(req)
        print()
        s = report["shanten"]
        print("向听  : %s" % ("已和牌" if s < 0 else ("听牌" if s == 0 else "%d 向听" % s)))
        if report.get("waits"):
            print("待牌  : %s" % ", ".join("%s×%d" % (k, v)
                                          for k, v in report["waits"].items()))
        if report.get("probability"):
            p = report["probability"]
            print("和牌率: %.1f%%   听牌率 %.1f%%" % (
                p["win_final"] * 100, p["tenpai_final"] * 100))
        if report.get("discards"):
            print("建议  :")
            for d in report["discards"][:5]:
                print("   打 %-4s 向听 %d 进张 %-3d 和牌率 %5.1f%% 期望值 %.2f" % (
                    d["name"], d["shanten"], d["ukeire"],
                    d["win_prob"] * 100, d["ev"]))
        if args.json:
            print()
            print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_calibrate(args):
    from .calibrate import main as cmain
    return cmain([])


def cmd_selftest(args):
    """用合成图端到端跑一遍，验证识别链路没坏。"""
    from . import synth
    from .recognize import recognize

    pack = TemplatePack(size=(synth.TILE_W, synth.TILE_H))
    for t, img in synth.make_templates().items():
        pack.add(t, img)
    layout = synth.layout_for(count=14)

    import random
    rnd = random.Random(args.seed)
    bad = 0
    for _ in range(args.rounds):
        tiles = [rnd.randrange(34) for _ in range(14)]
        shot = synth.make_screenshot(tiles, canvas=(900, 120))
        got = recognize(shot, pack, layout)["tiles"]
        if got != tiles:
            bad += 1
            print("✗ 期望 %s 实际 %s" % (tiles, got))
    if bad:
        print("SELFTEST FAILED: %d/%d 张截图识别错" % (bad, args.rounds))
        return 1
    print("SELFTEST OK: %d 张随机截图全部识别正确" % args.rounds)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vision", description="麻将截图识别")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    r = sub.add_parser("recognize", help="识别一张截图")
    r.add_argument("image")
    r.add_argument("--pack", default=None, help="模板包路径")
    r.add_argument("--layout", default=None, help="版面路径")
    r.add_argument("--min-score", dest="min_score", type=float, default=0.35)
    r.add_argument("--expect", type=int, default=None, help="预期手牌张数")
    r.add_argument("--analyze", action="store_true", help="识别完直接算一遍")
    r.add_argument("--ruleset", default="gb")
    r.add_argument("--turn", type=int, default=1)
    r.add_argument("--wall", type=int, default=None)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    sub.add_parser("calibrate", help="打开标定工具").add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS)

    s = sub.add_parser("selftest", help="合成图端到端自测")
    s.add_argument("--rounds", type=int, default=30)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    args = ap.parse_args(argv)
    if args.cmd is None:
        ap.print_help()
        return 0
    if args.cmd == "recognize":
        return cmd_recognize(args)
    if args.cmd == "calibrate":
        return cmd_calibrate(args)
    if args.cmd == "selftest":
        return cmd_selftest(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
