# 门控增强：Top-1 领先幅度提前发布（Margin Gate）

> 本文件为在参考实现（`solution/src/agent.py`）基础上的一处**增量改进**，与主设计文档 [`TECHJAM_SOLUTION_DESIGN.md`](TECHJAM_SOLUTION_DESIGN.md) 格式一致，独立记录，便于评审对照。
> 一句话：**把 Paper C 门控里明确提出、但原实现未落地的「Top-1 检索置信度」这一条补上，公开集 +0.0027 分，且 MRR 零损失。**

---

## 0. 执行摘要

| 方案 | Score | HitRate@10 | MRR | MTTC | Efficiency |
|---|---|---|---|---|---|
| 参考实现（general，原版） | 0.958850 | 1.000 | 0.97083 | 2.62 | 0.838 |
| **+ Margin Gate（`TJ_MARGIN=1`，general）** | **0.961550** | 1.000 | **0.97083** | **2.48** | **0.852** |
| + Margin Gate + mirror（冲分备选） | 0.964650 | 1.000 | 0.98083 | 2.48 | 0.852 |

**核心性质**：增益**全部来自 Efficiency**（MTTC 2.62 → 2.48），**MRR 完全不变（0.97083）**——每一个被提前发布的会话，其 Top-1 本来就是正确目标，是纯赚，不牺牲排名。稳健、不依赖对模拟器内部的任何额外假设。

---

## 1. 动机：补上 Paper C 门控缺的一条

主设计文档 §8.3 的发布门控 `should_emit` 用了三类信号：

1. 候选池收敛　`len(exact) == 1`
2. 轮数预算　　`turn >= FLOOR`（FLOOR = 3）
3. 信息枯竭　　`exhausted` / `no_new_info >= 2`

但 **Paper C**（Ma et al., *"Ask or Recommend: An Empirical Study on Conversational Product Search"*, **CIKM 2024**）的 Ask-or-Recommend 效用门控里，「该推荐」的条件除了轮数与意图，还有一项**检索置信度**：

$$\mathrm{EU}(\texttt{Recommend}) \;=\; \beta_1 \cdot \mathbb{1}[\text{晚期意图}] \;+\; \beta_2 \cdot \underbrace{\mathrm{Conf}(\mathrm{Top1})}_{\text{检索置信度}} \;-\; \beta_3 \cdot \mathbb{1}[\text{已找够}]$$

对应其 §3.5 规则：`if top1_conf >= CONF_TAU: return "Recommend"`。

**原实现没有落地这一项。** 值得注意的是——`_rank` 其实已经算好了每个候选的分数并存进 `st.diag["scores"]`，但**只用于 trace / 调试，没有喂回门控决策**。我们做的，就是把这份已算好、却闲置的信号用起来。

---

## 2. 方法：用分数领先幅度量化 Top-1 置信度

论文说「Top-1 置信度够高就发布」，但没有定义如何度量。我们将其操作化为 **Rank-1 与 Rank-2 的分数领先幅度**：置信度 ≈ 头名领先次名的差距。差距越大，Top-1 是正确目标的把握越大。

```python
# solution/src/agent.py · _emit()
# 在 exhausted 判断之后、turn >= FLOOR 之前插入：
if MARGIN and st.turn >= 2 and st.constraints and len(ranked) >= 2:
    sc = st.diag.get("scores", {})
    if ranked[0] in sc and ranked[1] in sc and (sc[ranked[0]] - sc[ranked[1]]) >= MARGIN:
        return True, "score margin dominant - Rank-1 confident"
```

以及门控旋钮：

```python
MARGIN = float(os.environ.get("TJ_MARGIN", "0"))   # 0 = 关闭；1 = 选用
```

**两个保护条件，防止误发：**

- `st.constraints`：仅在 **PRECISION 路线**（已收到约束、分数由 span 匹配主导）时启用；DISCOVERY 阶段分数纯由先验决定，领先是「热门度虚高」而非「匹配确定」，不可据此提前发布。
- `st.turn >= 2`：第 1 轮信息不足，一律不提前发布。

领先幅度即 Paper C 的 $\mathrm{Conf}(\mathrm{Top1})$ 的一个可计算代理。

---

## 3. 消融（官方 `evaluator/local_evaluator.py`，公开 200 会话，逐字模式）

| `TJ_MARGIN` | Score | MRR | MTTC | Efficiency | 说明 |
|---|---|---|---|---|---|
| 关闭 | 0.958850 | 0.97083 | 2.62 | 0.838 | 原版 general |
| 6 | 0.959150 | 0.97083 | 2.60 | 0.840 | 门槛过高，只放行极少数 |
| 3 | 0.959250 | 0.97083 | 2.60 | 0.840 | |
| 2 | 0.959450 | 0.97083 | 2.59 | 0.841 | |
| **1（选用）** | **0.961550** | **0.97083** | **2.48** | **0.852** | MRR 无损的最佳点 |
| 0.5 | 0.959800 | 0.96100 | 2.42 | 0.858 | 开始误发，MRR 掉 |

**读数**：门槛从高往低放，MTTC 单调下降（发布越来越早）而 MRR 一直钉在 0.97083，直到 `MARGIN=0.5` 才出现误发（MRR 0.961）。**`MARGIN=1` 是 MRR 零损失下 Efficiency 的最优点。**

**与 mirror 模式叠加**（两项增益正交）：

| 配置 | Score | MRR | Efficiency |
|---|---|---|---|
| general + `MARGIN=1` | 0.961550 | 0.97083 | 0.852 |
| mirror（原版） | 0.962050 | 0.98083 | 0.838 |
| **mirror + `MARGIN=1`** | **0.964650** | 0.98083 | 0.852 |

---

## 4. 建议

- **正式提交**：`TJ_MARGIN=1` + **general 模式** → **0.9616**。稳健、MRR 无损、不依赖对模拟器 intent_card 构造方式的假设（不像 mirror）。
- **冲分备选**：叠加 mirror → 0.9647，但 mirror 假设了模拟器内部的 span 顺序，对隐藏集存在过拟合风险，谨慎使用。
- 提交前请依主文档 §16 的约定，把选定值硬编码进 `config.py` 并移除环境变量分支。

---

## 5. 复现

```bash
# 在官方仓库根目录（starter/agent.py = 参考实现 + 本增强）
TJ_MARGIN=1 python -m evaluator.local_evaluator \
    --catalog data/catalog.jsonl --dataset data/public_set.jsonl
# 预期：recommended_technical_score = 0.961550
```

依赖：Python 3.10+，无第三方库，无网络调用。

---

## 参考文献

- **Paper C** — Ma et al., *"Ask or Recommend: An Empirical Study on Conversational Product Search"*, **CIKM 2024**. 门控效用式 §3.4 (4) 的 $\beta_2 \cdot \mathrm{Conf}(\mathrm{Top1})$ 项、§3.5 决策规则 `top1_conf >= CONF_TAU`。
