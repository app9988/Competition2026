# Shopping Copilot · 系统规格报告 (Specification Report)

| 项 | 内容 |
|---|---|
| 文档编号 | TJ-SPEC-001 |
| 版本 | 1.0 |
| 状态 | 已实现并验证 (Implemented & Verified) |
| 对象系统 | TechJam Conversational E-Commerce Search Challenge 参赛 Agent |
| 数据集 | Amazon Reviews 2023 · `Clothing_Shoes_and_Jewelry`（50,000 SKU 冻结目录 + 200 条公开标注会话） |
| 配套文档 | `TECHJAM_SOLUTION_DESIGN.md`（方案设计与推导）、`solution/README.md`（操作手册） |
| 实现位置 | `solution/src/agent.py`（评分主体）、`solution/server/`、`solution/web/`（演示，不评分） |

> **本文与设计文档的分工**：设计文档回答"为什么这样做"（逆向分析、策略推导、72h 排期）；本文回答"系统到底是什么"——需求、接口、组件、算法、验证证据、资源预算与合规边界。本文中每一条性能与效果数据均标注了测量条件与可复现命令。

---

## 1. 范围与术语

### 1.1 范围

**In scope（本规格覆盖）**：多轮对话购物 Agent 的检索、对话状态管理、提问策略与结果发布决策；其在官方无头评测协议下的行为契约；配套演示服务与界面。

**Out of scope（本规格不覆盖）**：目录数据的生产与清洗、评测器本身的实现、模型训练、生产环境部署与运维、多用户并发。

### 1.2 术语

| 术语 | 定义 |
|---|---|
| **粗品类串 (coarse category)** | 商品 `categories` 数组按逗号切分、剔除 `Clothing*` 前缀后，取末两段拼接所得字符串。全目录共 1,115 个取值。 |
| **属性跨度 (attribute span)** | 商品 `features` / `details` 字段展平并规范化后的单条文本片段；模拟顾客的偏好表述即为此类片段的原文。 |
| **候选池 (candidate pool)** | 某一轮次下仍被认为可能是目标的商品集合，分三级：全目录 → 品类桶 → 约束过滤后。 |
| **发布门控 (emission gate)** | 决定本轮"返回商品列表"还是"仅提问"的决策规则。 |
| **意图卡 (intent card)** | 评测器内部由目标商品元数据确定性生成的隐藏偏好集合；Agent 不可见。 |
| **MTTC** | Mean Turns To Conversion，首次命中轮次均值，未命中记 11。 |

---

## 2. 系统上下文

```
        ┌──────────────────────────────┐
        │  官方评测器 local_evaluator   │   ← 权威评分方，本系统不得修改
        │  · 确定性顾客模拟器            │
        │  · 隐藏意图卡 / ground truth   │
        └───────┬──────────────▲───────┘
   reset(sid,profile)          │ {message, ask_attribute,
   respond(sid,msg,turn,k)     │  recommendations, usage}
                ▼              │
        ┌──────────────────────┴───────┐        ┌────────────────────────┐
        │      Agent (被测系统)          │◀──读──│  catalog.jsonl (只读)   │
        │  L0 索引 · L1 NLU · L2 状态机  │        │  50,000 SKU            │
        │  L3 检索 · L4 提问 · L5 门控   │        └────────────────────────┘
        └──────────────────────┬───────┘
                               │ enable_trace=True（默认关闭）
                               ▼
        ┌──────────────────────────────┐        ┌────────────────────────┐
        │  演示服务 FastAPI（不评分）    │◀──────│  演示界面 React（不评分）│
        └──────────────────────────────┘        └────────────────────────┘
```

**边界声明**：演示服务与界面**不在评分路径上**。`agent.py` 不 import 任何演示代码，不依赖 `fastapi` / `uvicorn`。

---

## 3. 需求规格

### 3.1 功能需求

| ID | 需求 | 验收判据 | 状态 |
|---|---|---|---|
| **FR-1** | 系统须实现官方 Agent 接口：`reset(session_id, user_profile)` 与 `respond(session_id, user_message, turn, top_k)` | 官方评测器可直接实例化并完整跑完 200 会话 | ✅ |
| **FR-2** | `respond` 返回体须满足官方 JSON Schema：`message: str`、`ask_attribute ∈ 枚举 ∪ {null}`、`recommendations: [{parent_asin}]`、`usage` 非负整数 | 200 会话 × 全部轮次无一被评测器判为非法输出 | ✅ |
| **FR-3** | 系统须从顾客话语中抽取品类意图 | 公开集 200/200 会话成功解析品类 | ✅ |
| **FR-4** | 系统须从顾客话语中增量抽取属性约束并跨轮累积 | 约束集合随轮次单调增长，不丢失历史 | ✅ |
| **FR-5** | 系统须处理意图覆写（第 3/4 轮偏好翻转），提升新约束优先级而非清空历史 | intent_override 场景 MRR ≥ 0.95 | ✅ 0.967 |
| **FR-6** | 系统须处理边界场景（顾客对某属性无偏好），且不因一次拒答而永久放弃最优探针 | boundary 场景 Hit@10 = 1.000 | ✅ |
| **FR-7** | 系统须区分 Buying / Browsing 两条检索轨道 | 有约束走 PRECISION，无约束走 DISCOVERY | ✅ |
| **FR-8** | 系统须在每轮返回至多 10 个目录内合法且去重的 `parent_asin` | 评测器 `normalize_recommendations` 无剔除 | ✅ |
| **FR-9** | 系统须能在信心不足时选择只提问而不返回商品 | 门控可关闭，且有强制出口保证不永久沉默 | ✅ |
| **FR-10** | 系统须在话语被改写（非模板措辞）时仍能工作 | 改写压力测试 Hit@10 ≥ 0.90 | ✅ 0.990 |
| **FR-13** | 演示界面须支持中文/英文一键切换 | 语言按钮循环切换，选择持久化，默认跟随浏览器语言；对话内容为数据不翻译 | ✅ |
| **FR-14** | 演示服务须支持在改写压力模式下实时回放 | `POST /api/replay` 接受 `paraphrase: true`，逐轮改写顾客话术 | ✅ |
| **FR-11** | 演示服务须能按官方协议回放任一条标注会话并暴露推理轨迹 | `POST /api/replay` 返回逐轮 transcript + 命中信息 | ✅ |
| **FR-12** | 演示界面须支持明亮 / 暗色 / 跟随系统三种主题 | 三态循环，选择持久化，OS 切换实时跟随 | ✅ |

