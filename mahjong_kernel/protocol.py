# -*- coding: utf-8 -*-
"""内核协议：请求字段、返回结构、以及「45 条方程」与实现的对照表。

为什么要把对照表放进代码
------------------------
你给的那份文档列了 45 条「方程」，但里面有一部分是**经验公式**（比如
「门前清自摸概率 = 和牌率 × 0.35」），不是从牌理推出来的。混在一起会让人
误以为整套东西都是精确的。

所以这里把每一条都标上 ``kind``：

* ``exact``  组合数学 / 规则定义直接算出来的，结果可复现、可验证
* ``model``  有明确假设的模型，参数全部暴露，可以按桌风调
* ``n/a``    这套规则（中国麻将）里不存在，只保留给日麻或变体
"""

from __future__ import annotations

PROTOCOL_VERSION = "1.0"

# ---------------------------------------------------------------------------
#  请求字段
# ---------------------------------------------------------------------------

REQUEST_FIELDS = {
    "ruleset": ("string", "gb / sichuan / changsha / guangdong / 自定义 key，默认 gb"),
    "hand": ("string", "手牌，如 '123m456p789s11z'、'123万456筒789条东东'；也可用 tiles 传索引数组"),
    "tiles": ("int[]", "手牌索引数组（0..33），与 hand 二选一"),
    "melds": ("array", "[{kind, tile}] 副露；kind = chi/pon/minkan/ankan/kakan"),
    "flowers": ("int", "花牌张数（国标每张 1 番）"),
    "seat_wind": ("string|int", "自风：east/south/west/north 或 1..4"),
    "round_wind": ("string|int", "场风：同上"),
    "is_dealer": ("bool", "是否庄家"),
    "turn": ("int", "当前第几巡（从 1 开始）"),
    "wall_remaining": ("int", "牌山剩余张数；不传则按巡目推算"),
    "self_discards": ("string|int[]", "自己的弃牌（振听判断用）"),
    "visible": ("string|int[]", "手牌之外看得到的牌（弃牌/副露/牌河）"),
    "dora_indicators": ("string|int[]", "宝牌指示牌（扩展用）"),
    "deficiency_suit": ("string|int", "四川定缺花色：m/p/s"),
    "agari_tile": ("string|int", "和牌张（算番必须）"),
    "is_tsumo": ("bool", "是否自摸"),
    "flags": ("object", "偶然役：is_last_tile / is_after_kan / is_chankan"),
    "win_prob": ("float", "ev 接口：直接给和牌概率"),
    "deal_prob": ("float", "ev 接口：直接给放铳概率"),
    "win_points": ("float", "ev 接口：和牌点数"),
    "deal_points": ("float", "ev 接口：放铳失点"),
    "threshold": ("float", "ev 接口：押引阈值"),
    "scores": ("int[]", "ev 接口：四家点数（算顺位期望）"),
    "hero": ("int", "ev 接口：自己座位下标（0 起）"),
}

# ---------------------------------------------------------------------------
#  45 条方程 -> 实现
# ---------------------------------------------------------------------------

