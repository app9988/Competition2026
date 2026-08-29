# Shopping Copilot · L0–L5 算法流水线（公式 + 走查案例 + 缺点与改进）

> 本文只讲**算法本身怎么跑**：每一层的输入输出、数学公式、以及用公开集真实数据做的逐轮走查。
> 姊妹文档：`TECHJAM_SOLUTION_DESIGN.md`（为什么这么设计）、`TECHJAM_SPEC_REPORT.md`（需求与契约规格）。
>
> **本文所有数字均可复现**：走查用 `solution/src/agent.py` + 官方评测器实跑得到，打分分解可用 §9 的脚本复算。

---

## 0. 全景图

```
                    顾客消息 (string)
                          │
   ┌──────────────────────▼──────────────────────┐
   │ L1  NLU        Layer A 模板 → B 跨度恢复 → C 词法兜底 │
   │     产出：品类 c、新增约束 ΔK、语用信号(覆写/无偏好)   │
   └──────────────────────┬──────────────────────┘
                          ▼
   ┌─────────────────────────────────────────────┐
   │ L2  对话状态机   K ← K ∪ ΔK（去重保序）        │
   │     覆写提权 / 边界跳过 / 枯竭检测              │
   └──────────────────────┬──────────────────────┘
                          ▼
   ┌─────────────────────────────────────────────┐   ┌──────────────────┐
   │ L3  检索排序                                  │◀──│ L0 五个只读索引    │
   │     ① 候选池 P（三级降级）                     │   │ cat_index        │
   │     ② 硬过滤 S = {a ∈ P : K ⊆ span(a)}        │   │ card_set         │
   │     ③ 融合打分 Score(a) → Top-10              │   │ cs_inv           │
   └──────────────────────┬──────────────────────┘   │ FTS5             │
                          ▼                          │ prior            │
   ┌─────────────────────────────────────────────┐   └──────────────────┘
   │ L4  提问策略  argmax IG(attr) → ask_attribute │
   └──────────────────────┬──────────────────────┘
                          ▼
   ┌─────────────────────────────────────────────┐
   │ L5  发布门控  |S|=1 或 turn≥3 ? 出榜单 : 只提问 │
   └──────────────────────┬──────────────────────┘
                          ▼
        {message, ask_attribute, recommendations, usage}
```

**符号约定**（全文统一）

| 符号 | 含义 |
|---|---|
| `N` | 目录规模，50,000 |
| `a` | 一个商品（`parent_asin`） |
| `c` | 一条属性约束（归一化后的文本跨度） |
| `K` | 当前已知约束集合，`K = {c₁, …, c_m}` |
| `P` | 候选池（第一级筛选后） |
| `S` | 硬过滤存活集，`S ⊆ P` |
| `t` | 当前轮次，`1 ≤ t ≤ 10` |
| `r` | 目标在返回列表中的排名 |
| `span(a)` | 商品 `a` 的属性跨度集合 |
| `corpus(a)` | 商品 `a` 的全字段拼接文本（归一化） |

---

## 1. 评分函数：一切设计的源头

```
TechnicalScore = 0.50 · HitRate@10 + 0.30 · MRR + 0.20 · Efficiency

HitRate@10 = |{命中会话}| / N_sessions
MRR        = (1/N_sessions) · Σᵢ 1/rᵢ            未命中记 rᵢ → RR = 0
MTTC       = (1/N_sessions) · Σᵢ tᵢ             未命中记 tᵢ = 11
Efficiency = clip((11 − MTTC) / 10, 0, 1)
```

**单会话边际贡献**（后文反复用到）：

```
V(t, r) = 0.50 · 1 + 0.30 · (1/r) + 0.20 · (11 − t)/10
```

| 情况 | V |
|---|---|
| 完美（t=1, r=1） | **1.00** |
| t=2, r=1 | 0.98 |
| t=3, r=1 | 0.96 |
| t=3, r=2 | 0.81 |
| MISS | 0.00 |

> **关键不对称**：多花一轮只损失 `0.02`；排名从第 2 掉到第 1 却值 `0.15`。**7 倍价差**——这直接决定了 L5 的存在。

---

## 2. L0 · 离线索引层

一次性构建，全部驻内存，**只读**。实测 18–33 s / 230 MB。

### 2.1 索引 ① 粗品类桶 `cat_index`

```
coarse_category(categories):
    parts ← []
    for v in categories:
        for seg in v.split(","):          ← 注意：字段内含逗号也会被拆开
            seg ← strip(seg)
            if seg ≠ "" and lower(seg) ∉ {"clothing",
                                          "clothing shoes & jewelry",
                                          "clothing, shoes & jewelry"}:
                parts.append(seg)
    return " ".join(parts[-2:])  if parts else "clothing item"

cat_index[normalize(coarse_category(a))].append(a)      ∀a ∈ 目录
```

复杂度 `O(N)`。产出 **1,115** 个桶。

**实测选择性**