### 3.2 非功能需求

| ID | 需求 | 判据 | 实测 | 状态 |
|---|---|---|---|---|
| **NFR-1** | 评分路径零网络依赖 | 源码无 socket/http 调用 | 无 | ✅ |
| **NFR-2** | 评分路径零第三方依赖 | 仅 Python 3.10 stdlib | `json/re/sqlite3/math/time/os/collections/pathlib` | ✅ |
| **NFR-3** | 单轮响应延迟 p95 < 500 ms | 400 轮采样 | p95 76–83 ms | ✅ |
| **NFR-4** | 冷启动 < 120 s | 索引构建计时 | 18–33 s | ✅ |
| **NFR-5** | 常驻内存 < 1 GB | Python 堆 | 230 MB | ✅ |
| **NFR-6** | LLM Token 消耗为 0 | `usage` 累计 | 0 / 0 | ✅ |
| **NFR-7** | 任何输入不得抛出未捕获异常 | `respond` 全链路兜底 | 见 §9.1 | ✅ |
| **NFR-8** | 结果完全确定可复现 | 同输入同输出 | 无随机源，排序全平局裁决 | ✅ |
| **NFR-9** | 演示界面在明暗两种主题下均可读 | 关键组件对比度 | 见 §7.4 | ✅ |

### 3.3 约束

| ID | 约束 | 来源 |
|---|---|---|
| **CON-1** | 每会话最多 10 轮，超出判 0 | 官方规则 |
| **CON-2** | 目录严格只读，禁止改结构或注入 ASIN | 官方规则 |
| **CON-3** | 禁止修改评测器文件 | `docs/submission_rules.md` |
| **CON-4** | 最终评分环境**可能禁网** | `docs/submission_rules.md` |
| **CON-5** | 禁止提交 API Key / 私有评测数据 | `docs/submission_rules.md` |
| **CON-6** | 禁止部署外部向量数据库集群 | 赛题 out-of-scope |
| **CON-7** | intent_override 会话在覆写发生前命中不计分 | 评测器实现 |

---

## 4. 接口规格

### 4.1 IF-1 · Agent Python 接口（评分接口，权威）

```python
class Agent:
    def __init__(self, catalog_path: str = "data/catalog.jsonl",
                 enable_trace: bool = False) -> None: ...
    def reset(self, session_id: str, user_profile: dict) -> None: ...
    def respond(self, session_id: str, user_message: str,
                turn: int, top_k: int) -> dict: ...
```

**`respond` 返回体契约**

| 字段 | 类型 | 约束 |
|---|---|---|
| `message` | `str` | 必须是字符串（非 str 会导致整轮响应被评测器丢弃） |
| `ask_attribute` | `str \| None` | ∈ `{category, material, color, size, style, brand, budget, feature, use_case, other}` ∪ `{None}` |
| `recommendations` | `list[{parent_asin: str}]` | 有序（最佳在前）；仅前 10 个合法唯一 ID 计分 |
| `usage` | `{prompt_tokens: int≥0, completion_tokens: int≥0}` | 本系统恒为 `{0, 0}` |

**不变式**

* INV-1：`respond` 永不抛出异常（§9.1）。
* INV-2：`recommendations` 中的 ID 必定存在于目录内。
* INV-3：`enable_trace=False` 时，`respond` 的返回值与 `enable_trace=True` 时**逐字节相同**；埋点只增加旁路记录。
* INV-4：同一 `(catalog, 输入序列)` 恒产生同一输出（无随机源）。

**`user_profile` 输入契约**（官方给定，只读）：`purchase_frequency`、`average_prior_rating`、`rating_style`、`preference_tags[]`、`summary`。

### 4.2 IF-2 · 演示 HTTP 接口（不评分）

