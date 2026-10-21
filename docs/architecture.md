# 架构

一句话：**一个零依赖的计算内核 + 三套薄外壳 + 一个可选的图片识别层。**

```
                    ┌──────────────────────────────────────────┐
   输入              │  三种输入，归一成同一个 BoardState      │
                    │  ├─ 手打字符串  "123m456p789s11z"        │
                    │  ├─ 截图识别    vision/ → 牌索引列表      │
                    │  └─ HTTP JSON   别人程序发来的             │
                    └───────────────────┬──────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
   内核              │  mahjong_kernel/  （纯标准库，零依赖）    │
   (纯函数)          │                                          │
                    │  tiles → hand → shanten → ukeire         │
                    │                    ↓                     │
                    │              rulesets（可插拔）           │
                    │                ↓        ↓                │
                    │             score      probability       │
                    │                          ↓               │
                    │                     safety → ev          │
                    │                          ↓               │
                    │                     strategy             │
                    │                          ↓               │
                    │                     engine（门面）        │
                    └───────────────────┬──────────────────────┘
                                        ▼  dict in / dict out
                    ┌──────────────────────────────────────────┐
   外壳              │  api/cli.py    命令行                     │
                    │  api/server.py HTTP + 静态网页            │
                    │  webui/        单页界面（无构建）          │
                    │  desktop/      tkinter 窗口               │
                    └──────────────────────────────────────────┘
```

## 为什么内核必须零依赖

三个理由，按重要性排：

1. **可验证性**。如果内核依赖 numpy，那"这个向听数对不对"就多了一层
   "numpy 的数组语义"的不确定性。现在整个内核只依赖 Python 自己的
   `math` / `functools` / `dataclasses`，任何地方拷过去都能跑。
2. **可移植**。换台机器、换个 Python 3.9 的老环境，`git clone` 就能跑。
   CI 里有一条专门验证这点：导入内核后检查 `sys.modules` 里
   不能出现 numpy / PIL / cv2。
3. **可替换性**。识别层是唯一需要 Pillow + numpy 的地方，
   而且它只输出一个整数列表。想换成 OCR 或者神经网络，只动 `vision/`，
   内核一行不改。

## 数据流：一切都过 `BoardState`

内核对外的唯一入口是 `Engine`，它对外的唯一数据形态是 `dict`：

```python
report = Engine().analyze({
    "ruleset": "gb",
    "hand": "123m456p789s11z235m",
    "turn": 5,
    "wall_remaining": 60,
})
```

内部先把 dict 变成 `BoardState`（手牌 + 副露 + 场况），
再把它变成 `ScoreContext`（算分需要的那一份），
然后各模块只认这两个对象。

**为什么这样设计**：三种输入方式（手打、截图、HTTP）产生的都是
同一个 `BoardState`，所以"换一个前端"不需要碰内核一行代码。
`Engine` 里没有任何 `if 来自网页` 之类的分支。

## 规则集怎么插拔

`RuleSet` 抽象出七个东西：

| 抽象 | 作用 | 例子 |
|---|---|---|
| `tiles` | 牌池 | 四川没有字牌 → 108 张 |
| `allow_chi / peng / gang` | 允许的动作 | 四川不能吃 |
| `min_fan` | 起和番 | 国标 8 番、广东 0 番 |
| `detect_fans()` | 番种识别 | 国标 81 番全表 |
| `detect_special()` | 特殊和牌形 | 七对、十三幺、全不靠 |
| `resolve_exclusions()` | 不计原则 | "大三元不计箭刻" |
| `fan_to_points()` / `build_payments()` | 算分与付法 | 国标 底分×番；四川 2^番 |
| `validate_win()` | 和牌合法性 | 四川定缺、长沙"将有" |

加一套规则 = 加一个子类 + `register()`，CLI / HTTP / 界面全部自动支持。
不想写 Python 就用 `rulesets/custom.py` 的 JSON 声明式规则
（20 个条件谓词，够覆盖大部分地方规则）。

## 测试策略：每一块都用"另一个方法"验

这是这个项目花时间最多的地方。原则是：**不能自己验自己**。

