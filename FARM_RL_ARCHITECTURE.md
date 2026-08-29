# FARM-RL：字段对齐混合检索 + 强化学习对话策略

> 状态：候选架构；已实现一个零依赖代理版本验证关键假设，完整神经检索与 RL 训练尚未接入稳定提交。

## 1. 结论

现有方案不应该被端到端神经网络替换。它在公开集已经达到 `Hit@10 = 1.0`，失败面主要不是召回，而是同约束商品之间的排序，以及固定到第 3 轮发布造成的效率损失。

建议采用 **FARM-RL（Field-Aware Residual Matching with Reinforcement Learning）**：保留当前精确约束检索作为安全锚点，在它旁边增加字段图、多路神经检索和字段级 late interaction，只让神经网络学习残差；最后用一个小型强化学习策略联合决定“问哪个字段”和“现在是否发布”。

公开集上的零依赖代理实验已经验证了两个关键假设：

| 方案 | Hit@10 | MRR | MTTC | TechnicalScore |
|---|---:|---:|---:|---:|
| 当前 `general` | 1.000 | 0.970833 | 2.620 | 0.95885 |
| FARM 字段对齐，原门控 | 1.000 | 0.980833 | 2.610 | 0.96205 |
| FARM 字段对齐，小池提前发布（阈值 3） | 1.000 | 0.978333 | 2.525 | **0.96300** |

最后一行比当前方案提高 `+0.00415`。它不是完整神经/RL 成绩，只是用可解释规则替代未来两个学习模块的代理实验，因此可用于判断投入方向，不能当作私榜保证。

## 2. 为什么选这条路线

### 2.1 当前误差的真实形态

当前公开集 200 个会话全部召回目标，但有 10 个目标不在 Rank 1：7 个 Rank 2、2 个 Rank 4、1 个 Rank 6。换言之，新增普通 dense retriever 几乎没有可见收益空间，反而可能破坏已经为 1.0 的召回。

其中一部分错误来自字段边界丢失。例如一个商品字段是：

```text
solid colors: 100% cotton; heather grey: 90% cotton, 10% polyester; ...
```

对话解析会按分号拆成多个约束。当前 `attribute_spans` 认为它们只是普通子串，无法利用“这些片段共同来自同一个高显著字段”这一强信号。字段对齐代理正是修复这一点。

剩余 6 个错误中，多个商品的已披露四项意图字段完全相同。没有新增用户信息时，这类样本在信息论上不可辨识；更大的 reranker 也无法凭空恢复目标。它只能学习更好的目标先验，或由策略在尚有可回答字段时继续提问。

### 2.2 中美公开方法给出的共同方向

中国侧更强调统一检索底座、结构化需求状态和 outcome-based search RL：