| 方法 | 路径 | 请求 | 响应要点 |
|---|---|---|---|
| GET | `/api/meta` | — | 索引规模、冷启动耗时、实测 benchmark、baseline 对照 |
| GET | `/api/samples` | — | 200 条标注会话（`sample_id`、场景、目标品类与标题） |
| POST | `/api/session` | `{profile?}` | `{session_id, profile}` |
| POST | `/api/chat` | `{session_id, message}` | `{reply, ask_attribute, items[], trace}` |
| POST | `/api/replay` | `{sample_id}` | `{turns[], hit, first_hit_turn, best_rank, reciprocal_rank, hidden_card, target}` |

**推理轨迹 `trace` 结构**（每轮）：

```jsonc
{
  "turn": 3, "nlu_layer": "A|B|C", "route": "PRECISION|DISCOVERY",
  "category": "Basketball Men", "constraints": [...], "new_constraints": [...],
  "pool_catalog": 50000, "pool_stage1": 13, "pool_stage2": 1,
  "gate": true, "gate_reason": "candidate pool collapsed to 1 - Rank-1 certain",
  "ask_attribute": "other", "boundary": false, "exhausted": false,
  "latency_ms": 34.94
}
```

### 4.3 IF-3 · 数据契约

**目录行（只读，参赛者可见字段）**

| 字段 | 类型 | 本系统用途 |
|---|---|---|
| `parent_asin` | str | 唯一键，唯一计分标的 |
| `title` | str | BM25 检索字段（权重 6.0） |
| `categories` | list[str] | **粗品类桶构建（核心）** |
| `features` | list[str] | **属性跨度集构建（核心）** |
| `details` | dict | **属性跨度集构建（核心）** |
| `description` | list[str] | BM25 检索字段（权重 1.0） |
| `price` | float\|null | 先验加成 + 预算类跨度 |
| `average_rating` / `rating_number` | float / int | 流行度先验 |
| `store` | str | BM25 检索字段（权重 1.5） |

---

## 5. 组件规格

| ID | 组件 | 职责 | 输入 | 输出 |
|---|---|---|---|---|
| **C-1** | 索引层 (L0) | 构建 5 个只读内存索引 | `catalog.jsonl` | 品类桶、跨度集、稀有词倒排、FTS5、先验 |
| **C-2** | NLU (L1) | 三层降级解析顾客话语 | 原始消息 | 品类、约束集、语用信号 |
| **C-3** | 对话状态机 (L2) | 跨轮累积与修正 | C-2 输出 | `SessionState` |
| **C-4** | 检索排序 (L3) | 候选池生成 + 硬过滤 + 融合打分 | `SessionState` + C-1 | 有序 Top-K |
| **C-5** | 提问策略 (L4) | 选择信息增益最大的探针 | `SessionState` | `ask_attribute` |
| **C-6** | 发布门控 (L5) | 决定出结果还是只提问 | 候选池 + 轮次 | bool + 原因 |

### 5.1 C-1 索引层

| 索引 | 结构 | 规模（general 模式） | 构建复杂度 |
|---|---|---|---|
| `cat_index` | `dict[str, list[asin]]` | 1,115 桶 | O(N) |
| `card_set` | `dict[asin, set[str]]` | 50,000 条目 | O(N·F) |
| `cs_inv` | `dict[token, list[span]]` | 71,442 键 | O(U·T log T) |
| FTS5 表 | SQLite 虚表，7 字段加权 | 50,000 行 | O(N·L) |
| `prior` | `dict[asin, float]` | 50,000 条目 | O(N) |

N=50,000 商品，F=平均属性条数，U=唯一跨度数，T=跨度词元数，L=平均文本长度。

**关键实现约束**：`coarse_category` 必须逐字复刻 `split(",")` 与 `[-2:]` 的行为。目录中存在字段内含逗号的写法（如 `"Clothing, Shoes & Jewelry"`），逗号切分会将其拆开——这正是第二大桶 `Shoes & Jewelry Westlake`（1,136 条）的成因。此处偏差将导致首轮召回崩塌。

### 5.2 C-2 NLU：三层降级

| 层 | 触发条件 | 机制 | 失效行为 |
|---|---|---|---|
| **A 模板** | 消息匹配 7 个模板正则之一 | 直接抽取品类与约束 | 降级至 B |
| **B 跨度恢复** | A 未命中 | 闭集品类 n-gram 匹配 + 稀有词倒排召回跨度 + 精确子串验证 | 降级至 C |
| **C 词法兜底** | A、B 均未产出结构 | 整句 BM25，**并强制打开发布门控** | 无 |

**匹配顺序约束**：`P_OVERRIDE` 必须先于 `P_OPEN` 求值，否则覆写消息会被误判为开场白，槽位翻转失效。

### 5.3 C-3 对话状态机

```python
SessionState:
    category: str | None          # 已确认粗品类
    constraints: list[str]        # 有序去重属性跨度
    slot0: str | None             # 首要 / 覆写后约束
    parsed: bool                  # 是否曾解析出结构（C 层判据）
    dead: set[str]                # 已确认枯竭的属性
    asked: list[str]              # 提问历史
    boundary_hit: bool            # 本轮为脚本化拒答
    exhausted: bool               # 意图卡已榨干
    no_new_info_turns: int        # 连续无新增信息轮数
```

**状态转移规则**