| 指标 | 值 |
|---|---|
| 桶大小 p25 / p50 / p75 / p90 / max | 49 / **184** / 379 / 680 / 1354 |
| 200 个目标落在自己桶外的数量 | **0**（召回率 100%） |

> **实现陷阱**：必须逐字复刻 `split(",")` 与 `[-2:]`。目录里存在 `"Clothing, Shoes & Jewelry"` 这种字段内含逗号的写法，被逗号切开后产生了全场第二大桶 `Shoes & Jewelry Westlake`（1,136 条）。写错这一行，首轮召回直接崩塌。

### 2.2 索引 ② 属性跨度集 `card_set`

```
span(a) = { normalize(clean(s)) : s ∈ flatten(a.features) ∪ flatten(a.details) }
        ∪ { m }                    若 MATERIAL_RE 在 corpus(a) 中首次匹配到材质 m
        ∪ { "color: " + k }        若 COLOR_RE 在 corpus(a) 中首次匹配到颜色 k
        ∪ { "budget around $" + price }        若 price ≠ null

clean(s) = re.sub(r"\s+"," ",s).strip(" -;,.\t\n")[:180].rstrip()

flatten(v) = { f"{k}: {x}" : (k,x) ∈ v.items() }   若 v 是 dict
           = { str(x) : x ∈ v }                    若 v 是 list
```

> **为什么索引"全部跨度"而不是模拟器的 4 个槽位**：不假设评测器内部实现。代价仅 0.0032 分（0.9588 vs 0.9620），换来抗变更能力与可迁移的方法学。

### 2.3 索引 ③ 稀有词倒排 `cs_inv`

**问题**：目录约 40 万条唯一跨度，暴力做 `span ⊂ message` 是单轮 40 万次子串检查，不可接受。

```
趟 1（统计文档频率）:
    span_df[t] = |{ s ∈ 唯一跨度集 : t ∈ terms(s) }|

趟 2（只挂最生僻的 3 个词）:
    for s in 唯一跨度集:
        for t in sorted(set(terms(s)), key=span_df)[:3]:
            if span_df[t] ≤ 4000:            ← 高频词无判别力，丢弃
                cs_inv[t].append(s)
```

产出 **71,444** 个键。查询时候选量从 40 万降到数十。

> 生活类比：在书里找一句话，你会挑最生僻的词去查索引，而不是查"的"字。`df ≤ 4000` 就是这个上限。

### 2.4 索引 ④ BM25（SQLite FTS5，零依赖）

```sql
CREATE VIRTUAL TABLE products USING fts5(
  parent_asin UNINDEXED, title, categories, features, details, store, description,
  tokenize='unicode61 remove_diacritics 2');

SELECT parent_asin FROM products WHERE products MATCH ?
ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?;
```

字段权重：`asin 0.0 | title 6.0 | categories 4.0 | features 2.5 | details 2.5 | store 1.5 | description 1.0`

> **必须每个词元加双引号并剔除内部引号**，否则 `sqlite3.OperationalError` 会让整轮变空：
> `expr = " OR ".join('"' + t.replace('"','') + '"' for t in terms[:48])`

### 2.5 索引 ⑤ 流行度先验 `prior`

```
prior(a) = log1p(rating_number(a)) · (average_rating(a) / 5) + 0.7 · 𝟙[price(a) ≠ null]
```

**实测（仅知品类时按先验排序）**

| 先验函数 | Hit@10 | MRR |
|---|---|---|
| 常数（随机） | 0.080 | 0.021 |
| `log1p(RN)` | 0.815 | 0.498 |
| `log1p(RN)·AR/5` | 0.810 | 0.487 |
| **`log1p(RN)·AR/5 + 0.7·[price≠null]`** | **0.845** | **0.502** |

> 目标商品采样自 Amazon 官方 5-core leave-last-out 划分，天然偏向有评论沉淀的商品——这就是先验有效的原因。

---

## 3. L1 · NLU 三层降级

```
Layer A（模板）──未命中──▶ Layer B（跨度恢复）──未命中──▶ Layer C（词法兜底）
   逐字精确                  改写鲁棒                  强制开门控
```

### 3.1 Layer A：7 条模板正则

```
P_OVERRIDE = ignore my earlier preference.*?what i need is:\s*(.+?)\.?\s*$
P_BOUNDARY = don'?t have a preference for\s+(\w+);\s*please use your judgment
P_NOPREF   = don'?t have an additional preference for\s+(\w+)
P_REVEAL   = what matters is:\s*(.+?)\.?\s*$              ← 按 ";" 切成多条
P_BUY      = looking for (.+?)\.\s*a key requirement is:\s*(.+?)\.?\s*$
P_BROWSE   = looking for (.+?),\s*but i'?m still exploring
P_OPEN     = looking for (.+?)\.\s*(.+?)\s*$
```

> **求值顺序有约束**：`P_OVERRIDE` 必须在 `P_OPEN` 之前。否则覆写消息 `"Actually, ignore my earlier preference. What I need is: leather."` 会被 `P_OPEN` 抢先匹配，当成普通开场白，槽位翻转失效。

