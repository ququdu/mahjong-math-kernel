# 麻将数学内核 · Mahjong Math Kernel

[![tests](https://github.com/ququdu/mahjong-math-kernel/actions/workflows/tests.yml/badge.svg)](https://github.com/ququdu/mahjong-math-kernel/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)

> 🔒 **这个仓库已停止维护**：v1.0.0 的内容是完整的（132 个测试全绿、文档齐全），
> 之后不再更新。代码仍可自由使用、修改、分发（MIT）。有疑问欢迎看
> [docs/faq.md](docs/faq.md) 和 [docs/math.md](docs/math.md)，但 issue 可能不会回。
>
> 🔒 **Archived / unmaintained**: v1.0.0 is feature-complete. No further updates.
> Still free to use under MIT. Issues may go unanswered.

> ⚠️ **定位声明**：这是一个**数学/概率教学与离线研究工具**。
> 不抓屏、不监听游戏窗口、不自动操作、不做任何形式的代打或线上对战辅助，
> 也不涉及任何金钱、下注或胜率变现。详见 [DISCLAIMER.md](DISCLAIMER.md)。
>
> ⚠️ **Scope**: a math/probability study tool for offline analysis.
> No screen capture, no game-process hooks, no automation, no real-money use.

**麻将能不能被算出来？能算的部分比大多数人想的多，能算的边界也比视频里说的窄。**

这个仓库把麻将里**真能算**的东西算出来，把**只能用模型**的东西明确标成模型，
并且每一条都用测试或蒙特卡洛交叉验证过。

📐 **数学推导与反例：[docs/math.md](docs/math.md)** ← 建议先看这个

```bash
python -m mahjong_kernel.api.cli analyze "123m456p789s11z235m" --turn 5 --wall 60
```

```
手牌  : 122335m456p789s11z
向听  : 听牌
待牌  : 1m×3, 2m×2, 4m×4, 5m×3, 东×3
进张  : 15 张   效率 0.123
和牌率: 到末巡 26.9%   听牌率 86.0%   期望摸牌 8.1 巡
攻守  : 进攻（收益/风险 = 3.26 > 阈值 1.00）

弃牌建议（按期望值排序）:
  打    向听   进张     和牌率      放铳率      期望值      说明
  东    1    15      44.8%    13.7%   19.88
  3m   1    25      55.9%    28.4%   17.59
  5m   0    7       58.8%    40.0%   12.00    打后听牌
```

注意最后两行：打 5m 立刻听牌、和牌率更高，但**期望值反而更低**——
因为 5m 是危险牌（放铳率 40%），而 东 只掉一层向听却安全得多。
这就是内核不拿「进张数」直接排名的原因。

### 文档

| 文档 | 讲什么 |
|---|---|
| [docs/math.md](docs/math.md) | 公式推导、反例手牌、哪些精确哪些是模型 ← **建议先读** |
| [docs/architecture.md](docs/architecture.md) | 模块分层、数据流、测试策略、性能特征 |
| [docs/faq.md](docs/faq.md) | 常见问题（含「这算不算外挂/赌博」） |
| [DISCLAIMER.md](DISCLAIMER.md) | 定位与边界声明 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 怎么加规则集、怎么提 PR |
| [CHANGELOG.md](CHANGELOG.md) | 版本记录 |

---

## 三个值得一读的结论

**① 向听数的剪枝方向反了，会只往一个方向错。**
把「当前值」当剪枝条件的写法看起来天经地义，但它剪掉的正是能变好的分支。
实测 3500 组随机手牌里 **99 次算错（2.8%）**，而且**全部是把好牌算差**、
一次也没有反向。反例手牌 `111m259m79p22345s`：正确 2 向听，反向剪枝给 3。
→ [推导](docs/math.md#1-向听数一条公式和两种剪枝)

**② 和牌概率的分母不能用「剩余牌山」。**
有效牌数是按「所有没看到的牌」数的，两边分母必须一致。用剩余牌山会让命中率
在尾盘虚高：同一手牌解析算出 76%，真实蒙特卡洛只有 6.7%。
→ [推导](docs/math.md#2-超几何分布进张数为什么不能直接当和牌率)

**③ 中国麻将没有「振听」，所以日麻那套安全牌理论直接搬过来是错的。**
国标/四川/广东里打过的牌别人照样可以和，「现物=绝对安全」不成立。
唯一绝对安全的只有「四张都在场上」。
→ [推导](docs/math.md#5-中国麻将的安全度不能照搬日麻)

---

## 安装

内核本身**零依赖**，只要 Python 3.9+：

```bash
git clone https://github.com/ququdu/mahjong-math-kernel
cd mahjong-math-kernel
python -m mahjong_kernel.api.cli analyze "123m456p789s11z235m" --turn 5
```

想当库用（`pip install` 后可以直接 `import mahjong_kernel`）：

```bash
pip install -e .                 # 只要内核（零依赖）
pip install -e ".[vision]"       # 带离线截图识别（Pillow + numpy）
```

装完会多两个命令：`mahjong-kernel` 和 `mahjong-vision`。

---

## 它长什么样

三条入口，同一个内核：**网页界面**、**桌面窗口**、**命令行 + HTTP 接口**，
另加一个**截图识别**（丢一张截图自动认出手牌再算）。

http 服务默认零依赖，内核本身只用标准库。

### 1. 网页界面

```
双击  启动-网页.bat
```

或者手动：

```bash
python -m mahjong_kernel.api.server --port 8765
# 浏览器打开 http://127.0.0.1:8765/
```

### 2. 桌面窗口（tkinter，不用浏览器）

```
双击  启动-桌面.bat
```

或者：

```bash
python desktop/app.py
```

### 3. 命令行

```bash
# 一屏报告：向听 / 待牌 / 进张 / 和牌率 / 弃牌建议 / 攻守
python -m mahjong_kernel.api.cli analyze "123m456p789s11z235m" --turn 5 --wall 60

# 只算番与点数
python -m mahjong_kernel.api.cli score "123m456p789s111z22z" --win 2z

# 只算弃牌（按期望值排序）
python -m mahjong_kernel.api.cli discard "123m456p789s11z235m"

# 只算逐巡和牌概率
python -m mahjong_kernel.api.cli prob "123m456p7s11z23s" --wall 60

# 只算期望值（可带四家点数算顺位期望）
python -m mahjong_kernel.api.cli ev "123m456p7s11z23s" --scores 25000,25000,25000,25000

# 列出规则集 / 列出 45 条方程的实现对照
python -m mahjong_kernel.api.cli rulesets
python -m mahjong_kernel.api.cli equations
```

输出示例（加 `--json` 拿原始结构）：

```
手牌  : 122335m456p789s11z
向听  : 听牌
待牌  : 1m×3, 2m×2, 4m×4, 5m×3, 东×3
进张  : 15 张   效率 0.123
和牌率: 到末巡 26.9%   听牌率 86.0%   期望摸牌 8.1 巡
攻守  : 进攻（收益/风险 = 3.26 > 阈值 1.00）

弃牌建议（按期望值排序）:
  打    向听   进张     和牌率      放铳率      期望值      说明
  东    1    15      44.8%    13.7%   19.88
  3m   1    25      55.9%    28.4%   17.59
  5m   0    7       58.8%    40.0%   12.00    打后听牌
```

注意最后两行：打 5m 立刻听牌、和牌率更高，但**期望值反而更低**——
因为 5m 是危险牌（放铳率 40%），而 东 只掉一层向听却安全得多。
这就是内核不拿「进张数」直接排名的原因。

---

## 它能算什么

| 类别 | 内容 |
|---|---|
| 牌型 | 标准型向听（含副露）、七对子、十三幺、全不靠、七星不靠、组合龙 |
| 进张 | 有效牌逐张剩余数（扣掉已见牌）、牌效率、进张期望 |
| 番种 | 国标 81 番种全表 + 不计原则；四川血战；广东推倒和；JSON 自定义 |
| 点数 | 各规则算分、起和番、支付明细（点炮 / 自摸各家） |
| 概率 | 超几何分布、逐巡累积和牌率、听牌率、流局率、期望摸牌数 |
| 安全 | 危险度（壁 / 牌种 / 巡目 / 筋）、守备效率、最安全弃牌 |
| 决策 | 三情形期望值、押引判据、和了放铳均衡点、顺位期望、逐张弃牌 EV 排序 |
| 识别 | 截图 → 手牌 / 副露 → 直接算（自带标定工具） |
| 对外 | 内核门面、CLI、HTTP JSON API、JSON 声明式自定义规则 |

---

## 目录结构

```
麻将数学内核/
├── mahjong_kernel/          内核（纯 stdlib）
│   ├── tiles.py             34 牌索引、中英文解析
│   ├── hand.py              BoardState（手牌 + 副露 + 场况）
│   ├── meld.py              副露、和牌拆解、特殊和牌形
│   ├── shanten.py           向听数（标准 / 七对 / 十三幺）
│   ├── ukeire.py            有效牌、弃牌候选
│   ├── rulesets/            base / gb / sichuan / guangdong / custom
│   ├── score.py             算分入口
│   ├── probability.py       概率模型（超几何 + 逐巡 DP）
│   ├── simulate.py          蒙特卡洛（两种策略）
│   ├── safety.py            危险度 / 振听 / 守备效率
│   ├── ev.py                期望值 / 押引 / 顺位
│   ├── strategy.py          选牌决策（EV 排序）
│   ├── engine.py            门面：analyze/score/discard/probability/ev
│   ├── protocol.py          协议自描述 + 45 条方程对照表
│   └── api/                 CLI、HTTP 服务
├── webui/index.html         网页界面（单页，无构建）
├── desktop/app.py           桌面界面（tkinter）
├── vision/                  截图识别（Pillow + numpy）
│   ├── match.py             NCC 模板匹配
│   ├── pack.py              模板包 + 版面
│   ├── recognize.py         截图 → 牌 → 内核请求
│   ├── calibrate.py         标定工具（学模板 + 标位置）
│   └── synth.py             合成测试图
├── tests/                   132 个测试
├── vision_data/             模板包 / 版面 / 演示截图
├── 启动-网页.bat / 启动-桌面.bat
└── README.md
```

---

## 规则集

内置 4 套，`--ruleset` 或界面下拉切换：

| key | 名称 | 要点 |
|---|---|---|
| `gb` | 国标麻将 | 144 张、81 番种、8 番起和、底分 8、点炮者全付 |
| `sichuan` | 四川血战到底 | 108 张（无字牌）、定缺、不能吃、番数按 `2^番` 折算 |
| `changsha` | 长沙麻将 | 108 张、不能吃、雀头必须是 2/5/8 |
| `guangdong` | 广东推倒和 | 136 张、无番缚（鸡胡也能和）、番数按 `2^番` |

### 加一套自己的规则

不想写 Python 就直接用 JSON（`POST /api/rulesets` 注册即可）：

```json
{
  "key": "my_local",
  "name": "我们那儿的规矩",
  "min_fan": 1,
  "base_points": 1,
  "has_honors": true,
  "allow_chi": true,
  "fan_mode": "exponential",
  "fans": [
    {"name": "碰碰胡", "fan": 2, "when": {"all_triplets": true}},
    {"name": "清一色", "fan": 4, "when": {"pure_suit": true}},
    {"name": "混一色", "fan": 3, "when": {"half_flush": true}},
    {"name": "自摸",   "fan": 1, "when": {"tsumo": true}},
    {"name": "边张",   "fan": 1, "when": {"wait_in": ["边张"]}}
  ],
  "exclusions": {"清一色": ["混一色"]}
}
```

可用条件：`all_triplets` `all_sequences` `pure_suit` `half_flush` `all_honors`
`no_honors` `no_terminals` `all_yaochu` `min_rank_ge` `max_rank_le`
`suit_count_eq` `dragon_triplets_ge` `wind_triplets_ge`
`concealed_triplets_ge` `kan_count_ge` `pair_in` `pair_is_dragon` `wait_in`
`tsumo` `menzen` `ron` `after_kan` `last_tile` `chankan`。

要更复杂的规则就写一个 `RuleSet` 子类，然后在 `rulesets/__init__.py` 里
`register()`——引擎、CLI、HTTP、界面全部自动支持，不用改别的地方。

---

## 45 条方程 → 实现对照

你给的那份文档列了 45 条「方程」，但这 45 条**不是一个层级的东西**：
有的是组合数学（能精确算），有的是经验公式（比如「门前清自摸概率 =
和牌率 × 0.35」，那个 0.35 是拍的），还有几条在国标 / 四川 / 广东里
根本不存在（立直、宝牌、符数、满贯）。

所以每一条都标了类型：

* **精确** — 组合数学 / 规则定义直接算出来，可复现、可验证
* **模型** — 有明确假设，参数全部暴露，可以按桌风调
* **不适用** — 这套规则里不存在，只保留给日麻或变体

统计：**18 条精确 / 18 条模型 / 9 条不适用**。
完整表格（也可以 `python -m mahjong_kernel.api.cli equations`，
或界面里点「方程对照」页签）：

| # | 方程 | 实现 | 类型 | 说明 |
|---|---|---|---|---|
| 1 | 向听数计算方程 | `shanten.shanten` | 精确 | 标准型 shanten = 8 - 2*面子 - 搭子 - 雀头，用带安全剪枝的 DFS 精确求解；七对子 / 十三幺另算。已用不剪枝参照实现在 4100 组随机手牌上逐一对齐。 |
| 2 | 和牌概率累积方程 | `probability.win_probability_curve` | 模型 | 逐巡马尔可夫链：状态=进张级数，转移=有效牌命中率（密度 K/未见面牌数）。不是简单连乘，因为向听会一级级推进。 |
| 3 | 摸牌概率分布（超几何） | `probability.hypergeometric_at_least_one` | 精确 | P = 1 - C(N-K,n)/C(N,n)，连乘实现避免大组合数溢出。 |
| 4 | 牌效率函数 | `ev.tile_efficiency` | 精确 | 有效牌张数 / 未见面牌数 = 下一巡直接命中率。定义精确，分母用未见面牌数（不是剩余牌山，否则会虚高）。 |
| 5 | 立直和牌率微分方程 | `probability.expr_decay_win_curve` | 不适用 | dp/dt = -λp 的解析解。中国麻将没有立直，保留给日麻扩展。 |
| 6 | 进张期望方程 | `ev.expected_ukeire_value` | 精确 | 按剩余张数加权平均有效牌数。 |
| 7 | 门前清自摸概率 | `probability.analyse_probability` | 模型 | 门清手牌的听牌/自摸概率由同一条逐巡链给出（不再用'和牌率×0.35'那种凭空系数）。 |
| 8 | 牌山剩余模型 | `hand.BoardState.wall_size` | 精确 | 136 - 53（开局发出）- 4×巡目；也可以直接传 wall_remaining 覆盖。 |
| 9 | 巡目和牌率函数 | `probability.turn_win_rate` | 模型 | h(t) = h0·exp(-λt)，经验衰减曲线，λ 可调。 |
| 10 | 流局概率方程 | `probability.draw_game_probability` | 精确 | 1 - P(和牌)，忽略途中流局等特殊结束。 |
| 11 | 期望摸牌数 | `probability.expected_draws` | 精确 | 几何分布均值 = 未见面牌数 / 有效牌数。 |
| 12 | 听牌概率方程 | `probability.win_probability_curve['tenpai']` | 模型 | 与第 2 条同一条链的听牌累积概率。 |
| 13 | 最优和牌策略 | `strategy.analyse_discards` | 模型 | 对每张候选算 EV = P(和)×和牌点 - P(铳)×失点，按 EV 排序。不是只看进张——进张一样时危险度可能差一倍。 |
| 14 | 期待顺位计算 | `ev.placement_ev` | 模型 | 把四家点数当独立正态，抽样排名求期望顺位。只有一个可调参数 sigma。 |
| 15 | 攻守判断准则 | `ev.attack_defense_judge` | 模型 | 收益/风险比 > 阈值则进攻，阈值可调。 |
| 16 | 期望值方程 | `ev.expected_value` | 精确 | EV = P(和)·和点 - P(铳)·失点 + P(流)·流局价值。式子精确，输入是模型量。 |
| 17 | 立直期望值 | `ev.riichi_ev` | 不适用 | 含供托与宣言成本。中国麻将无立直，保留给「报听」类变体。 |
| 18 | 副露和牌率 | `engine.Engine.analyze（传 melds）` | 模型 | 把副露计入面子数后，同一条逐巡链自动适用于副露手。 |
| 19 | 打点期望方程 | `strategy.estimate_win_points` | 模型 | 已听牌时把每个待牌真的算一遍分再加权（这一档精确）；未听牌时用规则典型分值 × 牌型潜力系数（这一档是启发式）。 |
| 20 | 场况价值函数 | `ev.placement_ev` | 模型 | 顺位期望 + 点数 + 安全性，多目标折算成同一个 EV。 |
| 21 | 振听判据 | `safety.is_furiten` | 不适用 | 待牌与弃牌交集非空。国标/四川/广东都没有振听规则，所以危险度模型里**没有**「现物=绝对安全」这一条（那是日麻的）。 |
| 22 | 危险度函数 | `safety.DangerModel.tile_danger` | 模型 | 壁（剩几张）× 牌种（中张最险）× 巡目 × 筋折扣。全部参数可调。 |
| 23 | 守备效率 | `safety.defense_efficiency` | 精确 | 手牌中危险度低于阈值的张数占比。定义精确，输入是模型量。 |
| 24 | 押引基准 | `ev.attack_defense_judge` | 模型 | 同第 15 条，给的是可调的阈值判断。 |
| 25 | 巡目价值函数 | `probability.turn_value` | 模型 | decay^turn，越晚局面价值越低（因为可操作轮数变少）。 |
| 26 | 和了放铳均衡 | `ev.equilibrium_check` | 精确 | 边际收益 = 边际风险的临界点：P(铳)/P(和) ≤ 和牌点/失点。 |
| 27 | 期望值积分方程 | `ev.integral_ev` | 精确 | Σ rate(t)·discount^t，把每巡瞬时收益折现累加。 |
| 28 | 番数计算方程 | `rulesets.*.detect_fans` | 精确 | 国标 81 番种全表 + 不计原则；四川/广东/自定义各有自己的番种表。对每一种合法拆解都跑一遍，取番数最高者。 |
| 29 | 符数计算方程 | `不适用（中国麻将不计符）` | 不适用 | 国标按番数档位计分，没有符数。 |
| 30 | 和牌点数公式 | `rulesets.base.RuleSet.fan_to_points` | 精确 | 国标：底分 8 × 番数；四川/广东：2^番（可封顶）。 |
| 31 | 满贯判定条件 | `rulesets.gb.FAN_TABLE` | 不适用 | 中国麻将用番种档位（88/64/48/32/…）而不是「满贯/跳满」，没有这层换算。 |
| 32 | 役满概率方程 | `见 probability + simulate（概率由模型给出）` | 模型 | 役满概率本质上是模型量，用蒙特卡洛估比解析式更靠谱；这里给的是同一套概率框架，不编造「十种役满概率求和」这种式子。 |
| 33 | 立直一发概率 | `probability.ippatsu_probability` | 不适用 | 立直相关，中国麻将无。 |
| 34 | 门清自摸概率 | `同第 7 条` | 模型 | 同第 7 条。 |
| 35 | 抢杠概率方程 | `probability.chankan_probability` | 模型 | 对手加杠率 × 对手听牌率 × 杠牌正好是待牌，三个参数都可调。 |
| 36 | 海底摸月概率 | `probability.haitei_probability` | 模型 | 只在最后一巡成立，概率取 1/总巡数。 |
| 37 | 岭上开花概率 | `probability.rinshan_probability` | 模型 | 基础概率 × (1 + 0.5×杠数)，封顶 1。 |
| 38 | 一发概率函数 | `同第 33 条` | 不适用 | 立直相关。 |
| 39 | 宝牌期望方程 | `probability.dora_expectation` | 不适用 | 国标无宝牌（花牌另计）。保留给日麻扩展。 |
| 40 | 里宝牌期望 | `probability.ura_dora_expectation` | 不适用 | 同上。 |
| 41 | 平和概率函数 | `rulesets.gb.GBRuleSet._add_wait_fans` | 精确 | 给定手牌判定平和（四顺子 + 非役牌雀头 + 两面待牌），是确定性判定不是概率。 |
| 42 | 七对子概率 | `rulesets.*.detect_special` | 精确 | 给定手牌判定七对（国标/血战允许四张相同算两对），并识别龙七对。 |
| 43 | 国士无双概率 | `meld.is_kokushi` | 精确 | 国标叫十三幺，确定性判定 + 88 番。 |
| 44 | 番缚条件 | `rulesets.base.RuleSet.min_fan` | 精确 | 国标 8 番起和；番数不足直接判不能和。 |
| 45 | 综合和了期待方程 | `engine.Engine.analyze['score']` | 精确 | 把所有番种点数按概率加权，输出番种明细、总番、总点数、支付明细。 |

---

## 建模假设（重要）

**下面这几处是模型而不是定理**，参数都在代码里，不同意可以自己调：

| 模型 | 假设 | 参数在哪 |
|---|---|---|
| 逐巡和牌率 | 有效牌在「未见面牌」里均匀分布，单巡命中率 = 有效牌数 ÷ 未见面牌数；各级进张近似不变 | `probability.win_probability_curve(chain, wall, unseen=…)` |
| 听牌→和牌 | 听牌后按平均 10 张待牌估算 | `strategy.ASSUMED_TENPAI_WAITS` |
| 危险度 | 基础危险度(牌种) × 剩余张数折扣 × 巡目抬升 × 筋折扣 | `safety.DangerModel` 全部字段 |
| 对手听牌率 | 第 1 巡 10%，每巡 +5%，封顶 85% | `strategy.TENPAI_BASE / TENPAI_GROWTH / TENPAI_CAP` |
| 未听牌的打点 | 规则典型分值 × 牌型潜力系数（清一色 1.6 / 字牌 2.0 / 多对子 1.2 …） | `strategy.PROMISE_RULES` |
| 顺位期望 | 四家最终点数当独立正态抽样排名 | `ev.placement_probabilities(mu, sigma)` |
| 巡目价值 | `decay^turn`，默认 0.90 | `probability.turn_value(decay=…)` |

已经听牌时**打点是精确算的**：把每个待牌都真的算一遍番点数，再按剩余张数
加权。`strategy.estimate_win_points` 返回的第二个值是 `exact` 标记。

### 和原始草稿的主要差异

原始素材是一份 45 条方程的清单 + 一段 Python 草稿。下面是对着草稿逐行核对后的差异：

1. **向听**：草稿用的是**不剪枝的完整 DFS**，逻辑正确，但一次 14 张手牌要跑
   几百毫秒。这里加了「剩余牌张数能给多少分」的安全上界剪枝，并用 4100 组随机
   手牌与不剪枝版本逐一对齐。
   （剪枝方向很容易搞反，我自己第一版就反了，见 [docs/math.md](docs/math.md#剪枝二拿当前值当剪枝条件错的)）
2. **命中率分母**：草稿把「剩余牌山」当分母，尾盘会把命中率放大到接近 100%。
   有效牌数是按「所有没看到的牌」算的，两边分母必须一致。
3. **凭空系数**：草稿里 `menzen_tsumo_prob = win_prob * 0.35`、
   `rinshan_probability = 0.08 * (1 + kan*0.5)` 这类是拍出来的数；这里要么
   从同一条概率链推出来，要么明确标成「模型 + 可调参数 + 可调范围」。
4. **番种**：草稿的 `detect_yaku` 覆盖十几个役种，且没有处理「不计」关系；
   这里是国标 81 番种全表 + 不计表，对每一种合法拆解都跑一遍取番数最高者。
5. **点数支付**：草稿的自摸用 `ceil100(base) × 3` 近似，没有区分子家与亲家
   各自付多少；这里按规则分别计算并分别进位。
6. **符数**：草稿不区分明刻/暗刻（统一按暗刻算）、也不区分明杠/暗杠；
   这里区分。
7. **振听/安全牌**：草稿里有 `is_furiten`，但日麻那套「现物=安全」在国标/
   四川/广东里不成立（没有振听规则），所以危险度模型是重写的，不是搬过来的。

---

## 截图识别

目标不是「自动打牌」，是**丢一张截图进去，不用手打牌**。

### 先标定一次（学模板 + 标位置）

```bash
python -m vision.cli calibrate
```

1. **打开截图**：任意一张能看清手牌的截图（同一款游戏、同一个窗口大小）。
2. **框手牌区**：在图上拖一个矩形框住手牌那一排，把「格子数」填成实际张数。
   在下面输入框里按顺序输入这排牌（`123m456p789s11z22z`），点「学习模板」
   ——工具会切出这些格子，按你写的牌名存成模板。换个花色再学一两张，
   34 张很快就齐（有 34 张牌谱图的话一次就能学完）。
3. **存模板包 + 存版面**。之后就不用再标了。

模板包和版面存在 `vision_data/`，跟着项目走。

### 之后丢截图就能识别

```bash
# 只识别
python -m vision.cli recognize 截图.png

# 识别 + 直接给建议
python -m vision.cli recognize 截图.png --analyze --turn 5 --wall 60

# 或走统一入口
python -m mahjong_kernel.api.cli recognize 截图.png --analyze --turn 5
```

输出：

```
手牌  : 1m 2m 3m 1p 2p 3p 1s 2s 3s 东 东 发 发 中
置信度: 1.000

向听  : 听牌
待牌  : 东×2, 发×2
和牌率: 39.4%   听牌率 100.0%
建议  :
   打 中    向听 0 进张 4   和牌率  39.4% 期望值 14.85
   打 1m   向听 1 进张 12  和牌率  39.4% 期望值 13.95
```

识别不出来时会给出具体警告（「有一格不太确定：最像 3m（0.41）」），
不会硬编一个结果骗你。

### 验证识别链路没坏

```bash
python -m vision.cli selftest --rounds 30
```

用合成图跑 30 张随机截图，全部认对才算通过。
`vision_data/demo_*` 是一套现成的演示素材（合成图 + 模板包 + 版面），
可以拿来先跑通流程：

```bash
python -m vision.cli recognize vision_data/demo_shot.png \
  --pack vision_data/demo_templates.npz \
  --layout vision_data/demo_layout.json --analyze
```

---

## HTTP 接口

启动服务后 `GET /api/protocol` 就是完整的自描述（字段、接口、45 条方程）。
界面右上角「接口自描述」也是它。

```bash
curl -X POST http://127.0.0.1:8765/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"ruleset":"gb","hand":"123m456p789s11z235m","turn":5,"wall_remaining":60}'
```

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/rulesets` | 列出规则集 |
| GET | `/api/protocol` | 协议自描述（含 45 条方程） |
| GET | `/api/equations` | 只要方程对照表 |
| POST | `/api/analyze` | 一屏报告 |
| POST | `/api/score` | 番种与点数 |
| POST | `/api/discard` | 弃牌候选（按 EV 排序） |
| POST | `/api/probability` | 逐巡和牌概率 |
| POST | `/api/ev` | 期望值与押引结论 |
| POST | `/api/rulesets` | 注册 JSON 自定义规则 |

请求字段（只有 `hand` 必需）：

| 字段 | 说明 |
|---|---|
| `hand` | 手牌，`123m456p789s11z` / `123万456筒789条东东` / `[0,1,2,…]` |
| `melds` | `[{"kind":"pon","tile":31}]`，kind = chi/pon/minkan/ankan/kakan |
| `turn` / `wall_remaining` | 巡目 / 牌山剩余 |
| `agari_tile` / `is_tsumo` | 和牌张 / 是否自摸 |
| `visible` | 手牌之外看到的牌（扣张、和绝张） |
| `self_discards` | 自己的弃牌（振听判断） |
| `deficiency_suit` | 四川定缺 `m` / `p` / `s` |
| `seat_wind` / `round_wind` / `flowers` | 自风 / 场风 / 花牌数 |
| `flags` | `is_last_tile` / `is_after_kan` / `is_chankan` |
| `scores` / `hero` | 四家点数 / 自己座位（算顺位期望） |

### 当库用

```python
from mahjong_kernel import Engine

engine = Engine()
report = engine.analyze({
    "ruleset": "gb",
    "hand": "123m456p789s11z235m",
    "turn": 5,
    "wall_remaining": 60,
})
print(report["shanten"], report["ukeire"])
for d in report["discards"][:3]:
    print(d["name"], d["ev"])
```

---

## 测试

```bash
python -m pytest tests/ -q
# 132 passed
```

测试不是「跑一遍看看输出啥」，关键的地方都有对照：

* **向听**：与不剪枝的朴素 DFS 在 4100 组随机手牌（13/14 张、1~3 副露）上
  逐一对齐；并与和牌判定自洽（向听 −1 ⟺ 能和，0 ⟺ 存在一张牌能和）
* **算分**：81 番种表条目数、典型手牌逐条手算对照
* **概率**：超几何分布 vs 2 万次暴力抽样；解析 DP vs 链式蒙特卡洛
  （30 组手牌零不一致）
* **识别**：合成图随机 25 张截图 100% 正确；13 张留空、亮度偏移也要认对
* **一致性**：同一请求，引擎直调 / CLI / HTTP 三条路结果必须一致
* **界面**：`desktop/app.py --selftest` 真的建窗口、跑两轮计算、渲染、销毁

---

## 已知限制（说清楚比藏着强）

* **截图识别是模板匹配**，不是通用 OCR。换游戏、换分辨率、换皮肤要重新标定；
  认不准会明确报「不确定」，不会瞎猜。
* **番种不计原则**按官方标注整理，少数冷门组合可能与各地裁判习惯不同；
  番种明细全部可见，可以自己核对改表。
* **国标花牌**按每张 1 番计入总分（官方口径），地方玩法不同改 `RuleSet` 即可。
* **顺位期望**用独立正态近似。真实局面四家点数强相关，这个模型偏乐观，
  但做攻守权衡够用，`sigma` 可调。
* **不做自动点击 / 代打**。识别只负责把屏幕上的牌读出来，决策和动手是你的。
* 向听是纯 Python 递归，单次约 1.5 ms；一张 14 张手牌的完整弃牌分析首次
  约 0.2~0.6 秒，之后走缓存是毫秒级。

---

## 关于这个项目

麻将是个被玄学包围的游戏：有人说"牌运"、有人说"感觉"、有人说"这手牌该拆"。
但这个游戏里有一大部分是**确定的**——向听差几步、有多少张有效牌、
和牌概率多少、打哪张期望值最高，这些都有唯一正确答案。

这个仓库就是把这些唯一正确答案算出来，并且**老老实实标注哪些不是唯一答案**。

- 从一份 45 条方程的清单出发（据说来自某个讲"麻将可以被算出来"的视频），
  逐条落到代码上，然后给每一条打上 `精确 / 模型 / 不适用` 的标签
  （见 `mahjong_kernel/protocol.py`，18 精确 / 18 模型 / 9 不适用）
- 每个"精确"的都写了测试和对照实验（向听 4100 组、概率 2 万次暴力抽样、
  解析 DP vs 蒙特卡洛）
- 每个"模型"的假设和参数都写在明面上，不同意可以自己调

**它想回答的问题不是"怎么赢钱"，而是"这个游戏里有多少是可以算的"。**

## 为什么不做的事（边界）

下面这些是**故意不做**的，不是没做完：

| 不做 | 原因 |
|---|---|
| 抓屏 / 实时监听游戏窗口 | 那是线上对战辅助（外挂），违反几乎所有平台的服务条款，法律风险也高 |
| 自动出牌 / 自动点击 / 托管 | 同上，而且会让工具从"分析"变成"代打" |
| 接游戏进程内存 / 读包 | 明确属于非法获取计算机信息系统数据那一类 |
| 金钱、筹码、下注、胜率变现 | 不碰赌博相关的一切 |
| 把牌局数据上传到任何地方 | 全本地运行，没有网络请求（除了你自己开的本地 HTTP 服务） |

识别功能的存在理由是"省得手打牌"，输入永远是你**手动提供的图片文件**：
自己截个图、存下来、丢进来算。它不看你屏幕。

## 依赖

| 部分 | 需要 |
|---|---|
| 内核 / 桌面版 / CLI / HTTP 服务 | Python 3.9+，纯标准库 |
| 网页版 | 任意现代浏览器 |
| 截图识别 | `Pillow`、`numpy` |

内核本身**不依赖任何第三方包**——这是刻意的，换台机器拷过去就能跑。