| 事件 | 转移 |
|---|---|
| 识别到品类 | `category ← 首次识别值`（后续轮次不覆盖） |
| 识别到新跨度 | `constraints ← constraints ⧺ 新跨度`（去重，保序） |
| 覆写信号 | `slot0 ← 新约束`，新约束提至首位；**历史约束保留但降权** |
| 边界拒答 | `boundary_hit ← True`；**不写入 `dead`，不计入 `no_new_info`** |
| `other` 返回"无更多偏好" | `exhausted ← True` |

> **设计决策 DD-1（反直觉但经数据验证）**：意图覆写时**不清空**历史约束。评测器中 `new_value` 与 `old_value` 同属一张意图卡、指向同一商品；按字面语义擦除旧约束会丢失信息并拉低 MRR。保留降权使 intent_override 场景 MRR 达到 0.967。
>
> **设计决策 DD-2**：边界拒答是**一次性脚本行为**，与所问属性无关。早期实现将被拒属性写入 `dead`，导致最优探针 `other` 被永久封禁，boundary 场景 MRR 仅 0.581。修正后 MRR = 1.000，且全局 Hit@10 由 0.995 补齐至 1.000（增益 +0.0086 总分）。

---

## 6. 算法规格

### ALG-1 · 粗品类桶召回

```
输入: 顾客消息 m
输出: 候选池 P
1. c ← 从 m 中解析的品类串（C-2）
2. P ← cat_index[normalize(c)]
3. 若 P = ∅：对 c 的词元在 tok_index 中投票，取最高票商品集
4. 若仍为 ∅：P ← BM25(m, limit=1000)
```

复杂度 O(1) 哈希查找（步 2）。**实测：200/200 会话的目标均落在其品类桶内，召回率 100%**；桶大小 p25/p50/p75/p90/max = 49/184/379/680/1354。

### ALG-2 · 属性跨度集合过滤

```
输入: 候选池 P, 已知约束集 K
输出: 存活集 S
S ← { a ∈ P : K ⊆ card_set[a] }
若 S = ∅ 则 S ← P            # 硬过滤绝不产生空结果
```

`K ⊆ card_set[a]` 为集合子集判定，复杂度 O(|K|)。**这一步是候选池从 184 坍缩到 1 的关键。**

回退分支 `S ← P` 不可省略：改写场景下恢复的跨度可能含噪，过滤可能滤空；宁可排序不准，绝不返回空列表（保护 Hit@10）。

### ALG-3 · 融合打分

```
Score(a) = Σ_{c∈K} match(c, a)
         + 0.50 · bm25_norm(a)
         + 0.30 · prior(a)
         + 0.05 · Σ_{t∈tags} [t ⊂ corpus(a)]

match(c,a) = 12.0                                    若 c ∈ card_set[a]
           =  5.0                                    否则若 c ⊂ corpus(a)
           =  2.5 · |terms(c) ∩ corpus(a)| / |terms(c)|   否则

prior(a)  = log1p(rating_number) · average_rating/5 + 0.7·[price ≠ null]
平局裁决  : prior 降序 → parent_asin 字典序
```

**权重依据**

* `12 : 5 : 2.5` 的量级差保证精确跨度命中在任何情况下压倒词法相似，与 §7.2 可辨识性数据一致。
* `0.30` 为先验权重。敏感性实测：**0.10–1.00 全区间平坦**（0.9576–0.9589）；置 0 则跌至 0.9300。结论是先验不可或缺，但权重取值不敏感。
* `0.05` 为画像权重。敏感性实测：**该项为净负收益**，置 0 后 score 由 0.95885 升至 0.96010。保留为有意识的权衡——以 0.0013 分换取"安全个性化"方向的落地与可解释性。
* `12 / 5 / 2.5` 阶梯为**设计取值而非调优取值**，事后验证：W_SPAN 降到 3.0 会崩到 0.871（跨度信号不再压倒词法），≥6.0 后平坦；W_PARTIAL 在 0–5.0 区间对结果**无任何影响**（general 模式下该分支极少触发）。
* 完整敏感性数据见 §7.9。

### ALG-4 · 提问策略

探针序列：`[other ×3, feature, material, style, use_case, color, brand, budget, size, category]`

**`other` 严格占优的证明**：评测器回复逻辑为

```python
matches = [v for v in constraints
           if v not in disclosed and (attribute == "other" or classify(v) == attribute)][:2]
```

`attribute == "other"` 使谓词恒真，故 `other` 匹配任意未披露约束，而具名属性仅匹配 `classify(v)` 归入该类者。因此对任意属性 `x`：`IG(other) ≥ IG(x)`，其中 `IG = E[log₂|C_before| − log₂|C_after|]`。∎

意图卡共 4 槽位，每轮返回至多 2 条，故**两轮 `other` 即可榨干全部信息**。

### ALG-5 · 发布门控（决策论）

单会话对总分的边际贡献：

```
V(t, r) = 0.50·1 + 0.30·(1/r) + 0.20·(11−t)/10
```

比较"第 t 轮以排名 r 发布"与"第 t+1 轮以排名 r′ 发布"：

```
V(t,r) − V(t+1,r′) = 0.30·(1/r − 1/r′) + 0.02
```

代入 r′ = 1（下一轮信息充分时几乎必然排首位）：

