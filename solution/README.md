# Shopping Copilot · 参考实现 + 演示应用

配套技术文档：[`../TECHJAM_SOLUTION_DESIGN.md`](../TECHJAM_SOLUTION_DESIGN.md)

## 实测成绩（官方 `evaluator/local_evaluator.py`，公开集 200 会话）

```
score = 0.9588   hit@10 = 1.000   MRR = 0.9708   MTTC = 2.620   Efficiency = 0.838
（官方 BM25 baseline: 0.1067 —— 提升 9.0 倍）
```

原始输出见 [`results_public_set.json`](results_public_set.json)。

| 场景 | n | Hit@10 | MRR | MTTC |
|---|---|---|---|---|
| buying | 80 | 1.000 | 0.983 | 2.288 |
| browsing | 80 | 1.000 | 0.956 | 2.525 |
| intent_override | 30 | 1.000 | 0.967 | 3.600 (该场景理论下限) |
| boundary | 10 | 1.000 | 1.000 | 3.100 |

## 1 · 复现分数（这是被评分的部分）

把 `src/agent.py` 复制到官方仓库的 `starter/agent.py`，在仓库根目录执行：

```bash
python -m evaluator.local_evaluator --catalog data/catalog.jsonl --dataset data/public_set.jsonl
```

依赖：Python 3.10+，**无第三方库**，**无网络调用**。

## 2 · 启动演示界面（不参与评分）

**推荐**——一条命令，自带环境预检并自动开浏览器：

```bash
python run_demo.py
```

（在 `solution/` 目录下执行。换端口用 `--port 8001`，不自动开浏览器用 `--no-open`。）

等价的原始命令：

```bash
python -m uvicorn server.app:app --port 8000
```

**首次启动需 20–40 s 构建 5 万条商品的内存索引**，等日志出现 `Application startup complete.`
后再访问 <http://127.0.0.1:8000>。过早打开只会看到加载动画，属正常现象。

依赖：`pip install fastapi uvicorn`（**仅演示需要**；`agent.py` 本身零第三方依赖）。
数据路径默认为 `../techjam-conversational-search/data/`，可用 `TJ_CATALOG` / `TJ_DATASET` 覆盖。

常见问题：

| 现象 | 原因与处理 |
|---|---|
| 浏览器打不开 / 连接被拒绝 | 服务未启动，或索引还没构建完（等 `Application startup complete.`） |
| `Port 8000 is already in use` | 已有实例在跑，直接访问即可；或 `python run_demo.py --port 8001` |
| `ModuleNotFoundError: server` | 没在 `solution/` 目录下执行——`cd solution` 后重试 |
| `Catalog not found` | `catalog.jsonl` 未就位，见竞赛仓库 README 的下载步骤 |

### 界面功能

- **标注会话回放** —— 从 200 条真实标注会话中选一条，按官方协议逐轮播放，观察 Agent 如何锁定隐藏目标；回放结束后揭示 Agent 不可见的隐藏意图卡作对照。
- **自由对话** —— 任意输入，实时观察状态机与检索漏斗。
- **右侧推理面板** —— 检索漏斗（`50,000 → 品类桶 → 约束过滤`）、发布门控状态与原因、NLU 层、路由、延迟。
- **改写压力测试** —— 左栏开关实时改写顾客话术回放，现场证明 NLU 鲁棒性。
- **界面语言** —— 右上角 🌐 按钮一键切换中文/英文（持久化，默认跟随浏览器语言；对话内容为数据不翻译）。
- **主题** —— 右上角按钮循环切换 `跟随系统 / 明亮 / 暗色`，选择存于 `localStorage`；未选择时跟随操作系统的 `prefers-color-scheme`。

React / ReactDOM / Babel 已本地 vendor 到 `web/vendor/`，**整个演示完全离线可跑**。

## 3 · 目录

| 路径 | 参与评分 | 说明 |
|---|---|---|
| `src/agent.py` | ✅ **是** | 完整 Agent：L0 索引 / L1 三层 NLU / L2 状态机 / L3 检索排序 / L4 提问 / L5 发布门控 |
| `results_public_set.json` | — | 官方评测器实跑输出 |
| `server/app.py` | ❌ 否 | FastAPI 演示服务 |
| `server/simulator.py` | ❌ 否 | 顾客模拟器复刻，驱动回放 |
| `web/index.html` | ❌ 否 | 单文件 React 界面，无构建步骤 |
| `web/app.css` | ❌ 否 | 主题令牌与全部样式（明/暗双主题） |
| `run_demo.py` | ❌ 否 | 演示启动器：环境预检 + 自动开浏览器 |
| `tools/probe_selectivity.py` | ❌ 否 | 复现文档 §2.2 / §2.3 的可辨识性数据 |
| `tools/robust_eval.py` | ❌ 否 | 话术改写压力测试 |
| `tools/bench.py` | ❌ 否 | 冷启动 / 内存 / 延迟基准 |

> `server/` 与 `web/` 仅用于 Demo 视频，不影响 `agent.py` 的行为。埋点开关 `enable_trace` 默认关闭，打分路径零开销（重构后已回归验证：仍为 `0.9588`）。

## 4 · 工程指标

出厂配置 `TJ_MODE=general`（下表括号内为 `mirror` 消融配置的对照值）：

| 指标 | 实测 |
|---|---|
| 索引冷启动 | 18–33 s（mirror 17–24 s） |
| 单轮延迟 p95 | 76–83 ms（p99 ≤ 93，max ≤ 115） |
| 单轮延迟 p50 | 37–73 ms —— 随宿主机负载波动 |
| Python 堆内存 | 230 MB / peak 239 MB（mirror 137 MB） |
| LLM tokens | 0 prompt / 0 completion |
| 估算模型成本 | $0 |
| 外部网络 | 无 |

> 构建耗时与 p50 延迟在重复测量中波动明显（源于宿主机负载，非系统不稳定），故给出实测区间而非单点值；p95/p99 稳定。复现：`python tools/bench.py`。

## 5 · 消融开关（仅实验用；提交前请硬编码默认值并删除分支）

| 环境变量 | 默认 | 可选值 |
|---|---|---|
| `TJ_MODE` | `general` | `general`（不依赖评测器内部实现）/ `mirror`（逐字复刻，0.9620） |
| `TJ_GATE` | `ev` | `ev` / `greedy` / `turn3` / `singleton` |
| `TJ_FLOOR` | `3` | 强制发布轮次 |
| `TJ_PRIOR` | `pop_price` | `pop_price` / `pop` / `logrn` |

## 6 · 设计要点速览

1. **粗品类倒排桶** —— 首轮一次精确字符串匹配把 50,000 压到中位数 184，召回率 100%。
2. **属性跨度集合匹配** —— 模拟顾客的偏好表述是商品文案原文；用集合包含判定把候选池压到 1。
3. **三层降级 NLU** —— 纯模板正则在话术改写下得分归零（实测 `0.0000`）；v2 跨度恢复（宽松品类匹配 + 闭集材质/颜色 + 错桶逃逸）恢复到 `0.9236`（hit 0.990）。
4. **发布门控** —— 早一轮只值 0.02 分，而 Rank2→Rank1 值 0.15 分，所以没把握拿 Rank-1 就只提问不出结果。单项 +0.055。

完整算法、推导与全部实测数据见 [技术文档](../TECHJAM_SOLUTION_DESIGN.md)。
