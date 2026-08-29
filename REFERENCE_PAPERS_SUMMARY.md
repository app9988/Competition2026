# Reference 三篇论文：方案与数学建模总结（Agent 可推理版）
---

## 0. 三篇定位与互补关系

| 编号 | 论文 | 出处 | 解决的子问题 | 对 Agent 的可用产物 |
|---|---|---|---|---|
| **A** | Analysing the Effect of Clarifying Questions on Document Ranking in Conversational Search | Krasakis et al., ICTIR 2020 | 澄清轮的答案**该怎么用**（用 Q、用 A、还是都不用） | 极性/长度分类器 + 上下文选择函数 + 分数插值 |
| **B** | ProductAgent: Benchmarking Conversational Product Search Agent with Asking Clarification Questions | Ye et al., arXiv:2407.00942 (2024) | **提什么问 + 怎么检索**（三阶段循环 + 统计量驱动） | 三阶段循环、5 个工具签名、需求状态更新、检索/融合/重排 |
| **C** | Ask or Recommend: An Empirical Study on Conversational Product Search | Ma et al., CIKM 2024 | **什么时候问、什么时候推**（Ask-or-Recommend 门控） | 意图→动作条件概率表、满意度衰减方向、多样性触发澄清 |

**互补链路**：

```
C 决定「是否提问」  ->  B 决定「提什么问、怎么检索」  ->  A 决定「答案回来后怎么融进排序」
   (门控)                  (生成 + 统计量)                   (上下文选择 + 插值)
```

---

## 1. Paper A · 澄清轮的排序建模（ICTIR 2020）

### 1.1 任务形式化 【原文】

单轮澄清的文档排序。给定：

```
Q0 = 用户原始查询 (topic)
Q  = 系统澄清问题
A  = 用户对 Q 的回答
目标: 对文档集合 D 排序;  评估指标 = NDCG@20
数据: Qulac (198 topics / 762 facets / 10K QA 元组, 基于 TREC Web Track 2009-2012)
```

**关键前提**【原文】：直接把 `Q0 + Q + A` 拼成一个长查询效果**差**，因为 Q0 的权重被稀释。必须用**分数级插值**，不能用文本级拼接。

### 1.2 数学建模

**(1) 文档语言模型 — Dirichlet 先验平滑**【原文，Ponte & Croft / Zhai-Lafferty 标准形式】

```
p(w | theta_d) = ( tf(w,d) + mu * p(w|C) ) / ( |d| + mu )

  tf(w,d)   : 词 w 在文档 d 中的词频
  p(w|C)    = tf(w,C) / |C|        全集语言模型
  |d|       : 文档长度
  mu        : Dirichlet 平滑参数, 典型取 1000 ~ 2500
```

**(2) KL 散度查询似然打分**【标准定义】

```
score_QL(d | q) = -KL(theta_q || theta_d)
                =rank= SUM over w in q:  p(w|theta_q) * log p(w|theta_d)

  p(w|theta_q) = tf(w,q) / |q|      (MLE)
```

**(3) 会话插值 —— 核心公式**【原文】

```
==========================================================
  score(d) = lambda * score_QL(d | Q0)
           + (1 - lambda) * score_QL(d | C(Q,A))

  lambda = 0.5                      <-- 原文取等权
  若 C(Q,A) = 空集, 则退化为 score(d) = score_QL(d | Q0)
==========================================================
```

`C(Q,A)` 是**澄清轮上下文选择函数**，定义见 1.3。

### 1.3 方案：极性 + 长度 → 上下文选择

**(1) 极性分类器（词面启发式）**【原文】

```
pol(A) =
    idk   if  A 命中 "I don't know" 模式
    P     if  "yes" in tokens(A)
    N     if  "no"  in tokens(A)
    O     otherwise
```

> ⚠️ 原文只写「含 yes 记 P、含 no 记 N」，**未定义两者同时出现时的优先级**。
> 实现时需自行固定一条优先序，建议 `idk > P > N > O`
> ——因为 "Yes, but I don't want no..." 这类句式中 yes 承载主极性。

**(2) 长度分类器**【原文】

```
len(A) = single   if |tokens(A)| == 1
         multi    if |tokens(A)| >  1
```

**(3) 上下文选择函数 C —— 启发式排序器**【原文】

```
C(Q, A) =
    Q + A     if  pol == P                      (single 与 multi 皆是)
    Q + A     if  pol == O  and  len == multi
    A         if  pol == N  and  len == multi
    空集       otherwise:  (N,single) / (O,single) / idk
```

**记忆口诀：肯定用全轮，否定只用答，单字否定 / 不知道 → 整轮丢弃。**