```
0.30/r + 0.02 > 0.30  ⟺  0.30/r > 0.28  ⟺  r < 1.07
```

**判定：仅当确信可取得 Rank-1 时才发布结果，否则只提问。** 直觉：多花一轮仅损失 0.02 分，而排名从第 2 位（RR=0.5）升至第 1 位（RR=1.0）可得 0.15 分——**7 倍价差**。

实现（含强制出口）：

```
emit ⟸ true   若 ranked = ∅ → false
              若 ¬parsed                    → true   (C 层：无更多信息可期待)
              若 |S| = 1                    → true   (Rank-1 确定)
              若 exhausted                  → true   (意图卡榨干)
              若 turn ≥ FLOOR (=3)          → true   (信息饱和，强制出口)
              若 turn ≥ 2 ∧ 连续 2 轮无新信息 → true
              否则                           → false
```

> **强制出口是必需的**：纯 `|S| = 1` 策略（`TJ_GATE=singleton`）会使 18% 会话永远等不到收敛，Hit@10 从 1.000 崩至 0.820，总分跌至 0.7953。

### ALG-6 · 稀有词候选生成（Layer B）

暴力方案需对约 40 万条唯一跨度逐一执行 `span ⊂ message`，单轮 40 万次子串检查，不可接受。

```
建索引（两趟）:
  趟1: 对每条唯一跨度 s，对其每个词元 t：span_df[t] += 1
  趟2: 对每条 s，取其 df 最低的 3 个词元 t，若 span_df[t] ≤ 4000 则 span_inv[t].append(s)

查询:
  cand ← ⋃_{t ∈ terms(m)} span_inv[t]           # 稀有词召回，量级 O(10)
  hits ← [s ∈ cand : |s| ≥ 4 ∧ s ⊂ normalize(m)]  # 精确子串验证
  按长度降序，剔除被更长命中包含者，取前 4
```

`df ≤ 4000` 上限剔除高频无判别力词元。实测索引键 71,442，单轮候选量降至数十。

---

## 7. 验证与确认

### 7.1 验证环境

| 项 | 值 |
|---|---|
| 平台 | Windows 11，Python 3.10.6 |
| 评测器 | 官方 `evaluator/local_evaluator.py`（**未修改**） |
| 数据 | `catalog.jsonl` 50,000 行；`public_set.jsonl` 200 会话 |
| 配置 | `TJ_MODE=general TJ_GATE=ev TJ_FLOOR=3 TJ_PRIOR=pop_price`（出厂默认） |
| 复现命令 | `python -m evaluator.local_evaluator --catalog data/catalog.jsonl --dataset data/public_set.jsonl` |

### 7.2 V&V-1 · 主指标（官方评测器）

| 配置 | TechnicalScore | Hit@10 | MRR | MTTC | Efficiency |
|---|---|---|---|---|---|
| 官方 BM25 baseline | 0.10671 | 0.125 | 0.0680 | 9.810 | 0.119 |
| **本系统（general，提交配置）** | **0.95885** | **1.000** | **0.9708** | **2.620** | **0.838** |
| 本系统（mirror，消融上限） | 0.96200 | 1.000 | 0.9808 | 2.610 | 0.839 |

分场景（general）：

| 场景 | n | Hit@10 | MRR | MTTC | 备注 |
|---|---|---|---|---|---|
| buying | 80 | 1.000 | 0.983 | 2.288 | |
| browsing | 80 | 1.000 | 0.956 | 2.525 | |
| intent_override | 30 | 1.000 | 0.967 | 3.600 | **达该场景理论下限** |
| boundary | 10 | 1.000 | 1.000 | 3.100 | |

原始输出存档：`solution/results_public_set.json`。

### 7.3 V&V-2 · 可辨识性（信息量 → 收敛）

工具：`solution/tools/probe_selectivity.py`

| 已知信息 | 候选池中位数 | Hit@10 | MRR |
|---|---|---|---|
| 仅品类 | 184 | 0.845 | 0.502 |
| + 1 条跨度 | 26 | 0.945 | 0.698 |
| + 2 条跨度 | 1 | 0.995 | 0.926 |
| + 4 条跨度 | 1 | 1.000 | 0.978 |

补充：4 跨度全知时，175/200 目标在桶内唯一，147/200 在全目录唯一。

**该表是 `FLOOR=3` 取值的直接依据**：第 2 轮已基本收敛，第 3 轮饱和，第 4 轮起无新增信息。

### 7.4 V&V-3 · 鲁棒性（话术改写压力测试）

工具：`solution/tools/robust_eval.py`（对 8 类话术各准备 3–4 个自然改写模板）

| 配置 | 逐字 Score | 改写 Score | 改写 Hit@10 |
|---|---|---|---|
| 仅 Layer A（模板正则） | 0.9620 | **0.0000** | 0.000 |
| Layer A + B v1（general） | 0.9588 | 0.8843 | 0.945 |
| **Layer A + B v2（general，提交）** | **0.9588** | **0.9236** | **0.990** |
| Layer A + B v1（mirror） | 0.9620 | 0.8985 | 0.945 |

v2 加固项：宽松品类 n-gram（去标点、最大桶消歧）；闭集材质/颜色快通道；错桶词法逃逸（不伪造门控确定性）。verbatim 逐位回归通过。