### 3.2 Layer B：无模板恢复（核心创新）

**思路**：不理解句子结构，而是利用**目录是闭集**这一事实，直接从句子里"捞"出属于目录的成分。

**B-1 品类恢复（闭集 n-gram 查表）**

```
lw ← [小写词元 of msg]
for n = min(8, |lw|) down to 1:
    best ← null
    for i = 0 .. |lw|−n:
        gram ← join(lw[i : i+n])
        for key in cat_loose[gram]:          ← cat_loose = 去标点形式 → 原品类串
            if best = null or |cat_index[key]| > |cat_index[best]|:
                best ← key                    ← 歧义并列取【最大桶】
    if best ≠ null: return best

# 退化：词集完全覆盖
cands ← { c : terms(c) ⊆ terms(msg) }
return argmax_{c ∈ cands, |terms(c)| 最大} |cat_index[c]|
```

> **为什么歧义取最大桶**：桶选小了，目标会被永久排除在候选之外，后面所有轮次都白费；桶选大了只是排序变难。**召回优先于精度**。

**B-2 跨度恢复（稀有词候选生成 + 精确验证）**

```
cand ← ⋃_{t ∈ terms(msg)} cs_inv[t]                       量级 O(10)
hits ← [ s ∈ cand : |s| ≥ 4 ∧ s ⊂ normalize(msg) ]        精确子串验证
hits ← sort(hits, key=len, desc)
kept ← []
for s in hits:
    if ∄ k ∈ kept : s ⊂ k:  kept.append(s)                剔除被更长命中包含者
return kept[:4]
```

**B-3 闭集材质/颜色快通道**

`leather` / `cotton` 这类词的 `span_df` 远超 4000，进不了稀有词索引。但它们本来就是模拟器的有限属性词表，直接扫描：

```
if MATERIAL_RE.search(msg): K ← K ∪ { 匹配到的材质词 }
if COLOR_RE.search(msg):    K ← K ∪ { "color: " + 匹配到的颜色词 }
```

**B-4 语用信号**

```
PIVOT_RE  = (actually|instead|scratch that|forget|change of plan|wait)
NOPREF_RE = (no strong opinion|don'?t care|isn'?t something i care|easy on|
             your call|you pick|up to you|leave .* to you)
```

### 3.3 Layer C：词法兜底

当 A、B 都没解析出任何结构（`parsed = False`）：

1. `P ← BM25(整句消息, limit=1000)`
2. **强制打开发布门控**——既然拿不到新信息，等待就没有价值

### 3.4 三层的实测价值

| 配置 | 逐字 | 改写 | 改写 Hit@10 |
|---|---|---|---|
| 仅 Layer A | 0.9620 | **0.0000** | 0.000 |
| A + B + C（v1） | 0.9588 | 0.8843 | 0.945 |
| **A + B + C（v2，当前）** | **0.9588** | **0.9236** | **0.990** |

**对"没针对性设计过"的扰动同样稳**（真正的泛化证据）：

| 扰动 | Score |
|---|---|
| 品类词被删掉一个 | 0.9518 |
| 披露跨度被截断到 6 词 | 0.9562 |

---

## 4. L2 · 对话状态机

```
SessionState = {
  category,           已确认粗品类（首次赋值后不覆盖）
  constraints[],      有序去重的约束列表 K
  slot0,              首要 / 覆写后提权的约束
  parsed,             是否曾解析出结构（Layer C 判据）
  dead{},             已确认枯竭的属性
  asked[],            提问历史
  boundary_hit,       本轮收到脚本化拒答
  exhausted,          意图卡已榨干
  no_new_info_turns,  连续无新增信息轮数
  cat_from_recovery   品类是否来自 Layer B（决定是否启用错桶逃逸）
}
```

### 状态转移

| 事件 | 转移 | 设计理由 |
|---|---|---|
| 识别到品类 | `category ← 首次值`，**后续不覆盖** | 品类是会话主键 |
| 识别到新跨度 | `K ← K ⧺ ΔK`（去重保序） | 单调累积，`|K|` 只增不减 |
| **意图覆写** | `slot0 ← 新约束` 提至首位；**历史约束保留但降权** | 见下 DD-1 |
| **边界拒答** | 只置 `boundary_hit`；**不写入 `dead`**、不计入 `no_new_info` | 见下 DD-2 |
| `other` 返回"无更多偏好" | `exhausted ← True` | 真正的信息枯竭信号 |

### DD-1 · 覆写时**不清空**历史约束（反直觉，经数据验证）

评测器中 `new_value = hard_constraints[0]`，`old_value = soft_preferences[-1]`——**二者同属一张意图卡，指向同一件商品**。按字面语义擦除旧约束会丢失信息、拉低 MRR。

> 生活类比：顾客说"算了不要辣的"，他推翻的是**优先级**，不是"想吃川菜"这个事实。

**效果**：intent_override 场景 MRR = 0.967。