### 1.4 实证常量表（用作先验 / 调参依据）【原文】

**Table 1 — 按答案类型的 NDCG@20 及相对 Q0 的增益**

| 极性 | 长度 | 样本数 | Q0 | Q0+Q | Q0+A | Q0+Q+A |
|---|---|---|---|---|---|---|
| P | single | 364 | 0.191 | **+7.9%** † | +0.0% | **+7.9%** † |
| P | multi | 1275 | 0.162 | +0.0% | +0.6% | **+16.0%** † |
| N | single | 580 | 0.130 | −18.5% † | −0.8% | −18.5% † |
| N | multi | 3791 | 0.132 | −11.4% † | **+22.7%** † | +20.5% † |
| O | single | 47 | 0.177 | −16.9% | −52.0% † | −4.0% |
| O | multi | 1729 | 0.153 | −13.7% † | +10.5% † | **+11.8%** † |
| idk | multi | 346 | 0.162 | −13.0% † | −32.7% † | −11.7% † |

（† = 双尾 t 检验 p < 0.05）

> 注意 `N / multi` 行：`Q0+A` (+22.7%) **优于** `Q0+Q+A` (+20.5%)。
> 这正是上下文选择函数在该分支**只取 A** 的依据。

**Table 5 — 留出测试集（40 topics）总体对比**

| 排序器 | NDCG@20 |
|---|---|
| Q0 | 0.148 |
| +Q | 0.134 |
| +A | 0.163 |
| +Q+A | 0.166 |
| **启发式排序器** | **0.171**（对 +Q+A 显著，p < 0.001） |

**Table 2 — facet 难度与提问方向的相关性（Pearson r）**

```
r( NDCG@20(Q0),  正向回答占比 %P )  =  0.173   (p = 1.5e-6)
r( NDCG@20(Q0),  负向回答占比 %N )  = -0.197   (p = 4.3e-8)
```

→ **可推理结论**：Q0 单独检索得分越高的 facet，越容易收到肯定回答。
**可用 Q0 的检索质量作为「提问命中率」的先验。**

**Table 4 — 长度与增益的相关性（Pearson r）**

| X | Y | r | p |
|---|---|---|---|
| Q 的 token 数 | ΔNDCG(+Q) | 0.071 | 1.1e−11 |
| Q 的 token 数 | ΔNDCG(+Q+A) | 0.006 | 5.6e−1（不显著） |
| A 的 token 数 | ΔNDCG(+A) | **0.130** | 4.4e−34 |
| A 的 token 数 | ΔNDCG(+Q+A) | 0.056 | 1.1e−7 |
| Q+A 的 token 数 | ΔNDCG(+Q+A) | 0.049 | 4.1e−6 |

→ **答案越长增益越大（最强信号）**；问题长度正相关较弱但显著。

### 1.5 Agent 可执行伪代码

```python
def rank_with_clarification(Q0, Q, A, docs, lam=0.5, mu=2000):
    pol = polarity(A)                                    # idk > P > N > O
    ln  = "single" if len(tokenize(A)) == 1 else "multi"

    if   pol == "P":                       ctx = Q + " " + A
    elif pol == "O" and ln == "multi":     ctx = Q + " " + A
    elif pol == "N" and ln == "multi":     ctx = A
    else:                                  ctx = None    # N/single, O/single, idk

    if ctx is None:
        return {d: ql(d, Q0, mu) for d in docs}
    return {d: lam * ql(d, Q0, mu) + (1 - lam) * ql(d, ctx, mu) for d in docs}
```

**额外定性洞察**【原文·Table 3】：即使澄清问题收到单字否定，问题中出现的**上下文相关实体**仍有**查询扩展**价值。三个实例的 ΔNDCG 分别为 +18.53 / +15.97 / +13.57：

```
信息需求: Drafting of Declaration of Independence
Q0: all men are created equal
Q : Would you like to learn more about Thomas Jefferson?
A : No                                   -> ΔNDCG +18.53
   (Thomas Jefferson 虽被否定, 却是相关文档中的高频实体)
```

→ 不要因为「答案是 no」就丢弃问题里的实体词，**除非答案是单字**。

---

## 2. Paper B · ProductAgent 三阶段循环（arXiv:2407.00942, 2024）

### 2.1 任务形式化 【原文】

**商品需求澄清（Product Demand Clarification）**。用户以一个**商品类目**作为初始模糊查询 U1：

