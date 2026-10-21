# -*- coding: utf-8 -*-
"""引擎门面 / CLI / HTTP 服务 的一致性测试。

核心断言：同一个请求，**引擎直调**、**CLI**、**HTTP** 三条路的计算结果必须一致。
"""

import io
import json
import os
import sys
import threading
import urllib.request
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from mahjong_kernel import Engine, __version__
from mahjong_kernel.api import cli as cli_mod
from mahjong_kernel.api import server as server_mod
from mahjong_kernel.protocol import PROTOCOL_VERSION, describe

ENGINE = Engine()

HAND14 = "123m456p789s11z235m"
BASE_REQ = {"ruleset": "gb", "hand": HAND14, "turn": 5, "wall_remaining": 60}


# ---------------------------------------------------------------------------
#  Engine
# ---------------------------------------------------------------------------

def test_analyze_shape():
    r = ENGINE.analyze(BASE_REQ)
    for key in ("ok", "version", "ruleset", "state", "hand", "shanten",
                "is_tenpai", "waits", "ukeire", "probability", "discards", "advice"):
        assert key in r, key
    assert r["version"] == __version__
    assert isinstance(r["discards"], list) and r["discards"]


def test_analyze_agari_returns_score_only():
    r = ENGINE.analyze({"ruleset": "gb", "hand": "123m456p789s111z22z",
                        "agari_tile": "2z"})
    assert r["is_agari"] is True
    assert r["score"]["ok"] is True
    assert r["score"]["fan"] == 8


def test_analyze_blocked_agari_continues():
    """形状上和了但规则不允许（四川定缺）时，要继续给弃牌建议。"""
    r = ENGINE.analyze({"ruleset": "sichuan", "hand": "123m456m789m234p55s",
                        "deficiency_suit": "s", "turn": 3, "wall_remaining": 70})
    assert r.get("agari_blocked") is True
    assert r["discards"]
    assert r["discards"][0]["forced"] is True


def test_analyze_warns_on_illegal_input():
    r = ENGINE.analyze({"ruleset": "sichuan", "hand": "123m456m789m234p5z5z"})
    assert any("没有字牌" in w for w in r["warnings"])


def test_discard_ordered_by_ev():
    r = ENGINE.discard(BASE_REQ)
    evs = [d["ev"] for d in r["discards"]]
    assert evs == sorted(evs, reverse=True)
    assert r["advice"]["advice"] in ("进攻", "可以打，但留意危险牌", "弃和，优先打安全牌")


def test_probability_monotone():
    r = ENGINE.probability({"hand": "123m456p7s11z23s", "wall_remaining": 60})
    win = r["win_by_turn"]
    assert all(win[i] <= win[i + 1] + 1e-9 for i in range(len(win) - 1))
    assert 0.0 <= r["win_final"] <= 1.0
    assert 0.0 <= r["draw_probability"] <= 1.0


def test_ev_endpoint():
    r = ENGINE.ev({"hand": "123m456p7s11z23s", "wall_remaining": 60,
                   "scores": [25000, 25000, 25000, 25000], "hero": 0})
    assert "ev" in r and "should_push" in r
    assert r["placement"]["expected_ev"] is not None
    r2 = ENGINE.ev({"win_prob": 0.3, "deal_prob": 0.1,
                    "win_points": 100.0, "deal_points": 200.0})
    assert abs(r2["ev"] - (0.3 * 100 - 0.1 * 200)) < 1e-6


def test_rulesets_endpoint():
    r = ENGINE.rulesets()
    keys = {x["key"] for x in r["rulesets"]}
    assert {"gb", "sichuan", "changsha", "guangdong"} <= keys


def test_score_rejects_wrong_tile_count():
    r = ENGINE.score({"hand": "123m456p789s11z", "ruleset": "gb"})
    assert r["ok"] is False
    assert r["notes"]


def test_protocol_has_45_equations():
    d = describe()
    assert d["protocol"] == PROTOCOL_VERSION
    assert len(d["equations"]) == 45
    kinds = {e["kind"] for e in d["equations"]}
    assert kinds <= {"exact", "model", "n/a"}
    # 别把模型说成精确
    exact_count = sum(1 for e in d["equations"] if e["kind"] == "exact")
    assert 0 < exact_count < 45


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------

def run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli_mod.main(argv)
    return code, buf.getvalue()