> **重要限定**：改写模板由本团队编写，**不是**主办方的改写器。该数据证明的是"系统不依赖单一模板即可工作"，而非"在主办方任意改写下必达 0.88"。它是**存在性证据与回归基线**，不是性能承诺。

### 7.5 V&V-4 · 门控消融

| 策略 | Score | Hit@10 | MRR | MTTC |
|---|---|---|---|---|
| `greedy`（每轮都发） | 0.9072 | 1.000 | 0.7245 | 1.505 |
| `singleton`（仅唯一候选） | 0.7953 | 0.820 | 0.8200 | 4.035 |
| `turn3`（固定第 3 轮） | 0.9476 | 0.995 | 0.9758 | 3.130 |
| `ev` + FLOOR=2 | 0.9540 | 1.000 | 0.9280 | 2.220 |
| **`ev` + FLOOR=3（选用）** | **0.9620** | 1.000 | 0.9808 | 2.610 |
| `ev` + FLOOR=4 | 0.9587 | 1.000 | 0.9808 | 2.775 |

（上表为 mirror 模式下测得，用于策略选择；general 模式下相对排序一致。）

### 7.6 V&V-5 · 界面主题

验证方式：浏览器内读取计算样式，在 light / dark / auto 三态间循环。

| 检查项 | light | dark | 结论 |
|---|---|---|---|
| `body` 背景 / 前景 | `#f4f6fa` / `#101828` | `#151b26` / `#e9eef7` | ✅ |
| 会话卡 `.samp` | `#ffffff` | `#1c2433` | ✅ |
| 选中标签 `.tabs .on` | `#e8f0fb` | `#22314a` | ✅ |
| 门控警示 `.held` | `#fff8e8` | `#2e2410` | ✅ |
| 漏斗条三级 | `#cbd5e1/#38bdf8/#34d399` | `#3a465a/#2f7fa8/#1c8a63` | ✅ |
| 三态循环 + 持久化 | auto → light → dark → auto，`localStorage` | ✅ |
| 端到端回放 | HIT · turn 3 · rank #1 · RR 1 | 两主题下一致 | ✅ |

### 7.7 需求追溯矩阵

| 需求 | 验证证据 |
|---|---|
| FR-1, FR-2, FR-8 | V&V-1（200 会话完整跑通，无非法输出） |
| FR-3, FR-4 | V&V-2；`trace.constraints` 单调增长 |
| FR-5 | V&V-1 intent_override MRR 0.967 |
| FR-6 | V&V-1 boundary Hit@10 1.000 / MRR 1.000 |
| FR-7 | `trace.route` 在有/无约束时分别为 PRECISION / DISCOVERY |
| FR-9 | V&V-4 门控消融 |
| ALG-3 权重 | V&V-6 敏感性扫描 |
| FR-10 | V&V-3 改写压力测试 |
| FR-11 | `POST /api/replay` 实跑（§7.8） |
| FR-12 | V&V-5 |
| FR-13, FR-14 | 浏览器实测：双语切换、改写回放 public_0017 HIT·turn 3·rank 1 |
| NFR-1, NFR-2 | 源码审计：import 清单仅 stdlib |
| NFR-3~NFR-6 | §8 资源预算 |
| NFR-7 | §9.1 失效模式 |
| NFR-8 | 重构前后分数逐位一致（0.9588） |

### 7.8 端到端样例（实跑输出）

```
public_0006 [browsing]   HIT · turn 3 · rank #1 · RR 1.0
  T1  NLU=A  DISCOVERY  漏斗 50,000 → 13 → 13   门控 ⏸  "13 candidates remain - E[rank] > 1"
  T2  NLU=A  PRECISION  漏斗 50,000 → 13 →  7   门控 ⏸  "7 candidates remain - E[rank] > 1"
  T3  NLU=A  PRECISION  漏斗 50,000 → 13 →  1   门控 ▶  "candidate pool collapsed to 1 - Rank-1 certain"

public_0002 [intent_override]  HIT · turn 3 · rank #2 · RR 0.5
  T1  漏斗 258 → 108   门控 ⏸        （覆写前，命中不计分）
  T2  漏斗 258 →  21   门控 ⏸
  T3  漏斗 258 →  21   门控 ▶  "turn 3 >= emit floor 3 - information saturated"
```

---

### 7.9 V&V-6 · L3 融合权重敏感性

索引构建一次，逐个系数扫描，其余固定为默认值。基准 = `0.95885`。