```
D = { U1, A1, P1, U2, A2, P2, ... }

  U_t = 用户话语
  A_t = { Q_t1, Q_t2, ..., Q_tn }   Agent 生成的多选澄清问题集, 实现中 n = 3
        每个 Q_tj = (问题文本, 候选选项集 C_tj), 选项含 "Other" 兜底
  P_t = 本轮检索出的商品列表 (与问题同轮返回, 作为即时反馈)
```

### 2.2 方案：每轮三阶段循环 【原文】

```
  Memory: S_t (结构化 demands)
     |
     v
  [Stage 1] Category Analysis  —— 产出动态知识库
     S_t --Text2SQL--> SQL --SQL精确检索--> R_t --Category Analyze--> Phi_t (统计量)
     |
  [Stage 2] Item Search
     S_t --Query Generation--> q_t (NL query) --Retriever--> P_t (商品列表)
     |
  [Stage 3] Clarification Question Generation
     (S_t, Phi_t) --Question Generation--> A_t = {Q, C} x 3  (JSON)
     |
     v
  用户回答 --抽取 (Q, a) 对--> 回写 Memory, 进入下一轮
```

**双库设计**【原文】：商品同时存入 **SQL 关系库**（Stage 1 用，精确匹配，快）与**稠密向量库**（Stage 2 用，可按相关度排序，SQL 做不到）。

**5 个工具签名**【原文·Table 2】

| 工具 | 输入 | 输出 |
|---|---|---|
| `Text2SQL` | Demands S_t | SQL Query |
| `Category Analyze` | Product items R_t | Category statistics Phi_t |
| `Query Generation` | Demands S_t | NL query q_t |
| `Retriever` | NL query q_t | Product items P_t |
| `Question Generation` | Demands S_t + Statistics Phi_t | Clarification questions A_t |

> 【原文】为自动化评测而简化，**未使用 tool router**，工具调用是固定流水线，不做动态选择。

**商品 Schema（10 个 facet）**【原文·Table 8】：由 54 个层级实体标签经电商 NER 压缩而来

```
Category (str)          Brand (List[str])        Series (List[str])
Target Customer         Applicable Scenario      Decorative Attribute
Material                Style                    Specification
Color                   Function
```

### 2.3 数学建模

**(1) 需求状态更新（Memory）**【形式化，源自原文 Memory 模块描述】

```
S_t = S_{t-1}  UNION  { (Q_{t-1,j}, a_{t-1,j}) : j = 1..n,  a_{t-1,j} != 空 }
S_0 = { (category, U1) }
```

**(2) 统计量 Phi_t（动态知识库）**【形式化，原文只描述为 "summarized statistics"】

设 R_t 为 Stage 1 检索出的商品集合，F 为 facet 集合：

```
Phi_t(f, v) = | { i in R_t : v in i.f } |  /  | R_t |

  f in F,  v in Vals(f)
  含义: 在当前候选商品中, facet f 取值为 v 的比例
```

选项构造约束【原文·Prompt】：

```
C_tj  =  TopK_v Phi_t(f_j, ·)  UNION  { "Other" }
且严格禁止与历史问题重复
```

**(3) BM25（稀疏检索）**【标准定义，原文引用 Robertson et al. 2009】

```
score_BM25(q, d) = SUM over w in q:

                     tf(w,d) * (k1 + 1)
    IDF(w)  *  ---------------------------------------
               tf(w,d) + k1 * (1 - b + b * |d| / avgdl)


    IDF(w) = ln( (N - n(w) + 0.5) / (n(w) + 0.5) + 1 )

    k1 = 1.2 ~ 2.0 ,  b = 0.75 ,  N = 文档总数 ,  n(w) = 含 w 的文档数
```

**(4) 稠密检索（GTE / CoROM 双塔）**【标准定义】

```
score_dense(q, d) = cos( E_q(q), E_d(d) )
                  = E_q(q) · E_d(d) / ( ||E_q(q)|| * ||E_d(d)|| )

  GTE   : 多阶段对比学习的通用文本嵌入
  CoROM : BERT-base 双编码器, 在电商标注 query-passage 数据上训练
```

**(5) RRF 融合**【标准定义，原文引用 Cormack et al. 2009 的 reciprocal rerank fusion】

```
RRF(d) = SUM over r in Retrievers:  1 / ( k + rank_r(d) )

  k = 60  (标准默认值)
  注意: 原文实证表明本任务下融合会掉点, 见 2.4(b)
```

**(6) 重排**【原文：bge-reranker-base 交叉编码器】

```
s(q, d) = CrossEncoder( q || d ),   d in TopK( score_retrieve )
```

**(7) 评测指标**【原文 + 标准定义】

```
MRR@10  = (1/|Q|) * SUM_i  [ rank_i <= 10 ] / rank_i
HIT@10  = (1/|Q|) * SUM_i  [ rank_i <= 10 ]

  [ · ] 为指示函数
```