EQUATIONS = [
    (1, "向听数计算方程", "mahjong_kernel.shanten.shanten", "exact",
     "标准型 shanten = 8 - 2*面子 - 搭子 - 雀头，用带安全剪枝的 DFS 精确求解；"
     "七对子 / 十三幺另算。已用不剪枝参照实现在 4100 组随机手牌上逐一对齐。"),
    (2, "和牌概率累积方程", "mahjong_kernel.probability.win_probability_curve", "model",
     "逐巡马尔可夫链：状态=进张级数，转移=有效牌命中率（密度 K/未见面牌数）。"
     "不是简单连乘，因为向听会一级级推进。"),
    (3, "摸牌概率分布（超几何）", "mahjong_kernel.probability.hypergeometric_at_least_one", "exact",
     "P = 1 - C(N-K,n)/C(N,n)，连乘实现避免大组合数溢出。"),
    (4, "牌效率函数", "mahjong_kernel.ev.tile_efficiency", "exact",
     "有效牌张数 / 未见面牌数 = 下一巡直接命中率。定义精确，分母用未见面牌数"
     "（不是剩余牌山，否则会虚高）。"),
    (5, "立直和牌率微分方程", "mahjong_kernel.probability.expr_decay_win_curve", "n/a",
     "dp/dt = -λp 的解析解。中国麻将没有立直，保留给日麻扩展。"),
    (6, "进张期望方程", "mahjong_kernel.ev.expected_ukeire_value", "exact",
     "按剩余张数加权平均有效牌数。"),
    (7, "门前清自摸概率", "mahjong_kernel.probability.analyse_probability", "model",
     "门清手牌的听牌/自摸概率由同一条逐巡链给出（不再用'和牌率×0.35'那种凭空系数）。"),
    (8, "牌山剩余模型", "mahjong_kernel.hand.BoardState.wall_size", "exact",
     "136 - 53（开局发出）- 4×巡目；也可以直接传 wall_remaining 覆盖。"),
    (9, "巡目和牌率函数", "mahjong_kernel.probability.turn_win_rate", "model",
     "h(t) = h0·exp(-λt)，经验衰减曲线，λ 可调。"),
    (10, "流局概率方程", "mahjong_kernel.probability.draw_game_probability", "exact",
     "1 - P(和牌)，忽略途中流局等特殊结束。"),
    (11, "期望摸牌数", "mahjong_kernel.probability.expected_draws", "exact",
     "几何分布均值 = 未见面牌数 / 有效牌数。"),
    (12, "听牌概率方程", "mahjong_kernel.probability.win_probability_curve['tenpai']", "model",
     "与第 2 条同一条链的听牌累积概率。"),
    (13, "最优和牌策略", "mahjong_kernel.strategy.analyse_discards", "model",
     "对每张候选算 EV = P(和)×和牌点 - P(铳)×失点，按 EV 排序。"
     "不是只看进张——进张一样时危险度可能差一倍。"),
    (14, "期待顺位计算", "mahjong_kernel.ev.placement_ev", "model",
     "把四家点数当独立正态，抽样排名求期望顺位。只有一个可调参数 sigma。"),
    (15, "攻守判断准则", "mahjong_kernel.ev.attack_defense_judge", "model",
     "收益/风险比 > 阈值则进攻，阈值可调。"),
    (16, "期望值方程", "mahjong_kernel.ev.expected_value", "exact",
     "EV = P(和)·和点 - P(铳)·失点 + P(流)·流局价值。式子精确，输入是模型量。"),
    (17, "立直期望值", "mahjong_kernel.ev.riichi_ev", "n/a",
     "含供托与宣言成本。中国麻将无立直，保留给「报听」类变体。"),
    (18, "副露和牌率", "mahjong_kernel.engine.Engine.analyze（传 melds）", "model",
     "把副露计入面子数后，同一条逐巡链自动适用于副露手。"),
    (19, "打点期望方程", "mahjong_kernel.strategy.estimate_win_points", "model",
     "已听牌时把每个待牌真的算一遍分再加权（这一档精确）；"
     "未听牌时用规则典型分值 × 牌型潜力系数（这一档是启发式）。"),
    (20, "场况价值函数", "mahjong_kernel.ev.placement_ev", "model",
     "顺位期望 + 点数 + 安全性，多目标折算成同一个 EV。"),
    (21, "振听判据", "mahjong_kernel.safety.is_furiten", "n/a",
     "待牌与弃牌交集非空。国标/四川/广东都没有振听规则，"
     "所以危险度模型里**没有**「现物=绝对安全」这一条（那是日麻的）。"),
    (22, "危险度函数", "mahjong_kernel.safety.DangerModel.tile_danger", "model",
     "壁（剩几张）× 牌种（中张最险）× 巡目 × 筋折扣。全部参数可调。"),
    (23, "守备效率", "mahjong_kernel.safety.defense_efficiency", "exact",
     "手牌中危险度低于阈值的张数占比。定义精确，输入是模型量。"),
    (24, "押引基准", "mahjong_kernel.ev.attack_defense_judge", "model",
     "同第 15 条，给的是可调的阈值判断。"),
    (25, "巡目价值函数", "mahjong_kernel.probability.turn_value", "model",
     "decay^turn，越晚局面价值越低（因为可操作轮数变少）。"),
    (26, "和了放铳均衡", "mahjong_kernel.ev.equilibrium_check", "exact",
     "边际收益 = 边际风险的临界点：P(铳)/P(和) ≤ 和牌点/失点。"),
    (27, "期望值积分方程", "mahjong_kernel.ev.integral_ev", "exact",
     "Σ rate(t)·discount^t，把每巡瞬时收益折现累加。"),
    (28, "番数计算方程", "mahjong_kernel.rulesets.*.detect_fans", "exact",
     "国标 81 番种全表 + 不计原则；四川/广东/自定义各有自己的番种表。"
     "对每一种合法拆解都跑一遍，取番数最高者。"),
    (29, "符数计算方程", "不适用（中国麻将不计符）", "n/a",
     "国标按番数档位计分，没有符数。"),
    (30, "和牌点数公式", "mahjong_kernel.rulesets.base.RuleSet.fan_to_points", "exact",
     "国标：底分 8 × 番数；四川/广东：2^番（可封顶）。"),
    (31, "满贯判定条件", "mahjong_kernel.rulesets.gb.FAN_TABLE", "n/a",
     "中国麻将用番种档位（88/64/48/32/…）而不是「满贯/跳满」，没有这层换算。"),
    (32, "役满概率方程", "见 probability + simulate（概率由模型给出）", "model",
     "役满概率本质上是模型量，用蒙特卡洛估比解析式更靠谱；"
     "这里给的是同一套概率框架，不编造「十种役满概率求和」这种式子。"),
    (33, "立直一发概率", "mahjong_kernel.probability.ippatsu_probability", "n/a",
     "立直相关，中国麻将无。"),
    (34, "门清自摸概率", "同第 7 条", "model", "同第 7 条。"),
    (35, "抢杠概率方程", "mahjong_kernel.probability.chankan_probability", "model",
     "对手加杠率 × 对手听牌率 × 杠牌正好是待牌，三个参数都可调。"),
    (36, "海底摸月概率", "mahjong_kernel.probability.haitei_probability", "model",
     "只在最后一巡成立，概率取 1/总巡数。"),
    (37, "岭上开花概率", "mahjong_kernel.probability.rinshan_probability", "model",
     "基础概率 × (1 + 0.5×杠数)，封顶 1。"),
    (38, "一发概率函数", "同第 33 条", "n/a", "立直相关。"),
    (39, "宝牌期望方程", "mahjong_kernel.probability.dora_expectation", "n/a",
     "国标无宝牌（花牌另计）。保留给日麻扩展。"),
    (40, "里宝牌期望", "mahjong_kernel.probability.ura_dora_expectation", "n/a",
     "同上。"),
    (41, "平和概率函数", "mahjong_kernel.rulesets.gb.GBRuleSet._add_wait_fans", "exact",
     "给定手牌判定平和（四顺子 + 非役牌雀头 + 两面待牌），是确定性判定不是概率。"),
    (42, "七对子概率", "mahjong_kernel.rulesets.*.detect_special", "exact",
     "给定手牌判定七对（国标/血战允许四张相同算两对），并识别龙七对。"),
    (43, "国士无双概率", "mahjong_kernel.meld.is_kokushi", "exact",
     "国标叫十三幺，确定性判定 + 88 番。"),
    (44, "番缚条件", "mahjong_kernel.rulesets.base.RuleSet.min_fan", "exact",
     "国标 8 番起和；番数不足直接判不能和。"),
    (45, "综合和了期待方程", "mahjong_kernel.engine.Engine.analyze['score']", "exact",
     "把所有番种点数按概率加权，输出番种明细、总番、总点数、支付明细。"),
]