- BAAI 的 [BGE-M3](https://arxiv.org/abs/2402.03216) 在一个模型中统一 dense、sparse、multi-vector 检索，并用 self-knowledge distillation 互相提供教师信号。
- 阿里 Qwen 团队的 [Qwen3 Embedding/Reranker](https://qwenlm.github.io/blog/qwen3-embedding/) 分别采用双塔和交叉编码器，支持任务指令与 100 多种语言；0.6B 版本适合先做本地可行性验证。
- 清华/阿里等提出的 [ProductAgent](https://aclanthology.org/2025.emnlp-industry.25/) 使用结构化记忆、候选商品特征统计与 symbolic+dense 混合索引形成闭环。
- 人大团队的 [R1-Searcher](https://arxiv.org/abs/2503.05592) 表明 outcome-based RL 能学到更好的检索时机，且其分析显示 RL 在检索时机与跨域泛化上优于单纯 SFT。

美国侧更强调 schema、字段图、late interaction 和直接对业务指标优化：

- Amazon 的 [自然语言商品搜索接口](https://www.amazon.science/publications/building-natural-language-interface-for-product-search) 把自然语言映射为商品 schema/API，使用 LLM 生成弱监督数据，再训练多任务 schema generator；公开集 Exact Match 与 Micro-F1 分别比基线提高约 8.6% 和 10.5%。
- Amazon 的 [AsK](https://www.amazon.science/publications/ask-aspects-and-retrieval-based-hybrid-clarification-in-task-oriented-dialogue-systems) 根据歧义程度在“领域 aspect 提问”和“候选文档提问”之间动态切换，在相关产品任务上报告约 20% Recall@5 增益。
- Amazon 2026 的 [LLM 字段图搜索](https://www.amazon.science/publications/from-unstructured-to-structured-llm-guided-attribute-graphs-for-entity-search-and-ranking) 先离线构建类别感知 attribute graph，再基于图结构排序；论文报告零样本平均精度提升超过 5%，每商品 token 使用下降 57%。
- Stanford 的 [ColBERTv2](https://arxiv.org/abs/2112.01488) 证明 token 级 late interaction 能保留细粒度匹配，并通过残差压缩把空间开销降低 6–10 倍。
- Google 的 [Matching Cross Network](https://research.google/pubs/matching-cross-network-for-learning-to-rank-in-personal-search/) 将 query-document embedding 的逐元素匹配与用户、上下文等侧信息显式交叉，适合本题的字段分数、先验和匿名画像融合。
- Amazon 的 [RLQR](https://www.amazon.science/publications/enhancing-e-commerce-product-search-through-reinforcement-learning-powered-query-reformulation) 直接以商品覆盖率为奖励，报告相对标准生成模型 28.6% 的覆盖率提升，说明搜索策略应优化检索指标，而不是只模仿参考文本。

FARM-RL 不是简单拼接这些论文，而是把它们映射到本赛题当前仍有损失的两个位置：字段级排序残差，以及 ask/emit 动作策略。

## 3. 架构

```text
离线：Catalog
  -> 类别感知字段抽取/归一化
  -> Product--Field--Value 图
  -> exact / BM25 / dense / sparse / multi-vector 索引
  -> 合成对话与难负例

在线：多轮消息
  -> Demand Graph（正约束、负约束、软偏好、覆写、置信度、来源轮次）
  -> Safe Recall Union
       exact category + exact field filter
       BM25 per field
       BGE-M3 dense/sparse/multi-vector
  -> Field-Aligned Late Interaction
  -> Top-N Qwen3 cross-encoder rerank（可选）
  -> Matching Cross posterior calibrator
  -> Factored RL policy
       ask head: 10 个字段动作
       emit head: hold / show top-k
  -> 推荐或继续澄清
```

### F0：类别感知字段图

为每件商品构造：

```text
Product -> category/title/brand/store/price
Product -> feature_i
Product -> detail_key -> detail_value
Product -> derived material/color/style/use_case
```

每个 value 同时保存：原文、归一化值、字段类型、来源位置、抽取置信度。不要把所有字段直接拼成一段文本；字段来源本身就是本题最强的匹配特征。

### F1：Demand Graph

对话状态从字符串列表升级为：

```text
(facet, value, polarity, hardness, confidence, source_turn, active)
```

覆写把旧节点设为 `active=false` 或降为软偏好，不再依赖固定模板；否定约束单独建边，避免 dense similarity 把“不要红色”和“红色”当成相似。

解析采用双通道：高置信模板/词典直接落图；其余文本由小型 schema generator 或 NER 映射到字段和值。神经解析失败时继续使用当前 Layer B/C。

### F2：Safe Recall Union

```text
C = C_exact ∪ C_bm25 ∪ C_dense ∪ C_sparse ∪ C_multivector
```

硬约束已被高置信解析时，违反硬约束的商品仍然被过滤。神经召回只能补充 exact 召回之外的改写、同义词与错桶候选，不能覆盖精确冲突。

BGE-M3 可以先统一实现后三个神经通道；若部署受限，只保留 sparse+dense，multi-vector 延后。

### F3：字段级 late interaction

对每个需求节点 `q_i` 和商品字段 `f` 计算：

```text
m(i, f, d) = sum over query tokens x of max over field tokens y cos(E(x), E(y))
```

随后做类别感知的 field attention：

```text
S_field(d) = sum_i hardness_i * confidence_i * sum_f alpha(category, facet_i, f) * m(i,f,d)
```

这比“query 对整段 product 文本做一次 cosine”更适合本题，因为它保留了约束与字段之间的对应关系。公开代理中的 substring coverage 就是 `m(i,f,d)` 的离散下界。

### F4：残差排序与目标后验

最终排序器不直接替换当前分数，而学习残差：

```text
S(d) = S_symbolic(d)
     + lambda(state) * S_field(d)
     + mu(state) * S_cross_encoder(d)
     + MCN(side_features)
```

侧信息包括候选池大小、精确覆盖数、字段置信度、BM25、商品先验、匿名画像匹配、轮次、覆写与拒答信号。`lambda` 在精确字段冲突时为 0；只有 symbolic 不能区分或 NLU 置信度低时才升高。

训练目标采用同类别、同字段签名商品作为 hard negatives，并使用 top-heavy listwise loss。禁止把 `parent_asin` 本身作为特征，避免记住公开集目标。

排序器再经 temperature scaling 或 isotonic calibration 输出：

```text
p_i = P(target = candidate_i | dialogue state)
```

这个后验是 RL 门控需要的关键输入，比“候选数等于 1”更细致。

### F5：Factored RL 策略

动作拆成两个 head：

```text
ask  ∈ {category, material, color, size, style, brand, budget, feature, use_case, other}
emit ∈ {hold, show_top_k}
```

状态包含：`top1 posterior`、top1-top2 margin、候选熵、每字段条件熵/期望候选缩减、已问字段、dead 字段、无新增信息轮数、轮次和场景后验。

训练时直接使用官方指标对应的 outcome reward：

```text
hit:  R = 0.50 + 0.30 / rank + 0.20 * (11 - turn) / 10
miss: R = 0
```

中间过程不奖励“看起来像好问题”，避免 reward shaping 把策略带偏。可先用 Double DQN/QR-DQN 训练这个小型离散策略；如果只拥有固定日志，则改用 Conservative Q-Learning。动作 masking 禁止重复询问已枯竭字段。

## 4. 数据与训练

1. 从 50,000 商品自动生成 intent graph；按商品而不是按会话切分 train/dev/test，防止目标泄漏。
2. 按官方 40/40/15/5 场景生成至少 20–40 万条轨迹。
3. 为 30%–50% 消息加入改写、字段缺失、拼写噪声、否定和错桶；改写只用于训练，不进入最终在线依赖。
4. 排序 hard negative 优先选择同类别、相同前三个字段值但目标不同的商品。这正对应当前 6 个不可分辨错误。
5. 先训字段解析与 ranker，再冻结它们训练策略；最后只做小学习率联合校准，避免 reward 同时改变环境与策略造成不稳定。
6. 公开 200 会话仅用于最终阈值校准和报告，不直接记忆目标。

## 5. 实验矩阵与上线门槛

必须报告以下消融：

| 实验 | 要回答的问题 |
|---|---|
| 当前 general | 稳定基线 |
| + field signature proxy | 字段来源是否有价值 |
| + dense only | 单向量语义召回是否增加私榜鲁棒性 |
| + sparse + multi-vector | 细粒度匹配是否优于 dense only |
| + field late interaction | 字段对齐是否提升 Rank 1 |
| + cross encoder | 增益是否值得延迟 |
| heuristic gate vs RL | RL 是否真实改善 TechnicalScore，而非只降 MTTC |
| exact anchor on/off | 神经模块是否破坏 Hit@10 |
| clean vs paraphrase/dropout | 是否只过拟合公开模板 |

晋级条件建议设为：公开集 `TechnicalScore > 0.9630`，五折目标级切分均不低于当前方案，改写压力集明显优于当前方案，且 Hit@10 不低于 1.0。达不到时，完整神经/RL 方案不替换稳定提交。

## 6. 实施顺序

1. **已完成**：字段签名与小池门控代理，验证分数 0.9630。
2. 实现离线 field graph 与训练数据导出器；先不引入在线模型。
3. 接入 BGE-M3 或 Qwen3-Embedding-0.6B，验证 semantic recall 与改写集。
4. 训练 field-aware residual ranker；只有它稳定提升 MRR 后才接 cross encoder。
5. 用当前模拟器训练小型 RL policy，与候选数阈值做严格对照。
6. 最后才考虑 Qwen3-Reranker-0.6B；若延迟或封装不满足提交环境，保留为演示/服务版，提交版使用预计算 embedding + 小 ranker。

## 7. 复现代理实验

```bash
python solution/tools/eval_farm_proxy.py
```

结果写入 `solution/results_farm_proxy.json`。稳定提交 `solution/src/agent.py` 未被修改。