**(8) 问题冗余度监控（BERTScore）**【原文】

将问题文本与其选项拼成句子，以其余所有问题为参考：

```
Sim(Q_tj) = BERTScore( Q_tj + C_tj ,  { Q_t'j' + C_t'j' }  其中 (t',j') != (t,j) )

用途: 多样性早停 / 去重信号。 Sim > tau 时强制换 facet。
```

### 2.4 关键实证常量（可直接作为检索策略先验）【原文】

**(a) 传统检索设定** — 1M 文档 / 2000 条 Doc2Query 合成查询（平均长度 27.02）· Table 4

| Retriever | HIT@10 | MRR@10 | MRR@10 (rerank) |
|---|---|---|---|
| BM25 | 34.80 | 26.18 | 33.35 |
| **GTE** | **69.00** | **52.29** | **63.82** |
| CoROM | 61.65 | 44.95 | 57.41 |
| BM25+GTE | 37.70 | 26.69 | 35.81 |
| BM25+CoROM | 37.35 | 26.77 | 35.65 |
| GTE+CoROM | 59.45 | 26.91 | 55.90 |

**(b) 对话检索设定** — 1M 文档 / 10000 查询 · Table 5 摘要

| LLM | BM25 (HIT/MRR) | GTE (HIT/MRR) | CoROM (HIT/MRR) |
|---|---|---|---|
| GPT-3.5 | 35.04 / 27.26 | 8.49 / 4.95 | 12.48 / 7.96 |
| **GPT-4** | **39.48 / 32.00** | 8.27 / 4.92 | 13.86 / 9.11 |
| Qwen-max | 31.58 / 25.24 | 16.45 / 10.56 | 20.71 / 13.80 |

> ⭐ **最重要的可推理结论 —— 检索器选择会反转**：
>
> - 传统设定：**稠密 >> BM25**（GTE 比 BM25 的 MRR@10 高 26.11 个点）
> - 对话设定：**BM25 >> 稠密**（GPT-4 下 39.48 vs 8.27）
> - 原因【原文】：对话查询由**用户直接勾选的选项词**拼成，几乎是商品原文词面，BM25 精确词匹配的劣势被完全消除。
> - **决策规则**：查询由**受控词表/选项**生成 → 走 BM25；查询是**自由生成的自然语言** → 走稠密 + 重排。
> - **重排**：对稠密检索提升显著（+7.17 / +11.53 / +12.46 个点），但**对话设定下对 BM25 反而掉点**（查询噪声太低，无需重排）。
> - **融合**：RRF 在两种设定下 HIT@10 与 MRR@10 **均下降** → 本任务不要盲目做多路融合。

**(c) 查询长度随轮次增长**【原文·Table 3】

```
turn:            1      2      3      4      5
avg |q_t|:     8.59  16.45  27.40  37.33  45.03

对照: 传统设定的一次性完整查询平均长度 = 27.02
=> 第 3 轮即追平一次性完整查询的信息量
```

**(d) 统计量来源消融**【原文·Table 6】—— 决定 Stage 1 用哪个检索器

| Stage-1 检索器 | HIT@10 | MRR@10 |
|---|---|---|
| w/o Statistics | 15.60 | 10.69 |
| Random（忽略实时需求） | 39.50 | 19.54 |
| **BM25** | **47.00** | **38.51** |
| CoROM | 45.00 | 38.09 |
| SQL（原默认） | 39.90 | 32.40 |

→ 统计量是刚需（去掉掉 24 个 HIT 点）；且**用 BM25/CoROM 软检索替代 SQL 精确检索来产出统计量更好**（+7.1 HIT / +6.1 MRR）。

**(e) Text2SQL 失败率**【原文·Table 7】

| LLM | Invalid SQL % | **Trivial SQL %**（检索为空） |
|---|---|---|
| GPT-3.5 | 1.21 | 54.59 |
| GPT-4 | 3.52 | 55.36 |
| Qwen-max | 3.06 | 44.92 |

→ **失败模式**：后期轮次把所有已知需求**用 AND 全部拼进 WHERE**，导致空结果（约 45–55%）。
→ **必备兜底**：约束回退 / 逐条放松 WHERE 子句 / 改用软检索。

**(f) 问题冗余随轮次上升**【原文·Fig.5，BERTScore】

| Turn | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| GPT-3.5 | 0.74 | 0.86 | 0.92 | 0.94 | 0.95 |
| GPT-4 | 0.73 | 0.77 | 0.78 | 0.80 | 0.81 |
| Qwen | 0.71 | 0.73 | 0.75 | 0.79 | 0.81 |

