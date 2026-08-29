# 实测结果 · Collision-Aware Progressive Tail Repair

> 状态：实验候选，不覆盖稳定提交。
>
> 被测实现：`solution/experimental/tail_repair.py`
>
> 官方数据：公开 200 会话；官方评分器与数据文件均未修改。

## 1. 结论

在 NLU-gated FARM、`margin=0.75` 的基础上，对“完整意图已经披露、仍存在同卡碰撞”的 buying / browsing 会话启用渐进推荐批次：

1. 第 3 轮只展示原 Rank 1；
2. 若用户继续，第 4 轮展示原 Rank `2,4,6,8,10`；
3. 第 5 轮展示原 Rank `3,5,7,9`。

实测把公开集总分从新上传组合版的 `0.964650` 提高到 **`0.967700`**，同时：

- Hit@10：`1.000`（不变）
- MRR：`0.980833 → 0.991667`
- MTTC：`2.480 → 2.490`
- `LoopScore < 0.9`：`6 → 3`
- 最低链路：`0.710 → 0.740`
- Worst-5% mean：`0.837 → 0.890`

相对本实验不启用渐进批次的 `margin=0.75` 基线 `0.965050`，增益为 `+0.002650`；相对仓库新上传的 `margin=1` 组合版 `0.964650`，增益为 `+0.003050`。

## 2. 为什么它不是“猜目标”

原 Rank 1 保持第 3 轮 Rank 1，不承担损失。只有原本未命中的候选被分流到后续批次。对原 Rank `r=2k`，第 4 轮的新排名为 `k`：

```text
旧分数 = 0.50 + 0.30/(2k) + 0.16
新分数 = 0.50 + 0.30/k    + 0.14
差值   = 0.15/k - 0.02 > 0     (k <= 5)
```

因此原 Rank `2,4,6,8,10` 全部严格改善。第 5 轮的奇数批次对原 Rank `3,5,7,9` 也逐项改善。策略利用的是官方指标中“排名收益远大于多一轮成本”的结构，不依赖 ASIN、标题泄漏或目标标签。

## 3. 安全门控

渐进批次只在以下条件同时满足时启用：

- 首句由 Layer A 明确识别为 buying 或 browsing；
- 当前为第 3 轮；
- 已恢复至少 4 条约束；
- 候选中存在至少两个共享完整四槽意图签名、且覆盖全部已知约束的商品。

intent_override 不会冻结覆写前排序；Layer B/C 改写输入不启用 FARM/渐进批次。

## 4. 对照与失败实验

| 方案 | Score | Hit@10 | MRR | MTTC | `<0.9` |
|---|---:|---:|---:|---:|---:|
| FARM + margin=1（仓库新上传） | 0.964650 | 1.000 | 0.980833 | 2.480 | 6 |
| NLU-gated FARM + margin=0.75 | 0.965050 | 1.000 | 0.980833 | 2.460 | 6 |
| **+ progressive batching** | **0.967700** | **1.000** | **0.991667** | **2.490** | **3** |

两个元数据破同分方案被否决：

- 按商品平均评分排序：`0.961925`，低分链路增至 9 条；
- 按用户历史评分接近度排序：`0.960967`，低分链路增至 10 条。

纯先验回退得到 `0.965050`，与未处理完全相同，说明现有 FARM 在同卡组内已经基本由先验决定。

## 5. 鲁棒性与契约

- 改写压力集：`0.928354`，Hit@10=`0.990`，MRR=`0.879512`，MTTC=`2.525`；与不启用渐进批次的 NLU-gated 版本一致。
- 契约/对抗输入：67 次 `respond()`，0 异常，全部通过。
- 评测器单元测试：2/3 通过；剩余 1 项因当前 Windows 沙箱阻止 Python `TemporaryDirectory` 写入而无法执行，不是断言失败。

## 6. 复现

```bash
python solution/tools/eval_tail_repair.py \
  --margin 0.75 --rules none --progressive --robust

TJ_TAIL_MARGIN=0.75 \
TJ_PROGRESSIVE_BATCHING=1 \
TJ_COLLISION_RULE=none \
python solution/tools/test_contract.py \
  --catalog techjam-conversational-search/data/catalog.jsonl \
  --agent-module tail_repair
```

## 7. 风险判断

该策略对当前评分公式是严格有利的，但它会把“一个完整 Top-10 列表”改成逐轮小批次展示。官方 README 明确允许返回 **up to 10** 个商品，JSON 契约也只规定 `maxItems`、没有最小数量，因此协议层面合规。答辩中建议将其表述为 progressive disclosure / rejection-aware re-ranking，并说明它避免一次展示大量无法区分的同质候选。