def test_cli_json_matches_engine():
    code, out = run_cli(["--json", "analyze", HAND14, "--turn", "5", "--wall", "60"])
    assert code == 0
    cli_result = json.loads(out)
    engine_result = ENGINE.analyze(BASE_REQ)
    assert cli_result["shanten"] == engine_result["shanten"]
    assert cli_result["ukeire"] == engine_result["ukeire"]
    assert [d["name"] for d in cli_result["discards"]] == \
           [d["name"] for d in engine_result["discards"]]


def test_cli_human_output():
    code, out = run_cli(["analyze", HAND14, "--turn", "5", "--wall", "60"])
    assert code == 0
    assert "向听" in out and "弃牌建议" in out


def test_cli_score_command():
    code, out = run_cli(["score", "123m456p789s111z22z", "--win", "2z"])
    assert code == 0
    assert "8 番" in out


def test_cli_rulesets_and_equations():
    code, out = run_cli(["rulesets", "--json"])
    assert code == 0 and "sichuan" in out
    code, out = run_cli(["equations", "--json"])
    assert code == 0
    assert len(json.loads(out)) == 45


def test_cli_reports_bad_input():
    code, out = run_cli(["analyze", "123m9z"])
    assert code == 2


# ---------------------------------------------------------------------------
#  HTTP
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def http_server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % port
    httpd.shutdown()
    httpd.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_http_health_and_protocol(http_server):
    assert _get(http_server + "/api/health")["ok"] is True
    d = _get(http_server + "/api/protocol")
    assert len(d["equations"]) == 45


def test_http_analyze_matches_engine(http_server):
    got = _post(http_server + "/api/analyze", BASE_REQ)
    want = ENGINE.analyze(BASE_REQ)
    assert got["shanten"] == want["shanten"]
    assert got["ukeire"] == want["ukeire"]
    # 浮点用近似比较
    assert abs(got["probability"]["win_final"] - want["probability"]["win_final"]) < 1e-9
    assert [d["name"] for d in got["discards"]] == [d["name"] for d in want["discards"]]


def test_http_score_and_rulesets(http_server):
    r = _post(http_server + "/api/score",
              {"ruleset": "gb", "hand": "123m456p789s111z22z", "agari_tile": "2z"})
    assert r["ok"] and r["fan"] == 8
    r2 = _get(http_server + "/api/rulesets")
    assert {x["key"] for x in r2["rulesets"]} >= {"gb", "sichuan"}


def test_http_rejects_bad_json(http_server):
    req = urllib.request.Request(http_server + "/api/analyze", data=b"{oops",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20)
        assert False, "应当返回 400"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400


def test_http_unknown_route(http_server):
    try:
        _post(http_server + "/api/nope", {})
        assert False
    except urllib.error.HTTPError as exc:
        assert exc.code == 404


# ---------------------------------------------------------------------------
#  HTTP 截图识别（需要 vision 包 + 演示素材）
# ---------------------------------------------------------------------------

VISION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "vision_data")


@pytest.mark.skipif(not os.path.exists(os.path.join(VISION_DIR, "demo_shot.png")),
                    reason="没有演示素材")
def test_http_recognize_demo_shot(http_server):
    import base64

    with open(os.path.join(VISION_DIR, "demo_shot.png"), "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    got = _post(http_server + "/api/recognize", {
        "image": b64,
        "pack": os.path.join(VISION_DIR, "demo_templates.npz"),
        "layout": os.path.join(VISION_DIR, "demo_layout.json"),
    })
    assert got["ok"] is True
    assert got["tiles"] == [0, 1, 2, 9, 10, 11, 18, 19, 20, 27, 27, 32, 32, 33]
    assert got["request"]["hand"]

    # 识别结果直接能喂给 analyze
    report = _post(http_server + "/api/analyze", got["request"])
    assert report["ok"] is True
    assert isinstance(report["shanten"], int)


def test_http_recognize_reports_missing_pack(http_server):
    import base64

    tiny_png = base64.b64encode(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415408d763f8ffff3f0005fe02fea7d6a5a40000000049"
        "454e44ae426082")).decode()
    try:
        _post(http_server + "/api/recognize",
              {"image": tiny_png, "pack": "/no/such/pack.npz",
               "layout": "/no/such/layout.json"})
        assert False, "应当报错"
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode("utf-8"))
        assert exc.code == 400
        assert "模板包" in body["error"] or "教程" in body["error"] or "calibrate" in body["error"]