EQUATION_KINDS = {
    "exact": "精确（组合数学/规则定义直接算）",
    "model": "模型（有明确假设，参数可调）",
    "n/a": "本规则集不适用（日麻专属或该国规则无此概念）",
}


def describe():
    """返回协议自描述（给 UI / 第三方对接用）。"""
    from . import __version__
    from .rulesets import list_rulesets

    return {
        "protocol": PROTOCOL_VERSION,
        "kernel_version": __version__,
        "request_fields": {k: {"type": t, "desc": d} for k, (t, d) in REQUEST_FIELDS.items()},
        "endpoints": {
            "analyze": "一屏报告：向听/听牌/进张/概率/番点/弃牌建议/攻守",
            "score": "只算番种与点数",
            "discard": "只算弃牌候选（按 EV 排序）",
            "probability": "只算逐巡和牌概率曲线",
            "ev": "只算期望值与押引结论",
            "rulesets": "列出全部规则集",
            "protocol": "本自描述",
            "health": "健康检查",
        },
        "rulesets": list_rulesets(),
        "equations": [
            {"id": i, "name": n, "impl": impl, "kind": k, "note": note}
            for (i, n, impl, k, note) in EQUATIONS
        ],
        "equation_kinds": EQUATION_KINDS,
    }


def equation_table():
    """给 README / 界面用的纯文本对照表。"""
    lines = []
    for i, name, impl, kind, note in EQUATIONS:
        lines.append("#%02d [%s] %s\n    -> %s\n    %s" % (i, kind, name, impl, note))
    return "\n".join(lines)