### DD-2 · 边界拒答**不拉黑属性**

评测器逻辑：

```python
if scenario == "boundary" and not boundary_used and attribute:
    return f"I don't have a preference for {attribute}; please use your judgment.", True
```

这是**一次性脚本回复，与你问的是哪个属性无关**。早期实现把被拒属性写入 `dead`，等于把最优探针 `other` 永久封禁。

**修复效果**：boundary 场景 MRR **0.581 → 1.000**，全局 Hit@10 0.995 → 1.000（+0.0086 总分）。

> 生活类比：问卷里这一题勾了"无所谓"，不代表这个人以后什么都不回答。

---

## 5. L3 · 检索与排序

### 5.1 候选池生成（三级降级）

```
一级（精确）:  P ← cat_index[normalize(category)]                    O(1) 哈希
二级（投票）:  若 P = ∅ ：
                 votes ← Counter(); for t in terms(category): votes += tok_index[t]
                 P ← { a : votes[a] = max(votes) }
三级（兜底）:  若 P 仍 = ∅ ： P ← BM25(msg, 1000)
```

### 5.2 硬过滤（集合包含判定）

```
S = { a ∈ P : K ⊆ span(a) }                          子集判定，O(|K|) 哈希查找

若 S = ∅ 且 cat_from_recovery:                        ← 错桶逃逸
    P ← P ∪ BM25(msg, 600)
    S ← { a ∈ P : K ⊆ span(a) }
若 S 仍 = ∅:  S ← P                                   绝不返回空结果
```

> **两条不可省略的保护**：
> ① `S ← P` 回退——改写场景下恢复的跨度可能含噪，宁可排序不准也不能返回空列表（保护 Hit@10）；
> ② 错桶逃逸**只扩大打分池，不改变门控的确定性判据**——门控仍看全量子集匹配，不会伪造"Rank-1 确定"信号。

### 5.3 逐步可辨识性（决定对话该走几轮）

| 已知信息 | `|S|` 中位数 | Hit@10 | MRR |
|---|---|---|---|
| 仅品类 | 184 | 0.845 | 0.502 |
| + 1 条跨度 | 26 | 0.945 | 0.698 |
| **+ 2 条跨度** | **1** | 0.995 | 0.926 |
| + 4 条跨度 | 1 | 1.000 | 0.978 |

补充：4 跨度全知时，**175/200** 的目标在桶内唯一，**147/200** 在全目录唯一。

> **这张表直接决定 `FLOOR = 3`**：第 2 轮基本收敛，第 3 轮饱和，第 4 轮起无新增信息。

### 5.4 融合打分公式

```
Score(a) = Σ_{c ∈ K} match(c, a)
         + W_BM25    · bm25_norm(a)
         + W_PRIOR   · prior(a)
         + W_PROFILE · |{ τ ∈ preference_tags : τ ⊂ corpus(a) }|

             ⎧ W_SPAN    = 12.0                                    若 c ∈ span(a)      直接证据
match(c,a) = ⎨ W_SUB     =  5.0                                    否则若 c ⊂ corpus(a) 间接证据
             ⎩ W_PARTIAL ·|terms(c) ∩ corpus(a)| / |terms(c)|      否则                弱相关
                      (2.5)

bm25_norm(a) = 1 − rank_L(a) / |L|,     L = BM25 Top-300
W_BM25 = 0.50   W_PRIOR = 0.30   W_PROFILE = 0.05

平局裁决:  prior(a) 降序  →  parent_asin 字典序        （保证确定性可复现）
```

**权重设计原理**

`12 : 5 : 2.5` 不是三个调出来的数字，是**三个证据等级**。唯一的设计约束是：**一条直接证据必须压过任意数量的弱证据**。

> 生活类比：法庭证据分级。物证压倒证人证言，证人证言压倒间接推测——你不会说"3 个间接推测 = 1 份 DNA"。
> 而 `0.30 · prior` 相当于：**在物证完全相同、无法区分两名嫌疑人时**，才轮到"谁更知名"这种软性因素出场。

**敏感性实测**（`tools/sweep_weights.py`，基准 0.95885）

| 系数 | 扫描结果 | 结论 |
|---|---|---|
| `W_SPAN` | **3.0→0.8711** ｜ 6.0→0.9589 ｜ **12.0→0.9589** ｜ 24→0.9579 | **架构级开关**，不是旋钮：降到 3.0 直接崩 8.8 个点 |
| `W_PRIOR` | **0→0.9300** ｜ 0.1→0.9576 ｜ **0.3→0.9589** ｜ 1.0→0.9589 ｜ 2.0→0.9575 | 不可或缺，但 **0.1–1.0 全平坦** |
| `W_BM25` | 0→0.9569 ｜ **0.5→0.9589** ｜ 2.0→**0.9600** ｜ 5.0→0.9545 | 默认值**不是最优**（见 §8） |
| `W_PROFILE` | **0→0.9601** ｜ **0.05→0.9589** ｜ 1.0→0.9443 | **净负收益**（见 §8） |
| `W_SUB` | 0→0.9554 ｜ **5.0→0.9589** ｜ 11.9→0.9537 | 逼近 `W_SPAN` 时阶梯被破坏 |
| `W_PARTIAL` | 0→0.9589 ｜ **2.5→0.9589** ｜ 5.0→0.9589 ｜ 11.9→0.9458 | **0–5 完全无影响**（该分支几乎不触发） |