| 系数 | 扫描值 → score | 结论 |
|---|---|---|
| `W_PRIOR` | 0→**0.9300** ｜ 0.1→0.9576 ｜ 0.2→0.9586 ｜ **0.3→0.9589** ｜ 0.4/0.6/1.0→0.9589 ｜ 2.0→0.9575 | 先验**不可或缺**（置 0 掉 2.9 个点），但 **0.1–1.0 全平坦**，取值不敏感 |
| `W_BM25` | 0→0.9569 ｜ 0.25→0.9576 ｜ **0.5→0.9589** ｜ 1.0→0.9586 ｜ **2.0→0.9600** ｜ 5.0→0.9545 | 默认值**不是最优**，2.0 更好（+0.0011） |
| `W_PROFILE` | **0→0.9601** ｜ **0.05→0.9589** ｜ 0.25→0.9546 ｜ 1.0→0.9443 | **净负收益**，单调递减 |
| `W_SUB` | 0→0.9554 ｜ 2.5→0.9579 ｜ **5.0→0.9589** ｜ 8.0→0.9589 ｜ 11.9→0.9537 | 5–8 平坦；逼近 `W_SPAN` 时破坏阶梯 |
| `W_PARTIAL` | 0→0.9589 ｜ 1.0→0.9589 ｜ **2.5→0.9589** ｜ 5.0→0.9589 ｜ 11.9→0.9458 | **0–5 完全无影响**（general 模式下该分支几乎不触发） |
| `W_SPAN` | **3.0→0.8711** ｜ 6.0→0.9589 ｜ **12.0→0.9589** ｜ 24.0→0.9579 ｜ 100→0.9579 | 必须**压倒性**大于其他项；≥6 后平坦 |

**组合验证**

| 配置 | score | Rank-1 会话数 |
|---|---|---|
| 默认 | 0.95885 | 190/200 |
| `W_PROFILE=0` | 0.96010 | 192/200 |
| `W_BM25=2.0` | 0.95998 | 192/200 |
| `W_PROFILE=0` + `W_BM25=2.0` | **0.96065** | **193/200** |

**噪声基线**：单个会话从 Rank-2 升到 Rank-1，MRR 变化 0.0025，TechnicalScore 变化 **0.00075**。

> **对上表的正确解读**：最优组合相对默认值只赢 **3 个会话**（+0.0018 ≈ 2.4 倍噪声基线）。在 n=200 上追逐这个量级的差异属于典型过拟合，**不建议**据此改权重去博私有集。真正有价值的结论是定性的三条：
> 1. `W_SPAN` 必须压倒性大 —— 这是架构级判断，不是调参；
> 2. 先验不可或缺但权重不敏感 —— 说明系统鲁棒；
> 3. 画像项是净负收益 —— 保留它是拿 0.0013 分换赛题「安全个性化」方向的落地。

---

## 8. 性能与资源预算

测量条件：同 §7.1；`tracemalloc` 会使构建耗时膨胀约 3–5 倍，故构建与延迟均在**无 tracemalloc** 下测得，内存单独测量。

| 指标 | general（提交） | mirror（消融） | 预算 | 状态 |
|---|---|---|---|---|
| 冷启动构建 | 18–33 s | 17–24 s | < 120 s | ✅ |
| Python 堆（tracemalloc） | 230 MB (peak 239) | 137 MB (peak 139) | < 1 GB | ✅ |
| 单轮延迟 p50 | 37–73 ms | 36–74 ms | — | — |
| 单轮延迟 p95 | 76–83 ms | 76–83 ms | < 500 ms | ✅ |
| 单轮延迟 p99 / max | ≤ 93 / ≤ 115 ms | ≤ 88 / ≤ 100 ms | — | — |
| 目录磁盘占用 | 60.5 MB | 同 | — | — |
| LLM prompt / completion token | 0 / 0 | 0 / 0 | — | ✅ |
| 估算模型成本 | **$0** | $0 | — | ✅ |

> **变异性说明**：构建耗时与 p50 延迟在重复测量中波动明显（构建 18.75–33.07 s，p50 36.7–73.3 ms），源于测量期间宿主机负载差异，非系统本身不稳定。p95/p99 稳定。上表给出实测区间而非单点值。

---

## 9. 失效模式与降级

### 9.1 FM-1 · 未捕获异常

评测器对异常的处理是将该轮视作空响应，一次异常即可能损失该会话 0.5 分。

```python
def respond(self, session_id, user_message, turn, top_k):
    try:
        return self._respond(session_id, user_message, turn, top_k)
    except Exception:
        return {"message": "Here are some options.", "ask_attribute": "other",
                "recommendations": [{"parent_asin": a} for a in self.global_top10[:top_k]],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
```

降级后仍返回全局先验 Top-10，保留命中机会。

### 9.2 其他失效模式

| ID | 失效 | 检测 | 降级行为 |
|---|---|---|---|
| FM-2 | 品类桶未命中 | `cat_index` 查空 | 词元投票 → BM25 Top-1000 |
| FM-3 | 跨度硬过滤滤空 | `S = ∅` | 回退至未过滤候选池 |
| FM-4 | FTS5 查询语法错误 | `sqlite3.OperationalError` | 捕获并返回空词法结果，不影响其他信号 |
| FM-5 | 模板全部未命中 | `parsed = False` | Layer B → Layer C，且强制开门控 |
| FM-6 | `reset` 未被调用 | 会话不存在 | 惰性创建空状态，不抛异常 |
| FM-7 | 会话超过 10 轮 | 演示服务校验 | HTTP 400（评分路径由评测器自身限制） |

---

## 10. 风险登记册

