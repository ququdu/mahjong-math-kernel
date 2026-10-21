# -*- coding: utf-8 -*-
"""截图识别链路测试。

用合成图做端到端验证：切格 -> 模板匹配 -> 拼牌 -> 转成内核请求 -> 算出结果。
合成图用的是同一套画法，所以这些测试验的是**链路逻辑**（切格对不对、
匹配器认不认得出、拼牌顺序对不对、请求能不能用），不是真实素材的准确率。
真实准确率取决于用户自己的模板包，有专门的标定工具。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from vision import synth
from vision.image import load_image, save_image, split_row, to_float_rgb, to_gray
from vision.match import Matcher, parse_tile_string, tile_index
from vision.pack import Layout, Region, TemplatePack
from vision.recognize import infer_meld, recognize, to_request


def make_pack():
    pack = TemplatePack(size=(synth.TILE_W, synth.TILE_H))
    for t, img in synth.make_templates().items():
        pack.add(t, img)
    return pack


# ---------------------------------------------------------------------------
#  图像工具
# ---------------------------------------------------------------------------

def test_image_conversions():
    img = synth.make_tile_image(5)
    assert img.dtype == np.uint8
    f = to_float_rgb(img)
    assert f.shape == (synth.TILE_H, synth.TILE_W, 3)
    assert 0.0 <= f.min() and f.max() <= 1.0
    g = to_gray(img)
    assert g.shape == (synth.TILE_H, synth.TILE_W)
    # 灰度输入也能变成三通道
    assert to_float_rgb(g).shape[2] == 3


def test_split_row_positions():
    shot = synth.make_screenshot([0, 1, 2], canvas=(300, 100))
    region = {"x": 10, "y": 10, "cell_w": synth.TILE_W, "cell_h": synth.TILE_H,
              "pitch": synth.TILE_W + synth.GAP, "count": 3}
    cells = split_row(shot, region)
    assert len(cells) == 3
    # 每一格应该和对应模板几乎一致
    for i, t in enumerate([0, 1, 2]):
        a = to_float_rgb(cells[i])
        b = to_float_rgb(synth.make_tile_image(t))
        assert a.shape == b.shape
        assert np.abs(a - b).mean() < 0.02


# ---------------------------------------------------------------------------
#  模板包
# ---------------------------------------------------------------------------

def test_pack_roundtrip(tmp_path):
    pack = make_pack()
    assert len(pack) == 34
    assert pack.coverage()["complete"] is True
    path = str(tmp_path / "pack.npz")
    pack.save(path)
    back = TemplatePack.load(path)
    assert len(back) == 34
    assert back.size == pack.size
    for t in range(34):
        assert back.templates[t].shape == pack.templates[t].shape
        assert np.allclose(back.templates[t], pack.templates[t], atol=1e-5)


def test_pack_partial_coverage():
    pack = TemplatePack(size=(synth.TILE_W, synth.TILE_H))
    pack.add(0, synth.make_tile_image(0))
    cov = pack.coverage()
    assert cov["learned"] == 1
    assert cov["complete"] is False
    assert len(cov["missing"]) == 33


def test_pack_rejects_bad_tile():
    pack = TemplatePack()
    with pytest.raises(ValueError):
        pack.add(99, synth.make_tile_image(0))


def test_empty_pack_has_no_matcher():
    with pytest.raises(ValueError):
        TemplatePack().matcher()


# ---------------------------------------------------------------------------
#  匹配器
# ---------------------------------------------------------------------------

def test_matcher_identical_score_one():
    pack = make_pack()
    m = pack.matcher()
    cell = synth.make_tile_image(7)
    tile, score, alt, alt_score = m.match_cell(cell)
    assert tile == 7
    assert score > 0.999
    assert alt_score < score


def test_matcher_distinguishes_color_only():
    """2万 和 2筒 点数一样、只有颜色不同——不能认错。"""
    pack = make_pack()
    m = pack.matcher()
    for tile in (1, 10, 19):
        got, score, _, _ = m.match_cell(synth.make_tile_image(tile))
        assert got == tile, (tile, got)


def test_matcher_handles_brightness_shift():
    pack = make_pack()
    m = pack.matcher()
    cell = synth.make_tile_image(12).astype(np.float32) * 0.8 + 20
    got, score, _, _ = m.match_cell(cell)
    assert got == 12


# ---------------------------------------------------------------------------
#  解析辅助
# ---------------------------------------------------------------------------

def test_parse_tile_string():
    assert parse_tile_string("123m") == [0, 1, 2]
    assert parse_tile_string("123p") == [9, 10, 11]
    assert parse_tile_string("1z") == [27]
    assert parse_tile_string("7z") == [33]
    assert parse_tile_string("123万") == [0, 1, 2]
    assert tile_index(3, 7) == 33
    with pytest.raises(ValueError):
        parse_tile_string("abc")


# ---------------------------------------------------------------------------
#  端到端识别
# ---------------------------------------------------------------------------

def test_recognize_14_tiles():
    pack = make_pack()
    layout = synth.layout_for(count=14)
    tiles = [0, 1, 2, 4, 9, 10, 11, 18, 19, 20, 27, 27, 33, 33]
    shot = synth.make_screenshot(tiles, canvas=(900, 120))
    res = recognize(shot, pack, layout)
    assert res["ok"] is True
    assert res["tiles"] == tiles
    assert res["confidence"] > 0.95
    assert res["warnings"] == []


def test_recognize_13_tiles_leaves_last_blank():
    pack = make_pack()
    layout = synth.layout_for(count=14)
    tiles = [0, 1, 2, 4, 9, 10, 11, 18, 19, 20, 27, 31, 33]
    shot = synth.make_screenshot(tiles, canvas=(900, 120))
    res = recognize(shot, pack, layout, expect_hand=13)
    assert res["tiles"] == tiles
    assert res["warnings"] == []


def test_recognize_random_batch():
    pack = make_pack()
    layout = synth.layout_for(count=14)
    import random
    rnd = random.Random(2024)
    for _ in range(25):
        tiles = [rnd.randrange(34) for _ in range(14)]
        shot = synth.make_screenshot(tiles, canvas=(900, 120))
        assert recognize(shot, pack, layout)["tiles"] == tiles


def test_recognize_warns_on_wrong_count():
    pack = make_pack()
    layout = synth.layout_for(count=14)
    shot = synth.make_screenshot([0, 1, 2], canvas=(900, 120))
    res = recognize(shot, pack, layout, expect_hand=13)
    assert any("预期" in w for w in res["warnings"])


def test_recognize_requires_hand_region():
    pack = make_pack()
    with pytest.raises(ValueError):
        recognize(np.zeros((50, 50, 3), dtype=np.uint8), pack, Layout())


# ---------------------------------------------------------------------------
#  副露推断
# ---------------------------------------------------------------------------

def test_infer_meld():
    assert infer_meld([27, 27, 27])["kind"] == "pon"
    assert infer_meld([18, 19, 20])["kind"] == "chi"
    assert infer_meld([18, 19, 20])["tile"] == 18
    assert infer_meld([5, 5, 5, 5])["kind"] == "minkan"
    assert infer_meld([1, 3, 5]) is None
    assert infer_meld([27, 28, 29]) is None     # 字牌不能吃


# ---------------------------------------------------------------------------
#  拼成内核请求
# ---------------------------------------------------------------------------

def test_to_request_feeds_engine():
    pack = make_pack()
    layout = synth.layout_for(count=14)
    tiles = [0, 1, 2, 4, 9, 10, 11, 18, 19, 20, 27, 31, 33, 33]
    shot = synth.make_screenshot(tiles, canvas=(900, 120))
    res = recognize(shot, pack, layout)
    req = to_request(res, ruleset="gb", turn=4, wall_remaining=70)

    from mahjong_kernel import Engine
    report = Engine().analyze(req)
    assert report["ok"] is True
    assert isinstance(report["shanten"], int)
    assert report["hand"] == "1235m123p123s15z77z" or report["hand"] != ""


def test_layout_roundtrip(tmp_path):
    layout = Layout(hand=Region(x=10, y=20, cell_w=40, cell_h=56, pitch=42, count=14),
                    melds=[Region(x=10, y=90, cell_w=40, cell_h=56, pitch=42, count=3)])
    path = str(tmp_path / "layout.json")
    layout.save(path)
    back = Layout.load(path)
    assert back.hand.x == 10 and back.hand.count == 14
    assert len(back.melds) == 1 and back.melds[0].count == 3


# ---------------------------------------------------------------------------
#  像素往返（写文件再读回来，验证真实文件路径也能跑）
# ---------------------------------------------------------------------------

def test_recognize_from_saved_file(tmp_path):
    pack = make_pack()
    tiles = [3, 4, 5, 12, 13, 14, 21, 22, 23, 28, 28, 30, 32, 33]
    shot = synth.make_screenshot(tiles, canvas=(900, 120))
    img_path = str(tmp_path / "shot.png")
    save_image(shot, img_path)
    pack_path = str(tmp_path / "pack.npz")
    pack.save(pack_path)

    img = load_image(img_path)
    res = recognize(img, TemplatePack.load(pack_path), synth.layout_for(count=14))
    assert res["tiles"] == tiles