---

## 6. L4 · 提问策略

**探针序列**：`[other ×3, feature, material, style, use_case, color, brand, budget, size, category]`

### `other` 严格占优的证明

评测器的回复匹配条件：

```python
matches = [v for v in constraints
           if v not in disclosed and (attribute == "other" or classify(v) == attribute)][:2]
```

`attribute == "other"` 使谓词恒真 ⟹ 匹配**任意**未披露约束；具名属性只匹配 `classify(v)` 归入该类者。因此对任意属性 `x`：

```
IG(other) ≥ IG(x)

其中  IG(α) = 𝔼[ log₂|S_before| − log₂|S_after(α)| ]        ∎
```

意图卡共 4 个槽位，每轮至多返回 2 条 ⟹ **两轮 `other` 即可榨干全部信息**。

> 生活类比：`other` = 全身体检（每次必出 2 项结果）；`material` = 只查血脂（很可能"无此偏好"，白问一轮）。

---

## 7. L5 · 发布门控（决策论）

### 7.1 判据推导

比较「第 `t` 轮以排名 `r` 发布」与「忍住，第 `t+1` 轮以排名 `r′` 发布」：

```
V(t, r) − V(t+1, r′) = 0.30 · (1/r − 1/r′) + 0.20 · (1/10)
                     = 0.30 · (1/r − 1/r′) + 0.02

代入 r′ = 1（下一轮信息充分时几乎必然排首位）：
    立即发布更优  ⟺  0.30/r + 0.02 > 0.30
                  ⟺  0.30/r > 0.28
                  ⟺  r < 1.07
```

> **结论：只有确信能拿 Rank-1 才发布结果，否则闭嘴提问。**

### 7.2 实现（含强制出口）

```
emit(S, t) =
    false                                      若 ranked = ∅
    true   "Layer C 兜底，无更多信息可期待"        若 ¬parsed
    true   "候选池坍缩至 1，Rank-1 确定"          若 |S| = 1
    true   "意图卡已榨干"                        若 exhausted
    true   "第 t 轮 ≥ 强制发布轮 3，信息饱和"      若 t ≥ FLOOR (=3)
    true   "连续 2 轮无新信息"                   若 t ≥ 2 ∧ no_new_info ≥ 2
    false  "剩余 |S| 个候选，E[rank] > 1"        否则
```

### 7.3 消融实测

| 策略 | Score | Hit@10 | MRR | MTTC |
|---|---|---|---|---|
| `greedy` 每轮都发 | 0.9072 | 1.000 | 0.7245 | 1.505 |
| `singleton` 只等唯一候选 | 0.7953 | **0.820** | 0.8200 | 4.035 |
| `turn3` 固定第 3 轮 | 0.9476 | 0.995 | 0.9758 | 3.130 |
| `ev` + FLOOR=2 | 0.9540 | 1.000 | 0.9280 | 2.220 |
| **`ev` + FLOOR=3（选用）** | **0.9620** | 1.000 | 0.9808 | 2.610 |
| `ev` + FLOOR=4 | 0.9587 | 1.000 | 0.9808 | 2.775 |

> **强制出口不可省**：纯 `singleton` 策略让 18% 会话永远等不到收敛，Hit@10 从 1.000 崩到 0.820。
> 生活类比：限时考试可以检查，但**铃响必须交卷**。没有交卷机制的完美主义 = 0 分。

### 7.4 `FLOOR = 3` 的稳健性验证

8 个随机半分（各 100 条），`FLOOR=3` 赢 **7/8**：

| split | half | FLOOR=2 | FLOOR=3 | FLOOR=4 | argmax |
|---|---|---|---|---|---|
| 0 | 0 | 0.95425 | **0.96115** | 0.95925 | 3 |
| 0 | 1 | 0.95023 | **0.95655** | 0.95235 | 3 |
| 1 | 0 | 0.94023 | **0.95305** | 0.95015 | 3 |
| 1 | 1 | 0.96425 | **0.96465** | 0.96145 | 3 |
| 2 | 0 | 0.94625 | **0.96000** | 0.95690 | 3 |
| 2 | 1 | **0.95823** | 0.95770 | 0.95470 | 2 |
| 3 | 0 | 0.95815 | **0.96200** | 0.96010 | 3 |
| 3 | 1 | 0.94633 | **0.95570** | 0.95150 | 3 |

> **副产品（重要）**：半分之间分数波动 **0.940–0.965**。这意味着 0.9588 这个点估计在 n=200 上带 **±0.01 抽样不确定性**。私有集 800 条会收窄，但别把它当精确数字汇报。