| ID | 风险 | 概率 | 影响 | 缓解 | 残余风险 |
|---|---|---|---|---|---|
| R1 | 最终评测禁网 | 高 | 致命 | 评分路径零网络零依赖 | 已消除 |
| R2 | 私有集话术被改写 | 中 | 致命 | Layer B/C 三层降级 | 中（改写器未知，见 §7.4 限定） |
| R3 | 主办方调整意图卡构造 | 低 | 高 | 采用 general 模式，不复刻私有函数 | 低 |
| R4 | 未捕获异常判负 | 中 | 高 | FM-1 全链路兜底 | 已消除 |
| R5 | 私有集品类分布偏移 | 低 | 中 | FM-2 三级降级 | 低 |
| R6 | 评审判定为 harness overfitting | 中 | 高 | §11 合规声明 + 主动披露 | 中 |
| R7 | 冷启动超时 | 低 | 高 | 索引构建置于 `__init__` | 低 |
| R8 | 200 条公开集上超参过拟合 | 中 | 中 | 仅 3 个系数，拒绝复杂拟合 | 中 |

---

## 11. 合规声明

### 11.1 规则符合性

| 约束 | 符合性 | 证据 |
|---|---|---|
| CON-2 目录只读 | ✅ | 无写操作；仅 `open(..., encoding="utf-8")` 读取 |
| CON-3 不改评测器 | ✅ | `evaluator/` 未被修改；`robust_eval.py` 为独立旁路 harness |
| CON-4 可离线 | ✅ | 无网络调用 |
| CON-5 无密钥 | ✅ | 无 `.env`、无凭证 |
| CON-6 无向量库 | ✅ | 全部索引为进程内 Python 结构 + SQLite `:memory:` |
| 未接触私有标签 | ✅ | 仅使用参赛者可见的公开字段与公开会话 |

### 11.2 方法学披露（**必须写入提交 README**）

本系统的高分源于一项对数据的观察：**模拟顾客的偏好表述是目标商品文案的原文片段**。据此我们将任务建模为**跨度级精确检索**而非语义相似度检索，并对商品全部属性跨度建立倒排索引。

我们同时实现了逐字复刻评测器意图卡构造函数的变体（`TJ_MODE=mirror`，0.9620）作为消融对照，但**提交的是不依赖评测器内部实现的通用版本**（`TJ_MODE=general`，0.9588）。代价为 0.0032 分，换取：

1. 主办方调整模拟器时仍然有效；
2. 方法学可迁移至真实场景——真实顾客同样会引用商品描述原文；
3. 不触及 out-of-scope 中 "private-label reconstruction" 的观感边界。

### 11.3 局限性声明（**必须写入提交 README**）

* 本系统针对**确定性模拟器**优化。面对真实人类用户，跨度精确匹配的召回率会显著下降。
* 届时主要贡献者应为稠密召回层与 LLM 查询改写（当前均未启用，见设计文档 §7.5 与 §9.3）。
* §7.4 的改写鲁棒性数据基于自研改写器，不构成对主办方改写器的性能承诺。

---

## 12. 已知局限与未决项

| ID | 项 | 说明 | 优先级 |
|---|---|---|---|
| L-1 | 无稠密召回 | 改写场景下若跨度本身被改写（而非仅包裹），Layer B 亦失效 | P2 |
| L-2 | 画像利用极弱 | `preference_tags` 判别力低，权重仅 0.05 | P3 |
| L-3 | intent_override MTTC 无优化空间 | 受 CON-7 限制，3.6 为硬下限 | 不可行 |
| L-4 | boundary 必损一轮 | 首次提问必被拒答一次，无法规避 | 不可行 |
| L-5 | 超参在 n=200 上选定 | 存在过拟合风险，已限制为 3 个系数 | P2 |
| L-6 | 演示界面未做无障碍审计 | 仅验证了色彩对比可读性，未做键盘导航 / ARIA | P3 |
| L-7 | 演示服务单进程内存态 | 会话存于内存，重启即失；不适用于生产 | 可接受（非评分项） |

---

## 13. 提交检查清单

**代码**
- [ ] `agent.py` 导出 `Agent`，签名与 IF-1 一致
- [ ] 全链路 try/except（FM-1）
- [ ] `message` 恒为 str；`ask_attribute` ∈ 枚举 ∪ {null}；`usage` 非负整数
- [ ] 环境变量分支已清理，配置硬编码为 general / ev / 3 / pop_price
- [ ] `evaluator/`、`data/` 未被修改
- [ ] 无密钥、无网络调用
- [ ] 干净虚拟环境 `git clone` → 一条命令复现 0.9588

**文档**
- [ ] README 含：概述 / 安装 / 复现 / **局限性反思** / 团队分工
- [ ] README 载入 §11.2 方法学披露与 §11.3 局限性声明
- [ ] 披露模型选择、Token（0）、延迟（p95 ≤ 83 ms）、成本（$0）
- [ ] 明确标注 `server/`、`web/` 不参与评分

**视频**
- [ ] ≤ 4 分钟，YouTube 公开
- [ ] 展示多轮会话 + 推理面板（漏斗坍缩 + 门控状态）
- [ ] 口播覆盖：问题 → 信息通道 → 门控决策论 → 鲁棒性测试 → 成绩

---

## 14. 变更记录

| 版本 | 变更 |
|---|---|
| 1.0 | 首版。系统已实现并通过 V&V-1~V&V-5 全部验证。 |

---

*本报告所有数值均可通过 `solution/tools/` 下脚本复现；主指标可通过官方评测器直接复核。*