**(g) 澄清问题的 facet 分布**【原文·Fig.6】

```
高频 (各占 >10%): Applicable Scenario, Style, Function
低频 (对用户过于专业): Series, Specification
```

### 2.5 Agent 可执行伪代码

```python
def product_agent_turn(S_t, category, n_q=3):
    # Stage 1: Category Analysis —— 产出动态统计量
    sql   = tool_text2sql(S_t, schema)              # 空结果率 45~55%, 必须兜底
    R_t   = sql_exec(sql) or bm25_search(S_t)       # 消融证明 BM25 兜底更优
    Phi_t = tool_category_analyze(R_t)              # Phi_t[f][v] = 取值频率

    # Stage 2: Item Search
    q_t   = tool_query_generation(category, S_t)    # 短、关键词、空格分隔
    P_t   = retrieve(q_t)                           # 选项拼装的查询 -> BM25

    # Stage 3: Clarification Question Generation
    A_t   = tool_question_generation(category, Phi_t, S_t, n=n_q)   # JSON
    A_t   = dedup_by_bertscore(A_t, history, tau=0.85)              # 抑制冗余

    return A_t, P_t                                 # 问题与商品同轮返回
```

**三段 Prompt 的硬约束（原文要点）**：

- `Text2SQL`：只输出 SQL 不输出解释；用 `SELECT *`；必须带 `LIMIT {max_number}`；**尽量用 `LIKE` 而非 `=`**（这是对抗 trivial SQL 的关键）。
- `Query Generation`：简洁、关键词组成、空格分隔；覆盖全部已知需求；无解释、无引号。
- `Question Generation`：聚焦当前类目；**禁止与历史问题重复**；**选项尽量直接取自统计量**；严格 JSON 输出。
- `User Simulator`（评测用）：只能用给定选项作答，不在选项内则答 `"Other"` —— 防止信息泄漏给 Agent 造成捷径。

---

## 3. Paper C · Ask-or-Recommend 门控（CIKM 2024）

### 3.1 研究设置 【原文】

Wizard-of-Oz 在线系统：196 名参与者随机分配为 **customer** 或 **shopping assistant**，assistant 可调用 Amazon 商品搜索 API。

```
904 段对话 / 5254 条话语 / 2491 个推荐商品 / 291 个澄清问题 / 1700 次检索请求
平均: 5.81 话语, 3.37 轮, 2.76 商品
单段对话范围: 5~16 话语, 3~7 轮, 1~30 商品
```

**用户意图 I**【原文】：`Reveal`（披露需求）、`Revise`（修正需求）、`Interpret`（回应澄清 / 对推荐给反馈）、`Chitchat`（寒暄）
**系统动作 A**【原文】：`Chitchat`、`Clarify`、`Recommend`、`No-answer`

### 3.2 核心条件概率表（门控的直接先验）【原文】

```
P(Clarify | intent):                     P(Recommend | intent):
    Chitchat   = 0.748                       Chitchat   = 0.035
    Reveal     = 0.0968                      Reveal     = 0.863
    Interpret  < 0.01                        Interpret  = 0.889
    Revise     < 0.01                        Revise     = 0.971

  (one-way ANOVA, p < 0.05)
```

**在不同意图阶段执行动作的收益**【原文】

| 动作 | 意图阶段 | 找到目标商品比例 | 用户满意度 (1–5) |
|---|---|---|---|
| `Clarify` | Chitchat（早） | **95.19%** | **4.84** |
| `Clarify` | Reveal（中） | 87.50% | 4.59 |
| `Clarify` | Interpret（晚） | 66.67% | 4.17 |
| `Recommend` | Reveal（早） | 90.59% | 4.49 |
| `Recommend` | Interpret（晚） | 97.81% | **4.96** |
| `Recommend` | Revise（晚） | **100%** | 4.86 |

（组间差异均显著，p < 0.05）

> ⭐ **最重要的可推理结论：澄清要早问，推荐要晚推。**
>
> ```
> Clarify   成功率随对话推进单调衰减:  95.19% -> 87.50% -> 66.67%
> Recommend 成功率随对话推进单调上升:  90.59% -> 97.81% -> 100%
> 两条曲线在 Reveal 阶段交叉  ==> Reveal 是「问」与「推」的切换点
> ```

### 3.3 其他因子的方向性结论 【原文】