---

## 8. 走查案例（真实数据，可复现）

### 案例 A · `public_0006` [browsing] — 教科书式收敛

**目标**：`B071F2Z7JG` — Pro Club Men's Heavyweight Mesh Basketball Shorts

```
categories      : ['Clothing, Shoes & Jewelry', 'Sport Specific Clothing', 'Basketball', 'Men']
coarse_category : 'Basketball Men'        →  桶大小 13
price=36.5  avg_rating=4.6  rating_number=3042
prior = log1p(3042)·(4.6/5) + 0.7 = 8.0206·0.92 + 0.7 = 8.0790
隐藏卡  hard = ['polyester', '100% Polyester']
        soft = ['Drawstring closure', 'High quality mesh for maximum breathability to keep you cool']
```

| 轮 | 顾客消息 | L1 | L2 `\|K\|` | L3 池 | L5 | 输出 |
|---|---|---|---|---|---|---|
| 1 | `I'm looking for Basketball Men, but I'm still exploring.` | A | 0 | 50000→13→13 | **HOLD** `13 candidates remain` | 无 |
| 2 | `For that, what matters is: polyester; 100% Polyester.` | A | 2 | 50000→13→**7** | **HOLD** `7 candidates remain` | 无 |
| 3 | `For that, what matters is: Drawstring closure; High quality mesh…` | A | 4 | 50000→13→**1** | **EMIT** `pool collapsed to 1` | rank **1** |

**结果**：`HIT · turn 3 · rank 1 · RR 1.0` → `V = 0.5 + 0.3 + 0.2×0.8 = 0.96`

**第 3 轮打分分解（逐项可复算）**

```
目标 B071F2Z7JG:
  match('polyester')                       12.000   span exact
  match('100% polyester')                  12.000   span exact
  match('drawstring closure')              12.000   span exact
  match('high quality mesh for maximum…')  12.000   span exact
  W_BM25 × bm25_norm                        0.500   0.5 × 1.0000
  W_PRIOR × prior                           2.424   0.3 × 8.0790
  W_PROFILE × tag hits                      0.050   0.05 × 1
  ─────────────────────────────────────────────────
  TOTAL                                    50.974

亚军 B007023PU8:
  前三条约束各 12.000，第四条 partial 0.00 →  0.000
  W_BM25 0.000 + W_PRIOR 1.930 + W_PROFILE 0.050
  TOTAL                                    37.980
```

> **看点**：第 4 条约束（那句长文案）是**唯一的判别器**——它把 12 分的差距一次性拉开。这正是"跨度级精确检索"的威力：一条足够长的原文引用，胜过任何语义相似度。

> **⚠ 同时也暴露一个真实缺陷**：第 1 轮时目标**已经**在榜首（8.079 > 6.435）。若当时就发布，`V(1,1) = 1.00`；实际等到第 3 轮，`V(3,1) = 0.96`。**门控在这条会话上净亏 0.04。** 详见 §9.1。

---

### 案例 B · `public_0001` [buying] — 一条罕见跨度直接锁定

**目标**：`B09PYB7B6Z` — QIAN0813 Celtic Knot Triple Moon Pentagram Necklace

```
coarse_category : 'Jewelry Necklaces'     →  桶大小 329
prior = log1p(490)·(4.5/5) + 0.7 = 6.1964·0.9 + 0.7 = 6.2768
隐藏卡  hard = ['Material:alloy', 'Triple Moon Pentagram Symbol']
```

| 轮 | 顾客消息 | L2 `\|K\|` | L3 池 | L5 | 输出 |
|---|---|---|---|---|---|
| 1 | `…Jewelry Necklaces. A key requirement is: Material:alloy.` | 1 | 50000→329→**2** | **HOLD** `2 candidates remain` | 无 |
| 2 | `For that, what matters is: Triple Moon Pentagram Symbol; …` | 3 | 50000→329→**1** | **EMIT** `pool collapsed to 1` | rank **1** |

**结果**：`HIT · turn 2 · rank 1 · RR 1.0` → `V = 0.5 + 0.3 + 0.2×0.9 = 0.98`

```
T1 top3:  B09PYB7B6Z 14.165  |  B075KXNBNF 12.978  |  B07ZFM77HB 7.311
T2 top3:  B09PYB7B6Z 38.383  |  B075KXNBNF 12.581  |  B07ZFM77HB 8.113
                      ↑ 一条罕见跨度让分差从 1.19 拉到 25.80
```

> **看点**：`"Triple Moon Pentagram Symbol"` 在 5 万条目录里几乎唯一。**门控在这里的表现是教科书式的**：第 1 轮 `|S| = 2`，虽然目标已是榜首，但 `r` 不确定，忍住；第 2 轮坍缩到 1，确定，发布。**这一次忍耐是对的。**

---

### 案例 C · `public_0002` [intent_override] — 失败案例解剖