| 模块 | 怎么验 |
|---|---|
| 向听 | 与**不剪枝的朴素 DFS** 在 4100 组随机手牌上逐一对齐 + 与和牌判定自洽 |
| 番种/点数 | 81 番种表条目数 + 典型手牌逐条手算对照 |
| 超几何 | 与 2 万次**暴力抽样**对齐 |
| 逐巡概率 | 解析 DP vs **链式蒙特卡洛**（两个独立实现算同一件事） |
| 识别 | 合成图随机 25 张截图 100% 正确 |
| 一致性 | 同一请求，**引擎直调 / CLI / HTTP** 三条路结果必须一致 |
| 界面 | `desktop/app.py --selftest` 真的建窗、跑两轮、渲染、销毁 |

"向听与不剪枝版本对齐"这一条抓出过真 bug：一个剪枝方向写反了，
3500 组里有 99 次算错（全部是把好牌算差）。细节在
[docs/math.md](math.md#剪枝二拿当前值当剪枝条件错的)。

## 性能特征

纯 Python 递归，没有 C 扩展、没有预计算表。实测（一台普通 Windows 机器）：

| 操作 | 耗时 |
|---|---|
| 单次向听（14 张，冷） | 0.7~1.5 ms |
| `analyze` 一屏报告（14 张，冷启动） | 0.17~0.3 s |
| `analyze` 同手牌（缓存命中） | 2~4 ms |
| 识别一张 14 张手牌的截图 | 7~18 ms |

冷启动八成时间花在"逐张弃牌分析"上：11~14 个候选 × 34 张有效牌
≈ 400 次向听递归。想让这一步更快，唯一的办法是把向听换成查表/位运算实现
（很多 C++ 实现能做到 10 μs 级），目前没做，因为两三百毫秒在交互上够用。

缓存用 `functools.lru_cache`，key 是 `(34 长度计数元组, 副露数)`。
好处是"连续微调手牌"这种交互几乎全是缓存命中。

## 目录职责对照

| 路径 | 职责 | 依赖 |
|---|---|---|
| `mahjong_kernel/tiles.py` | 34 牌索引、中英文解析、格式化 | 标准库 |
| `mahjong_kernel/hand.py` | `BoardState`：手牌 + 副露 + 场况 | 标准库 |
| `mahjong_kernel/meld.py` | 副露、和牌拆解、特殊和牌形判定 | 标准库 |
| `mahjong_kernel/shanten.py` | 向听数（三条公式） | 标准库 |
| `mahjong_kernel/ukeire.py` | 有效牌、弃牌候选 | 标准库 |
| `mahjong_kernel/rulesets/` | 规则抽象 + 四套内置 + JSON 自定义 | 标准库 |
| `mahjong_kernel/score.py` | 算分入口 | 标准库 |
| `mahjong_kernel/probability.py` | 超几何 + 逐巡马尔可夫链 | 标准库 |
| `mahjong_kernel/simulate.py` | 蒙特卡洛（两种策略） | 标准库 |
| `mahjong_kernel/safety.py` | 危险度、守备效率、振听判据 | 标准库 |
| `mahjong_kernel/ev.py` | 期望值、押引临界点、顺位期望 | 标准库 |
| `mahjong_kernel/strategy.py` | 逐张弃牌 EV 排序 | 标准库 |
| `mahjong_kernel/engine.py` | 门面：dict in / dict out | 标准库 |
| `mahjong_kernel/protocol.py` | 协议自描述 + 45 条方程对照 | 标准库 |
| `mahjong_kernel/api/` | CLI、HTTP | 标准库 |
| `webui/index.html` | 单页界面，无构建、无 CDN | 浏览器 |
| `desktop/app.py` | tkinter 窗口 | tkinter |
| `vision/` | 图片 → 牌索引（离线，不发网络请求） | Pillow + numpy |

## 有意为之的取舍

- **不做实时/抓屏**：见 [DISCLAIMER.md](../DISCLAIMER.md) 和 README 的"为什么不做的事"。
- **不做神经网络识别**：模板匹配在标定好的场景下足够准，而且**可解释**
  （每格有分数、有次高候选，认不准会明确报"不确定"而不是瞎猜）。
- **不做服务端/多用户**：HTTP 服务只监听 127.0.0.1，没有账号、没有数据库、
  没有上传。
- **不预计算查表**：会让仓库里多出几 MB 二进制文件，
  而当前性能对交互来说够用。