| 因子 | 对**检索表现**的影响 | 对**用户满意度**的影响 |
|---|---|---|
| SERP 多样性 nERR-IA@20 ↑ | — | 触发**更多**澄清问题（需求未收敛） |
| 已找到相关商品数 ↑ | — | 推荐动作次数**下降**（易命中，无需反复推） |
| 搜索关键词数 1→2→3 | 推荐数 2.57→4.16→**7.12**；相关数 1.24→2.17→**3.41** | — |
| 提问澄清问题 | 推荐数与相关商品数**上升** | 问得越多满意度**显著下降**（p<0.05） |
| 对话时长 ↑ | 推荐数↑，但**命中率（相关/推荐）下降** | — |
| 对话轮数 ↑ | — | **显著下降**（p<0.05） |
| 用户 `Reveal` 用时 ↑ | — | **上升**（表达更精确） |
| 系统生成澄清的耗时 ↑ | — | **下降**（等待反感） |

### 3.4 数学建模

**(1) nERR-IA@k（多样性度量）**【标准定义，原文只给指标名】

```
ERR-IA@k = SUM over subtopic s:  P(s|q) * ERR_s@k

ERR_s@k  = SUM over r = 1..k:  (1/r) * R_s(d_r) * PROD over i = 1..r-1: (1 - R_s(d_i))

R_s(d)   = ( 2^g_s(d) - 1 ) / 2^g_max

nERR-IA@k = ERR-IA@k / ERR-IA@k_ideal

  s        : subtopic / facet
  P(s|q)   : facet 先验
  g_s(d)   : 文档 d 对 facet s 的分级相关度
```

→ **nERR-IA@20 高 ==> 候选集横跨多个 facet ==> 需求未收敛 ==> 该提问。**

**(2) 命中率（对话时长的负效应）**【形式化】

```
HitRate(D) = |relevant products| / |recommended products|

d HitRate / d T_conv  <  0      (对话时长越长, 命中率越低)
```

**(3) 满意度回归模型**【形式化 —— 原文只给方向与显著性，**未给系数**，需自行拟合】

```
Sat_hat = s0
        - c1 * T             (对话轮数)
        - c2 * n_CQ          (澄清问题数)
        - c3 * t_clarify     (系统生成澄清的耗时)
        + c4 * t_reveal      (用户表达需求所用时间)

  c1, c2, c3, c4 > 0        <-- 只有符号方向有原文依据, 数值需拟合
```

**(4) Ask-or-Recommend 期望效用门控**【形式化 —— 把 3.2/3.3 的表格结论封装成可计算规则】

```
EU(a | s) = P(success | a, s)  -  lambda * E[ dDissat | a, s ]
              \_ 来自 3.2 收益表 _/        \_ 来自 (3) 的负项 _/

a* = argmax over a in {Clarify, Recommend, Chitchat, No-answer}  EU(a | s)
```

展开成可直接执行的形式：

```
EU(Clarify)   = alpha1 * nERR_IA_20                              # 候选未收敛
              + alpha2 * [ intent in {Chitchat, Reveal} ]        # 早期意图
              - ( c1*T + c2*n_CQ + c3*t_clarify )                # 满意度代价

EU(Recommend) = beta1 * [ intent in {Interpret, Revise} ]        # 晚期意图
              + beta2 * Conf(Top1)                               # 检索置信度
              - beta3 * [ n_rel 已充足 ]                          # 相关商品已够多
```

### 3.5 Agent 可执行决策规则（论文结论直接写死为规则集）

```python
INTENT_CLARIFY_PRIOR   = {"Chitchat": 0.748, "Reveal": 0.0968,
                          "Interpret": 0.005, "Revise": 0.005}
INTENT_RECOMMEND_PRIOR = {"Chitchat": 0.035, "Reveal": 0.863,
                          "Interpret": 0.889, "Revise": 0.971}
CLARIFY_SUCCESS        = {"Chitchat": 0.9519, "Reveal": 0.8750, "Interpret": 0.6667}
RECOMMEND_SUCCESS      = {"Reveal": 0.9059, "Interpret": 0.9781, "Revise": 1.000}

def choose_action(intent, turn, n_cq, nerr_ia_20, top1_conf,
                  MAX_TURNS=4, MAX_CQ=2, DIV_TAU=0.5, CONF_TAU=0.7):
    # 硬预算: 数据中 3~7 轮, 均值 3.37; 轮数与提问数均显著拉低满意度
    if turn >= MAX_TURNS or n_cq >= MAX_CQ:          return "Recommend"
    if intent in ("Interpret", "Revise"):            return "Recommend"  # 晚期 97.8~100%
    if top1_conf >= CONF_TAU:                        return "Recommend"
    if intent == "Chitchat":                         return "Clarify"    # 早期 95.19%
    if intent == "Reveal" and nerr_ia_20 >= DIV_TAU: return "Clarify"
    return "Recommend"
```

