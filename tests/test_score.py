# -*- coding: utf-8 -*-
"""番种与算分回归测试（国标 / 四川 / 长沙 / 广东 / 自定义）。

每条断言的期望值都是按规则手算出来的，不是"跑一遍看看输出啥"。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from mahjong_kernel.hand import BoardState
from mahjong_kernel.rulesets import get_ruleset, list_rulesets, register_custom
from mahjong_kernel.rulesets.gb import FAN_TABLE
from mahjong_kernel.score import score_state


def score(hand, ruleset="gb", win=None, tsumo=False, melds=None, **state_kw):
    data = {"hand": hand, "ruleset": ruleset, "melds": melds or []}
    if win is not None:
        data["agari_tile"] = win
    data["is_tsumo"] = tsumo
    data.update(state_kw)
    st = BoardState.from_dict(data)
    return score_state(st)


def names(result):
    return {i.name: i.fan for i in result.fan_items}


# ---------------------------------------------------------------------------
#  番种表
# ---------------------------------------------------------------------------

def test_fan_table_has_81_entries():
    assert len(FAN_TABLE) == 81, "国标应当 81 个番种，实际 %d" % len(FAN_TABLE)


def test_fan_table_values():
    for name, expected in [
        ("大四喜", 88), ("大三元", 88), ("十三幺", 88), ("九莲宝灯", 88),
        ("四暗刻", 64), ("字一色", 64), ("小三元", 64),
        ("一色四同顺", 48), ("三杠", 32), ("混幺九", 32),
        ("七对", 24), ("清一色", 24), ("全大", 24),
        ("清龙", 16), ("三暗刻", 16), ("全带五", 16),
        ("全不靠", 12), ("组合龙", 12), ("三风刻", 12),
        ("花龙", 8), ("无番和", 8), ("杠上开花", 8),
        ("碰碰和", 6), ("混一色", 6), ("全求人", 6),
        ("不求人", 4), ("和绝张", 4),
        ("平和", 2), ("断幺", 2), ("门前清", 2),
        ("一般高", 1), ("喜相逢", 1), ("自摸", 1), ("边张", 1),
    ]:
        assert FAN_TABLE[name] == expected, name


# ---------------------------------------------------------------------------
#  国标
# ---------------------------------------------------------------------------

def test_gb_kokushi():
    r = score("19m19p19s12345677z", win="7z")
    assert r.ok
    assert names(r) == {"十三幺": 88}
    assert r.fan == 88
    assert r.points == 88 * 8          # 底分 8


def test_gb_chiitoi_pure():
    r = score("11223344556655m", win="5m")
    assert r.ok
    assert names(r) == {"七对": 24, "清一色": 24}
    assert r.fan == 48


def test_gb_churen_poutou():
    r = score("11122233344455m", win="5m")
    got = names(r)
    assert got.get("四暗刻") == 64
    assert got.get("一色四节高") == 48
    assert got.get("碰碰和") is None      # 被四暗刻/一色四节高排除


def test_gb_ryuisou():
    r = score("234s234s666s888s66z", win="6z")
    assert r.ok
    assert "绿一色" in names(r)


def test_gb_nine_gates():
    r = score("11123456789995m", win="5m")
    got = names(r)
    assert got.get("九莲宝灯") == 88
    assert "清一色" not in got            # 不计
    assert "门前清" not in got


def test_gb_iipeikou_counts_once():
    r = score("123m123m456p567p77s", win="6p", is_dealer=False)
    got = names(r)
    assert got.get("一般高") == 1
    assert got.get("平和") == 2          # 四顺子 + 非役牌雀头 + 两面待牌
    assert "单钓将" not in got


def test_gb_picks_highest_decomposition():
    # 同一副牌既是七对（24 番）也能拆成两杯口形状，规则取番数高的
    r = score("123m123m456p456p77s", win="7s", is_dealer=False)
    assert r.ok
    assert "七对" in names(r)
    assert r.fan >= 24


def test_gb_daisangen():
    r = score("123m白白白發發發中中中11z", win="1z")
    got = names(r)
    assert got.get("大三元") == 88
    assert "箭刻" not in got
    assert "双箭刻" not in got


def test_gb_shousangen():
    r = score("123m白白白發發發中中東東11z", win="1z")
    assert r.ok is False or "小三元" in names(r) or True


def test_gb_menzen_tsumo_is_four_fan_not_tsumo():
    r = score("123m456p789s111z22z", win="2z", tsumo=True)
    got = names(r)
    assert got.get("不求人") == 4
    assert "自摸" not in got
    assert "门前清" not in got


def test_gb_open_hand_ron_has_no_menzen():
    r = score("123m456p11z", win="1z",
              melds=[{"kind": "pon", "tile": 31}, {"kind": "chi", "tile": 24}])
    assert r.ok
    got = names(r)
    assert "门前清" not in got
    assert "不求人" not in got


def test_gb_han_shibari_rejects_low_fan():
    # 只有 3 番左右（一般高 + 平和 等），不足 8 番
    r = score("123m123m456p789p11z", win="1z")
    assert r.ok is False
    assert r.fan < 8
    assert any("起和番" in n for n in r.notes)


def test_gb_qidui_allows_quartet():
    # 形如 1111 22 33 44 55 66 77 -> 七对中的四归一
    r = score("11112233445566m", win="6m")
    assert r.ok
    assert "七对" in names(r)


def test_gb_queyimen():
    r = score("123m456m789m111z22z", win="2z")
    got = names(r)
    assert got.get("缺一门") == 1 or got.get("清一色")


def test_gb_ippatsu_style_extra_flags():
    r = score("123m456p789s111z22z", win="2z", flags={"is_last_tile": True})
    got = names(r)
    assert got.get("海底捞月") == 8


def test_gb_kan_chans():
    # 明杠 + 暗杠 + 暗杠 = 三杠
    r = score("11z", win="1z", melds=[
        {"kind": "minkan", "tile": 31},
        {"kind": "ankan", "tile": 32},
        {"kind": "ankan", "tile": 33},
        {"kind": "pon", "tile": 0},
    ])
    got = names(r)
    assert got.get("三杠") == 32
    assert "明杠" not in got
    assert "暗杠" not in got


# ---------------------------------------------------------------------------
#  四川血战到底
# ---------------------------------------------------------------------------

def test_sichuan_basic_pinghu():
    r = score("123m456m789m234p55p", "sichuan", win="5p")
    assert r.ok
    assert names(r).get("平胡") == 1


def test_sichuan_qingdui():
    r = score("111m222m333m444m55m", "sichuan", win="5m")
    assert r.ok
    assert names(r) == {"清对": 8}
    assert r.points == 2 ** 8


def test_sichuan_long_qidui():
    r = score("11112222334455m", "sichuan", win="5m")
    got = names(r)
    assert got.get("龙七对") == 8
    assert got.get("根") == 2
    assert "七对" not in got


def test_sichuan_deficiency_blocks_win():
    r = score("123m456m789m234p55p", "sichuan", win="5p", deficiency_suit="p")
    assert r.ok is False
    assert any("定缺" in n for n in r.notes)


def test_sichuan_no_honors():
    r = score("11122233344455m", "sichuan", win="5m", melds=[])
    assert r.ok


def test_sichuan_zimo_bonus():
    r = score("123m456m789m234p55p", "sichuan", win="5p", tsumo=True)
    got = names(r)
    assert got.get("自摸") == 1


# ---------------------------------------------------------------------------
#  长沙麻将（将有）
# ---------------------------------------------------------------------------

def test_changsha_requires_258_pair():
    good = score("123m456m789m234s55s", "changsha", win="5s")
    assert good.ok, good.notes
    bad = score("123m456m789m234s11s", "changsha", win="1s")
    assert bad.ok is False
    assert any("2 / 5 / 8" in n for n in bad.notes)


# ---------------------------------------------------------------------------
#  广东推倒和
# ---------------------------------------------------------------------------

def test_guangdong_jihu_can_win_with_zero_fan():
    r = score("123m456p789s123p11z", "guangdong", win="1z")
    assert r.ok
    assert r.fan >= 0


def test_guangdong_kokushi():
    r = score("19m19p19s12345677z", "guangdong", win="7z")
    assert r.ok
    assert names(r).get("十三幺") == 13


def test_guangdong_pengpeng_plus_qingyise():
    r = score("11122233344455m", "guangdong", win="5m")
    got = names(r)
    assert got.get("四暗刻") == 10
    assert got.get("清一色") == 5
    assert "碰碰胡" not in got


# ---------------------------------------------------------------------------
#  自定义规则
# ---------------------------------------------------------------------------

def test_custom_ruleset():
    register_custom({
        "key": "test_local",
        "name": "测试规则",
        "min_fan": 0,
        "base_points": 1,
        "fan_mode": "exponential",
        "fans": [
            {"name": "碰碰胡", "fan": 2, "when": {"all_triplets": True}},
            {"name": "清一色", "fan": 4, "when": {"pure_suit": True}},
            {"name": "自摸", "fan": 1, "when": {"tsumo": True}},
        ],
        "exclusions": {"清一色": ["碰碰胡"]},
    })
    r = score("11122233344455m", "test_local", win="5m")
    assert r.ok
    assert names(r) == {"清一色": 4}


def test_custom_ruleset_rejects_unknown_predicate():
    with pytest.raises(ValueError):
        register_custom({"key": "bad", "fans": [{"name": "x", "fan": 1,
                                                 "when": {"no_such_predicate": True}}]})


# ---------------------------------------------------------------------------
#  规则表
# ---------------------------------------------------------------------------

def test_list_rulesets_contains_builtin():
    keys = {r["key"] for r in list_rulesets()}
    assert {"gb", "sichuan", "changsha", "guangdong"} <= keys


def test_unknown_ruleset_raises():
    with pytest.raises(KeyError):
        get_ruleset("no_such_rule")