**目标**：`B071X54486` — Hide & Drink Full Grain Leather Men's Belt

```
coarse_category : 'Accessories Belts'     →  桶大小 258
prior = log1p(6614)·(4.3/5) + 0.7 = 8.7971·0.86 + 0.7 = 8.2655
隐藏卡  hard = ['leather', '100% Leather']    soft = ['Imported', 'Buckle closure']
覆写    turn=3, new_value = 'leather'
```

| 轮 | 顾客消息 | L2 `\|K\|` | L3 池 | L5 | 目标排名 |
|---|---|---|---|---|---|
| 1 | `…Accessories Belts. Buckle closure` | 1 | 258→**108** | HOLD | (3) |
| 2 | `For that, what matters is: leather; 100% Leather.` | 3 | 258→**21** | HOLD | (2) |
| 3 | `Actually, ignore my earlier preference. What I need is: leather.` | 3 | 258→**21** | **EMIT** `turn 3 ≥ floor 3` | **2** |

**结果**：`HIT · turn 3 · rank 2 · RR 0.5` → `V = 0.5 + 0.15 + 0.16 = 0.81`

**为什么输了——第 3 轮打分分解**

```
胜者 B08L13H7SY:                          目标 B071X54486:
  match('buckle closure')  12.000           match('buckle closure')  12.000
  match('leather')         12.000           match('leather')         12.000
  match('100% leather')    12.000           match('100% leather')    12.000
  ─────────────────────────────             ─────────────────────────────
  约束项小计               36.000           约束项小计               36.000   ← 完全打平
  W_BM25 × 0.6700           0.335           W_BM25 × 0.7900           0.395   ← 目标反而略优
  W_PRIOR × 9.2953          2.789           W_PRIOR × 8.2655          2.480   ← 输在这里
  W_PROFILE                 0.050           W_PROFILE                 0.050
  ─────────────────────────────             ─────────────────────────────
  TOTAL                    39.174           TOTAL                    38.925

  margin = 0.249  （约 39 分量级上的 0.6%）
  B08L13H7SY: 17,454 条评价, avg 4.4, $20.99  →  prior 9.2953
  B071X54486:  6,614 条评价, avg 4.3, $46.99  →  prior 8.2655
```

**三重失效叠加**：

1. **约束不具区分度** — `leather` / `100% Leather` / `buckle closure` 在 258 件皮带里是通用属性，池子只从 258 压到 21，从未坍缩到 1；
2. **覆写没带来新信息** — `new_value = 'leather'` 在第 2 轮就已披露，第 3 轮 `|K|` 纹丝不动（3→3），池子仍是 21；
3. **只能靠先验裁决** — 约束项完全打平，决定权交给流行度，而目标的评价数只有对手的 38%。

> **这不是 bug，是设计的边界**：当顾客给的信息本身无法区分两件商品时，任何检索系统都只能靠先验猜。**这条会话贡献了全系统 MRR 缺口（0.9708 vs 1.000）的十分之一。**

---

## 9. 缺点与改进方向

### 9.1 已识别的算法缺陷

| # | 缺陷 | 证据 | 影响 | 可修复性 |
|---|---|---|---|---|
| **D-1** | **门控不知道自己已经排第一** | 案例 A：T1 目标已是榜首（8.079 vs 6.435），门控仍 HOLD，净亏 0.04 | 影响 browsing 场景的部分会话 | **难**——门控只能看到 `\|S\|`，无法估计"当前 rank 是否已为 1"。需要一个校准的置信度模型，而 n=200 不足以训练 |
| **D-2** | **约束无区分度时只能靠先验猜** | 案例 C：约束项 36.000 完全打平，输在 prior 0.309 的差距 | 10/200 会话未排第 1 | **难**——信息论上限，顾客没给出可区分的信息 |
| **D-3** | **覆写轮可能零信息** | 案例 C T3：`new_value` 已在 T2 披露，`\|K\|` 3→3，池子 21→21 | intent_override 场景 | **不可修复**——由评测器行为决定 |
| **D-4** | `W_PARTIAL` 分支几乎是死代码 | 敏感性扫描：0–5 区间对结果**零影响** | 无 | 可删，但留着做改写兜底 |
| **D-5** | 画像项净负收益 | `W_PROFILE=0` → 0.9601（+0.0013） | 微小 | 见 §9.3 权衡 |
| **D-6** | `W_BM25` 默认值非最优 | 2.0 → 0.9600（+0.0011） | 微小 | 见 §9.3 权衡 |

### 9.2 残余失败的统计画像

```
10/200 会话未排第 1
  按场景: browsing 6, buying 2, intent_override 2
  按排名: rank2 ×7, rank4 ×2, rank6 ×1
  按轮次: turn3 ×9, turn4 ×1        ← 全部是被 FLOOR 强制放行的
  桶大小: 残余中位数 127  vs  全体中位数 182
```

> **反直觉发现**：残余会话的品类桶**比平均更小**。所以瓶颈**不是"候选太多"**，而是 D-2——顾客给的约束本身不具区分度。**全部修好也只值 +0.0088。**