---

## 4. 三篇融合：统一 Agent 决策模型

### 4.1 状态定义

```
s_t = < S_t, Phi_t, P_t, t, n_CQ, intent_t, div_t, conf_t >
```

| 分量 | 含义 | 来源 |
|---|---|---|
| `S_t` | 结构化需求集 {(Q, a)} | B §2.3(1) |
| `Phi_t` | facet–取值频率统计量 | B §2.3(2) |
| `P_t` | 当前候选商品列表 | B Stage 2 |
| `t`, `n_CQ` | 轮数、已问澄清问题数 | C §3.3 |
| `intent_t` | 用户意图 ∈ {Reveal, Revise, Interpret, Chitchat} | C §3.1 |
| `div_t` | nERR-IA@20 多样性 | C §3.4(1) |
| `conf_t` | Top-1 检索置信度 | 归一化自 §4.2 |

### 4.2 统一排序打分函数

结合 A 的插值思想与 B 的检索器切换规则：

```
==================================================================
  score(d | s_t) = lambda * score_base(d | U1)
                 + (1 - lambda) * SUM over k = 1..t:
                       gamma^(t-k) * w_k * score_base( d | C(Q_k, A_k) )

  lambda = 0.5          【A 原文】原始查询与澄清上下文等权
  C(·)                  【A §1.3】按极性/长度决定用 Q+A / A / 丢弃
  gamma in (0,1]        【形式化】轮次衰减因子; A 为单轮, 多轮衰减需自行拟合
                        gamma = 1 时退化为等权累加
  w_k                   可取 A Table 1 的 Δ% 作为该分支的可信度权重
==================================================================
```

`score_base` 的选择【B 原文实证】：

```
score_base =
    BM25            if 查询由「受控选项词」拼装  (对话轮 t >= 2)
    dense + rerank  if 查询是「自由自然语言」    (首轮 t = 1, 或用户自由文本)

不要做 RRF 多路融合  【B 原文实证: 两种设定下均掉点】
```

### 4.3 提问选择：facet 级信息增益【形式化 —— 三篇均未给此公式，为 B 的统计量的自然延伸】

在 Phi_t 上定义 facet 的熵，选熵最大（最不确定）且未问过的 facet：

```
H(f | Phi_t) = - SUM over v in Vals(f):  Phi_t(f,v) * log Phi_t(f,v)

IG(f) = H(候选集) - SUM over v:  Phi_t(f,v) * H(候选集 | f = v)

f* = argmax over f NOT IN F_asked:  [ IG(f) - eta * Sim(Q_f, 历史问题) ]

  Sim : B §2.3(8) 的 BERTScore
  eta : 冗余惩罚系数
```

**先验偏好**【B Fig.6 实证】：优先 `Applicable Scenario` / `Style` / `Function`，回避 `Series` / `Specification`。

### 4.4 参数默认值表

| 参数 | 默认值 | 依据 |
|---|---|---|
| `lambda`（Q0 与澄清轮插值权重） | **0.5** | A【原文】 |
| `mu`（Dirichlet 平滑） | 1000 ~ 2500 | 标准 |
| `k1`, `b`（BM25） | 1.2~2.0, 0.75 | 标准 |
| `k`（RRF） | 60 | 标准（**但本任务建议不用融合**） |
| `n`（每轮澄清问题数） | **3** | B【原文实现】 |
| TopK（选项取自统计量） | 5 + `"Other"` | B【原文示例均为 5 选项 + Other】 |
| `MAX_TURNS` | **3 ~ 4** | C【原文：3–7 轮，均值 3.37；轮数↑满意度显著↓】 |
| `MAX_CQ` | **1 ~ 2** | C【原文：291 CQ / 904 对话 ≈ 0.32 个/对话】 |
| BERTScore 去重阈值 `tau` | 0.85 | B【原文：GPT-3.5 第 3 轮已达 0.92，明显冗余】 |
| 搜索关键词数 | **>= 3** | C【原文：3 关键词得 7.12 推荐 / 3.41 相关】 |
| 检索器切换 | 首轮 dense+rerank，后续 BM25 | B【原文实证反转】 |

### 4.5 完整回合伪代码（三篇合一）

