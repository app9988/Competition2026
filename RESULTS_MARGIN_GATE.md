# 实测结果记录 · Margin Gate 版本

> 官方评测器：`techjam-conversational-search/evaluator/local_evaluator.py`
> 数据集：公开 200 会话（`data/public_set.jsonl`）
> 被测 agent：`solution/src/agent.py`（参考实现 + 本分支的 Top-1 领先幅度门控）
> 方法与推导见 [`TECHJAM_MARGIN_GATE_ENHANCEMENT.md`](TECHJAM_MARGIN_GATE_ENHANCEMENT.md)

---

## 1. 总分对照

| 配置 | Technical Score | Hit@10 | MRR | MTTC | Efficiency |
|---|---|---|---|---|---|
| 参考实现（general，`TJ_MARGIN` 未设） | 0.958850 | 1.000 | 0.97083 | 2.62 | 0.838 |
| **本版本（general + `TJ_MARGIN=1`）** | **0.961550** | **1.000** | **0.97083** | **2.48** | **0.852** |
| 冲分备选（mirror + `TJ_MARGIN=1`） | 0.964650 | 1.000 | 0.98083 | 2.48 | 0.852 |

增益 **+0.0027** 全部来自 Efficiency（MTTC 2.62 → 2.48），MRR 零损失。

---

## 2. 本版本各场景明细（general + `TJ_MARGIN=1`）

| 场景 | n | Hit@10 | MRR | MTTC |
|---|---|---|---|---|
| buying | 80 | 1.000 | 0.98333 | 2.12 |
| browsing | 80 | 1.000 | 0.95625 | 2.35 |
| intent_override | 30 | 1.000 | 0.96667 | 3.60 |
| boundary | 10 | 1.000 | 1.00000 | 3.10 |
| **全体** | **200** | **1.000** | **0.97083** | **2.48** |

buying / browsing 的 MTTC 相对参考实现下降（2.29 → 2.12、2.52 → 2.35），即领先幅度门控提前发布的直接效果；intent_override（3.60）与 boundary（3.10）受场景机制约束（覆写发生在第 3–4 轮、边界拒答浪费一轮），非门控可改善。

---

## 3. 复现命令

```bash
# 把 solution/src/agent.py 复制到官方仓库 starter/agent.py，仓库根目录执行：
TJ_MARGIN=1 python -m evaluator.local_evaluator \
    --catalog data/catalog.jsonl --dataset data/public_set.jsonl
# 预期 recommended_technical_score = 0.961550
```

依赖：Python 3.10+，无第三方库，无网络调用。评测确定性——每次运行结果一致。

---

## 4. 门控门槛消融（`TJ_MARGIN` 扫描）

| `TJ_MARGIN` | Score | MRR | MTTC | Efficiency |
|---|---|---|---|---|
| 关闭 | 0.958850 | 0.97083 | 2.62 | 0.838 |
| 2 | 0.959450 | 0.97083 | 2.59 | 0.841 |
| **1（选用）** | **0.961550** | **0.97083** | **2.48** | **0.852** |
| 0.5 | 0.959800 | 0.96100 | 2.42 | 0.858 |

`MARGIN < 1` 开始出现误发（MRR 从 0.97083 掉到 0.961），故 **1 为 MRR 零损失下的最优点**。

---

*记录时间：2026-08-29（Asia/Taipei）*
