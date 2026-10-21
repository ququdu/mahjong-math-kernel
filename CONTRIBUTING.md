# 贡献指南

先说清楚方向：这个项目的核心是**可验证的数学**，不是功能数量。
所以"加一个炫的功能"不如"证明现有的一条结论是对的"。

## 三条原则

1. **精确的东西必须有对照实验**。新增或修改任何数学计算，
   都要有一个"用另一个方法算同一件事"的测试。自己验自己不算。
2. **模型的东西必须标出来**。如果某个计算依赖假设（对手听牌率、危险度权重之类），
   把假设写在函数注释里，把参数暴露出来，并在 `protocol.py` 里标成 `model`。
3. **内核保持零依赖**。`mahjong_kernel/` 里不许 import 第三方包。
   需要 PIL/numpy 的东西放到 `vision/`。

## 开发环境

```bash
git clone https://github.com/ququdu/mahjong-math-kernel
cd mahjong-math-kernel

# 内核本身不需要装任何东西
python -m pytest tests -q

# 跑截图识别相关的测试需要这两个
pip install pillow numpy
```

## 提交前自查

```bash
python -m pytest tests -q          # 必须全绿
python desktop/app.py --selftest   # 桌面版必须能跑
python -m vision.cli selftest      # 改了识别就必跑
```

CI 还会额外检查：导入内核后 `sys.modules` 里不能出现 numpy / PIL / cv2。

## 想加一套地方规则？

最小的做法是用 JSON 声明式规则（不用写 Python）：

```python
from mahjong_kernel.rulesets import register_custom
register_custom({
    "key": "my_local",
    "name": "我们那儿的规矩",
    "min_fan": 1,
    "fans": [
        {"name": "碰碰胡", "fan": 2, "when": {"all_triplets": True}},
        {"name": "清一色", "fan": 4, "when": {"pure_suit": True}},
    ],
})
```

条件词表见 README 的"加一套自己的规则"，或者
`mahjong_kernel/rulesets/custom.py` 里的 `PREDICATES`。

要更复杂的（比如血战的"查叫"、某些地方的"百搭"），就写 `RuleSet` 子类，
放在 `rulesets/` 下，然后在 `rulesets/__init__.py` 注册。
记得顺手加测试：**至少一正一反两个例子**（一个能和的、一个不能和的）。

## 想加番种/役种？

1. 在对应 `rulesets/*.py` 的 `FAN_TABLE` 中加入名称与番数
2. 在 `detect_fans()` 里加判定
3. 如果它有"不计"关系，加到 `EXCLUSIONS`
4. 在 `tests/test_score.py` 里加一对正反例

## 改了 `docs/math.md` 里的数字？

请**真的跑一遍**再写。那份文档里所有数字都是实测的，
包括"3500 组里 99 次算错"这种。改数字要能给出复现命令。

## 提 Issue 时

- **逻辑算错**：给出完整手牌字符串（如 `123m456p789s11z235m`）+ 规则 + 你期望的结果
- **规则不符合你那边**：说明是哪个地区、具体哪条、能否给个手牌例子
- **识别不准**：不用发截图，发"哪一格最像什么、分数多少"就行
- **不要在 issue 里放大段真实游戏截图**（可能有个人信息）

## 不接受的东西

- 实时读屏 / 抓屏 / 进程注入 / 包分析
- 自动出牌 / 自动点击 / 托管
- 任何和赌博、下注、资金相关的东西

这些不是"还没做"，是**故意不做**，见 [DISCLAIMER.md](DISCLAIMER.md)。

## 许可

提交代码即表示同意以 MIT 协议发布。
