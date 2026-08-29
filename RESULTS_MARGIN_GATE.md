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

## 5. 选不出 Rank-1 的题目（大家一起看）

公开 200 会话 **全部召回**（Hit@10 = 1.0），失分只来自 **10 个目标没排到第 1 名**（稳定版 + margin gate）。其中 **4 个被 FARM 字段对齐修复**（见 [`RESULTS_FARM_MARGIN.md`](RESULTS_FARM_MARGIN.md)），**6 个是信息论天花板，任何模型都无解**。

| 会话 | 场景 | 排名 | 已揭露线索（全部） | 目标商品 | 排它前面的对手 | FARM 是否修复 |
|---|---|---|---|---|---|---|
| public_0020 | buying | 6 | cotton; grey; 100% cotton; imported | Funny Saying Novelty 梗T | Post Heart Surgery Recovery Tshirt（更热门） | ❌ 仍第6 |
| public_0076 | browsing | 4 | cotton; grey; 80% cotton 20% poly; imported | Proud Army Girlfriend 帽T | Viking Odin's Ravens 帽T（更热门） | ❌ 仍第4 |
| public_0099 | browsing | 4 | cotton; 60% cotton 40% poly; imported; drawstring | Core 10 Fleece 长裤 | Starter Jogger Sweatpants（更热门） | ❌ 仍第4 |
| public_0161 | buying | 2 | cotton; cotton blend; imported; pull on closure | Thankful Grateful Blessed 女上衣 | STYLEIE Tale As Old As Time Tee（更热门） | ❌ 仍第2 |
| public_0172 | browsing | 2 | cotton; 100% cotton; imported; synthetic sole | Skechers Women's **Sneaker** | Skechers Women's **Bobs** Sneaker（更热门） | ❌ 仍第2 |
| public_0175 | browsing | 2 | cotton; 100% cotton; imported; zipper closure | Ariat M2 Boot Cut **Jean** | Wrangler 13MWZ Cowboy Cut（更热门） | ❌ 仍第2 |
| public_0002 | intent_override | 2 | leather; 100% leather; buckle closure; imported | Hide & Drink 皮件（某款） | Hide & Drink 皮件（同牌另款） | ✅ FARM 修复→1 |
| public_0081 | browsing | 2 | cotton; 100% cotton; pull on; machine wash | Fruit of the Loom Eversoft | Fruit of the Loom Tag-Free Tank | ✅ FARM 修复→1 |
| public_0120 | browsing | 2 | leather; red; leather lining; snap closure | SENDEFN 女钱包 | Travelambo 女钱包 RFID | ✅ FARM 修复→1 |
| public_0144 | intent_override | 2 | polyester; 100% polyester; zipper; imported | URBAN REPUBLIC 冬外套 | Tommy Hilfiger 绗缝连帽（更热门） | ✅ FARM 修复→1 |

### 根因（6 个天花板题共有）

**目标与「更热门的对手」共享全部已揭露线索。** 揭露出来的都是大路货（cotton、grey、imported、100% cotton、closure…），同类目下多个商品**全部符合**，只能用热门度先验分高下——而目标恰好不是最热门的那个。

真正能区分的字（`Bobs`、`Funny Saying`、`Jean` vs `Cowboy Cut`、图案主题）**都在标题里，但模拟器的意图卡只有那 4 条大路货约束，永远不会揭露它们**。因此：

- **多问几轮没用**：`other` 只能榨出意图卡里的东西，全是大路货。
- **LLM 没用**：实测把这几题交给 LLM 破同分，MRR 从 0.981 掉到 0.913（它也看不到区分字，只能瞎猜，还不如热门度先验）。
- **换检索器/重排没用**：对手在信息论上与目标不可分。

**结论：这 6 题是先验运气（目标偏冷门），不是 bug。** 稳定版 0.9616 / FARM 版 0.9647 的 MRR 已贴住这个信息上限。可讨论的唯一方向是热门度先验权重是否要按隐藏集分布微调，但那是赌数据分布，风险高。

---

*记录时间：2026-08-29（Asia/Taipei）*