### 9.3 不建议做的"改进"（过拟合陷阱）

| 组合 | Score | Rank-1 会话数 |
|---|---|---|
| 默认 | 0.95885 | 190/200 |
| `W_PROFILE=0` | 0.96010 | 192/200 |
| `W_BM25=2.0` | 0.95998 | 192/200 |
| `W_PROFILE=0` + `W_BM25=2.0` | **0.96065** | **193/200** |

**噪声基线**：单个会话 Rank-2→Rank-1 使 TechnicalScore 变化 **0.00075**。

最优组合相对默认只赢 **3 个会话**（+0.0018 ≈ 2.4× 噪声）。**在 n=200 上追这个量级是教科书式过拟合**——私有集 800 条用的是不同用户与目标商品，这 3 条优势完全可能反向。

**建议保持默认**：
- `W_BM25` 从 0.5 调到 2.0 纯属拟合噪声，无理论支撑；
- `W_PROFILE` 置 0 虽有理论支撑（标签无判别力），但保留它是**有意识的权衡**——用 0.0013 分换取赛题「安全个性化」创新方向的实际落地与可解释性。

### 9.4 改进方向（按投入产出排序）

**P0 · 阻塞项（当前完全缺失，却是 100% 判分载体）**

| 项 | 说明 |
|---|---|
| 官方布局提交包 | `submission/agent.py` + `requirements.txt` + `README.md` + `src/`。规则明确：**"若无法从提交包复现，主办方可判该次运行无效"** |
| Devpost 书面说明 | 方法 / 工具 / API / 库 / 额外数据集 |
| Demo 视频 | ≤4 min，YouTube 公开 |
| README 的「局限性反思」与「团队分工」 | 官方点名要求的章节 |

**P1 · 低成本降风险**

| 项 | 动作 |
|---|---|
| 清理环境变量分支 | `TJ_MODE/GATE/FLOOR/PRIOR` 在评测环境不会被设置，留着只增加不确定性。硬编码为 `general/ev/3/pop_price` |
| 干净环境复现验证 | 新目录 `git clone` → 一条命令跑出 0.9588 |
| 契约测试写进 README | `tools/test_contract.py`：67 次调用 0 异常，覆盖 FTS5 注入、5 万字符消息、null 字节、畸形 profile、`turn=0/999`、`top_k=0`、未 reset 调用 |

**P2 · 最弱的评分线：影响力与相关性（20%）**

系统针对确定性模拟器优化，文档已诚实声明——但**只有免责声明，没有正面价值论证**。三个不需要写新算法的补强：

*a) 规模化成本对比（最硬的商业论据）*
```
本方案:       p95 80 ms,   $0/轮,      可离线运行
LLM 重排方案:  p95 ~500 ms, ~$0.002/轮, 依赖外部服务

按 100 万会话/天 × 3 轮 = 300 万次调用：
  本方案 $0/天   vs   LLM 方案 ~$6,000/天
```

*b) 发布门控是可迁移的产品原则*
"没把握就先问，不要给用户一个第 2 名的列表"在真实对话式商务同样成立，且与 CIKM 2024 实证研究结论（早问、晚荐显著提升表现）一致。**本方案的决策论推导给这条经验规律提供了精确量化判据 `r < 1.07`——这是原创贡献。**

*c) 跨度检索的洞察在真实场景成立*
真实顾客确实会引用商品文案原话——"就是那个写着三年电池的"。可在自由对话 tab 演示真实风格查询。

**P3 · 建议不做**
- 残余 10 条会话：+0.0088 上限，受 D-2 信息论限制，性价比极低
- 权重微调：见 §9.3，纯噪声

### 9.5 战略结论

> 技术分从 0.9588 再挤 0.009，对总评影响约 `0.009 × 35% ≈ 0.3%`；
> 而「影响力与相关性」从"只有免责声明"变成"有量化业务论据"，可能是 20% 权重上**几个百分点**的差距。
>
> **停止优化技术分，把时间投到 P0 + P2。**

---

## 10. 复现方式

| 内容 | 命令 |
|---|---|
| 主指标 | `python -m evaluator.local_evaluator --catalog data/catalog.jsonl --dataset data/public_set.jsonl` |
| 可辨识性表（§5.3） | `python tools/probe_selectivity.py` |
| 改写鲁棒性（§3.4） | `python tools/robust_eval.py --catalog … --dataset …` |
| 权重敏感性（§5.4） | `python tools/sweep_weights.py --catalog … --dataset …` |
| 契约与对抗测试（§9.4） | `python tools/test_contract.py --catalog …` |
| 资源基准 | `python tools/bench.py` |
| 演示界面 | `cd solution && python run_demo.py` |

走查案例的逐层轨迹可在演示界面「标注会话回放」中选择对应 `sample_id` 实时复现。

---

*本文所有数值均来自官方评测器与 `solution/tools/` 下脚本的实跑输出。*