```python
def turn(state, user_msg):
    # ── C: 意图识别 ───────────────────────────────────────────
    intent = classify_intent(user_msg)          # Reveal / Revise / Interpret / Chitchat

    # ── A: 上一轮澄清答案的极性+长度分析 -> 决定如何并入检索上下文 ──
    if state.last_question is not None:
        pol, ln = polarity(user_msg), length_class(user_msg)
        ctx = select_context(state.last_question, user_msg, pol, ln)   # A §1.3
        if ctx:
            state.contexts.append(ctx)
        if pol != "idk":
            state.S.update(extract_qa_pairs(state.last_question, user_msg))  # B §2.3(1)

    # ── B Stage 1: 动态统计量 (BM25 兜底/替代 SQL, 消融证明更优) ──
    R   = sql_exec(text2sql(state.S)) or bm25_search(state.S)
    Phi = category_analyze(R)                                          # B §2.3(2)

    # ── B Stage 2: 检索 (按查询形态切换检索器) ────────────────────
    q = query_generation(state.S)                       # 关键词式, >= 3 个词 (C)
    P = bm25(q) if state.turn >= 2 else rerank(dense(q))
    P = rescore(P, state.contexts, lam=0.5)             # A §4.2 分数插值

    # ── C: Ask-or-Recommend 门控 ─────────────────────────────
    div, conf = nerr_ia_20(P, Phi), top1_confidence(P)
    action = choose_action(intent, state.turn, state.n_cq, div, conf)

    if action == "Recommend":
        return recommend(P[:k])

    # ── B Stage 3 + 信息增益选 facet ─────────────────────────
    facets = topk_by_ig(Phi, exclude=state.asked_facets, n=3)          # §4.3
    Q = question_generation(state.category, Phi, state.S, facets)
    Q = dedup_by_bertscore(Q, state.history, tau=0.85)
    state.n_cq += len(Q)
    state.turn += 1
    return Q, P[:k]          # B【原文】问题与商品同轮返回, 作为即时反馈
```

---

## 5. 结论卡：Agent 可直接执行的 12 条规则

| # | 规则 | 来源 |
|---|---|---|
| R1 | 澄清上下文**不要文本拼接**进原查询，要**分数级插值**，lambda = 0.5 | A【原文】 |
| R2 | 肯定答案 → 用 `Q+A`；多词否定 → **只用 A**；单词否定 / `idk` / 单词 Other → **整轮丢弃** | A【原文】 |
| R3 | 答案越长增益越大（r = 0.130，最强信号）；单字答案基本无价值 | A【原文·Table 4】 |
| R4 | 即使答案是 "no"，多词回答中的实体仍有**查询扩展**价值 | A【原文·Table 3】 |
| R5 | Q0 单独检索得分高的 facet，提问更易收到肯定回答（r = 0.173）→ 可作提问命中率先验 | A【原文·Table 2】 |
| R6 | 每轮**同时**返回澄清问题（3 个多选）与候选商品，作为即时反馈 | B【原文】 |
| R7 | 选项**必须取自实时统计量 Phi_t**，不能靠 LLM 内部知识（去掉统计量掉 24 个 HIT 点） | B【原文·Table 6】 |
| R8 | 统计量来源用 **BM25/CoROM 软检索**而非 SQL 精确匹配（Text2SQL 有 45–55% 空结果率） | B【原文·Table 6/7】 |
| R9 | **查询由选项词拼装 → BM25；自由自然语言 → 稠密 + 重排**。不要做 RRF 融合 | B【原文·Table 4/5】 |
| R10 | 用 BERTScore 监控问题冗余（第 3 轮易达 0.92）；超阈值强制换 facet | B【原文·Fig.5】 |
| R11 | **早澄清晚推荐**：Chitchat/Reveal 阶段澄清（95.19%/87.50%）；Interpret/Revise 阶段推荐（97.81%/100%） | C【原文】 |
| R12 | 严控预算：轮数 ≤ 3–4、澄清问题 ≤ 1–2、系统响应要快 —— 三者均**显著降低满意度**；搜索时用 ≥ 3 个细粒度关键词 | C【原文】 |

---

## 6. 三篇未覆盖、需自行补齐的部分

1. **多轮澄清的衰减权重 `gamma` 与 `w_k`**：A 只做**单轮**澄清，多轮累加的权重分配无实证依据。
2. **满意度回归系数 `c1..c4`、门控权重 `alpha` / `beta` / `lambda`**：C 只给方向与显著性，**没有给系数**，必须在本项目数据上拟合。
3. **facet 信息增益 `IG(f)`**：三篇均未使用，属本文档基于 B 的 `Phi_t` 所作的推导扩展。
4. **极性冲突优先级**：A 未定义 "yes" 与 "no" 同时出现时的判定顺序。
5. **中文/电商语料适配**：A 基于英文 Qulac（TREC Web Track），C 基于 Amazon API；只有 B 基于中文电商（AliMe KG，1M 商品 / 20 类目）。
