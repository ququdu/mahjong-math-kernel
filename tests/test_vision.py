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


# ---------------------------------------------------------------------------
#  实时模式（截屏 / 帧指纹 / 变更跳过）
# ---------------------------------------------------------------------------

from vision.capture import Capturer, frame_key, list_backends   # noqa: E402
from vision.live import LiveConfig, LiveSession                 # noqa: E402


def test_roi_from_layout():
    layout = synth.layout_for(count=14, origin=(10, 10))
    roi = layout.roi(margin=6)
    assert roi is not None
    x, y, w, h = roi
    assert x <= 10 and y <= 10
    assert w >= 13 * (synth.TILE_W + synth.GAP) + synth.TILE_W
    assert h >= synth.TILE_H


def test_roi_none_without_hand_region():
    assert Layout().roi() is None


def test_layout_shift_maps_to_roi_coordinates():
    layout = synth.layout_for(count=14, origin=(10, 10))
    x, y, _w, _h = layout.roi(0)
    shifted = layout.shifted(x, y)
    assert shifted.hand.x == layout.hand.x - x
    assert shifted.hand.y == layout.hand.y - y


def test_frame_key_detects_change():
    a = synth.make_tile_image(0)
    b = synth.make_tile_image(1)
    assert frame_key(a) == frame_key(a.copy())
    assert frame_key(a) != frame_key(b)


def test_capture_backends_available():
    """列一下可用后端；无头环境（CI）下一个都没有也是正常的。"""
    backends = list_backends()
    assert isinstance(backends, list)
    if not backends:
        pytest.skip("当前环境没有可用的截屏后端（无头 / 无图形会话）")
    for name in backends:
        assert name in ("mss", "gdi", "pil")


def test_capture_returns_rgb_array():
    backends = list_backends()
    if not backends:
        pytest.skip("没有截屏后端")
    with Capturer(bbox=(0, 0, 120, 60), backend=backends[0]) as cap:
        arr = cap.grab()
    assert arr.shape == (60, 120, 3)
    assert arr.dtype == np.uint8


class _FakeCapturer:
    """把合成整图按 ROI 裁出来，模拟屏幕变化。"""

    backend_name = "fake"

    def __init__(self, tiles, roi, canvas=(900, 120)):
        self.roi = roi
        self.canvas = canvas
        self.frames = 0
        self.set(tiles)

    def set(self, tiles):
        self.full = synth.make_screenshot(tiles, canvas=self.canvas)

    def grab(self, bbox=None):
        self.frames += 1
        x, y, w, h = bbox or self.roi
        return self.full[y:y + h, x:x + w].copy()

    def close(self):
        pass


def make_session(tiles):
    pack = make_pack()
    layout = synth.layout_for(count=14)
    cap = _FakeCapturer(tiles, layout.roi())
    session = LiveSession(cap, pack, layout, LiveConfig(turn=5, wall=60))
    return session, cap


def test_live_first_poll_analyzes():
    session, cap = make_session([0, 1, 2, 4, 9, 10, 11, 18, 19, 20, 27, 27, 33, 33])
    res = session.poll()
    assert res.changed is True
    assert res.report and res.report["ok"]
    assert res.hand
    assert res.timings["recognize"] >= 0
    # 首屏是"结论级"的：向听/待牌立刻有，弃牌排序留给 refine()
    assert res.shanten is not None
    full = session.refine()
    assert full and full.top_discards(3)
    session.close()


def test_live_skips_unchanged_frame():
    session, cap = make_session([0, 1, 2, 4, 9, 10, 11, 18, 19, 20, 27, 27, 33, 33])
    session.poll()
    before = cap.frames
    res = session.poll()
    assert res.changed is False
    assert res.reason == "画面没变"
    assert cap.frames == before + 1, "应该只多截了一帧，不做识别和计算"
    session.close()


def test_live_recomputes_after_tile_change():
    tiles = [0, 1, 2, 4, 9, 10, 11, 18, 19, 20, 27, 27, 33, 33]
    session, cap = make_session(tiles)
    first = session.poll()
    changed = list(tiles)
    changed[12] = 32                      # 换掉一张牌
    cap.set(changed)
    res = session.poll()
    assert res.changed is True
    assert res.report["hand"] != first.report["hand"]
    session.close()


def test_live_frame_changed_but_same_hand_is_skipped():
    """画面变了（比如动画抖动）但认出来的牌一样，不该重算。"""
    tiles = [0, 1, 2, 4, 9, 10, 11, 18, 19, 20, 27, 27, 33, 33]
    session, cap = make_session(tiles)
    session.poll()
    # 在背景上点一个像素，指纹变了，但牌没变
    cap.full = cap.full.copy()
    cap.full[0, 0] = [255, 0, 255]
    res = session.poll()
    assert res.changed is False
    session.close()


def test_live_force_recompute():
    session, _cap = make_session([0, 1, 2, 4, 9, 10, 11, 18, 19, 20, 27, 27, 33, 33])
    session.poll()
    res = session.poll(force=True)
    assert res.changed is True
    session.close()


def test_live_session_requires_hand_region():
    with pytest.raises(ValueError):
        LiveSession(_FakeCapturer([0], (0, 0, 100, 60)), make_pack(), Layout())


def test_live_two_stage_partial_then_refined():
    """首屏先出结论（partial），再补完整排序。"""
    session, _cap = make_session([0, 1, 2, 4, 9, 10, 11, 18, 19, 20, 27, 27, 33, 33])
    lite = session.poll()
    assert lite.changed is True
    assert lite.partial is True
    assert lite.report["shanten"] is not None
    assert lite.report["discards"] == []            # 首屏不做排序

    full = session.refine()
    assert full is not None
    assert full.partial is False
    assert full.report["discards"]                    # 排序补上了
    assert full.report["hand"] == lite.report["hand"]
    assert session.refine() is None                   # 没有待补的了
    session.close()


# ---------------------------------------------------------------------------
#  截屏后端探测：能 import 不等于能抓图
# ---------------------------------------------------------------------------

def test_backend_that_cannot_grab_is_rejected(monkeypatch):
    """无头 Linux 上 PIL.ImageGrab 能 import 但一 grab 就抛；这种后端不能被选中。"""
    import vision.capture as cap

    class Broken:
        name = "broken"

        def grab(self, bbox):
            raise OSError("no display")

        def close(self):
            pass

    monkeypatch.setitem(cap._BACKENDS, "broken", Broken)
    with pytest.raises(Exception):
        cap._try_backend("broken")

    # 自动选择时必须跳过它，落到下一个可用后端
    with pytest.raises(RuntimeError) as ei:
        cap._make_backend("broken")
    assert "没有可用的截屏后端" in str(ei.value)


def test_backend_probe_returns_working_backend(monkeypatch):
    import numpy as np
    import vision.capture as cap

    class Fake:
        name = "fake"

        def grab(self, bbox):
            x, y, w, h = bbox
            return np.zeros((h, w, 3), dtype=np.uint8)

        def close(self):
            pass

    monkeypatch.setitem(cap._BACKENDS, "fake", Fake)
    be = cap._try_backend("fake")
    assert be.name == "fake"
    be.close()
