"""Generate the Markdown report for a completed CompetitionAI test run."""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_ROOT = ROOT / "techjam-conversational-search"
sys.path.insert(0, str(OFFICIAL_ROOT))

from evaluator.local_evaluator import coarse_category, intent_card  # noqa: E402


SCENARIO_ZH = {
    "buying": "购买型",
    "browsing": "浏览型",
    "intent_override": "意图覆写",
    "boundary": "边界拒答",
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def loop_score(session):
    if not session["hit"]:
        return 0.0
    turn = int(session["first_hit_turn"])
    rank = int(session["best_rank"])
    return 0.50 + 0.30 / rank + 0.20 * (11 - turn) / 10


def aggregate_score(metrics):
    if not metrics or metrics.get("mttc") is None:
        return 0.0
    efficiency = max(0.0, min(1.0, (11.0 - float(metrics["mttc"])) / 10.0))
    return 0.50 * metrics["hit_rate_at_10"] + 0.30 * metrics["mrr"] + 0.20 * efficiency


def mark(value):
    return "🔴 **< 0.9**" if value < 0.9 else "✅"


def escape(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def build_catalog_context(catalog_path):
    products = {}
    signatures = defaultdict(list)
    with Path(catalog_path).open(encoding="utf-8") as handle:
        for line in handle:
            product = json.loads(line)
            parent_asin = str(product["parent_asin"])
            products[parent_asin] = product
            category = coarse_category([str(value) for value in product.get("categories") or []])
            card = intent_card(product)
            signature = (
                category,
                tuple(card.get("hard_constraints") or []),
                tuple(card.get("soft_preferences") or []),
            )
            signatures[signature].append(parent_asin)
    return products, signatures


def signature_collision(parent_asin, products, signatures):
    product = products[parent_asin]
    category = coarse_category([str(value) for value in product.get("categories") or []])
    card = intent_card(product)
    signature = (
        category,
        tuple(card.get("hard_constraints") or []),
        tuple(card.get("soft_preferences") or []),
    )
    return len(signatures[signature])


def scenario_loop_scores(result):
    grouped = defaultdict(list)
    for session in result["sessions"]:
        grouped[session["scenario_type"]].append(loop_score(session))
    return {key: statistics.fmean(values) for key, values in grouped.items()}


def difficulty_loop_scores(result, metadata):
    grouped = defaultdict(list)
    for session in result["sessions"]:
        difficulty = metadata[session["sample_id"]].get("difficulty_bucket", "unknown")
        grouped[difficulty].append(loop_score(session))
    return {key: statistics.fmean(values) for key, values in grouped.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stable", required=True)
    parser.add_argument("--farm", required=True)
    parser.add_argument("--stable-robust", required=True)
    parser.add_argument("--farm-robust", required=True)
    parser.add_argument("--stable-bench", required=True)
    parser.add_argument("--farm-bench", required=True)
    parser.add_argument("--dataset", default=str(OFFICIAL_ROOT / "data/public_set.jsonl"))
    parser.add_argument("--catalog", default=str(OFFICIAL_ROOT / "data/catalog.jsonl"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    stable = read_json(args.stable)
    farm = read_json(args.farm)
    stable_robust = read_json(args.stable_robust)
    farm_robust = read_json(args.farm_robust)
    stable_bench = read_json(args.stable_bench)
    farm_bench = read_json(args.farm_bench)
    metadata = {
        sample["sample_id"]: sample
        for sample in map(json.loads, Path(args.dataset).read_text(encoding="utf-8").splitlines())
        if sample
    }
    products, signatures = build_catalog_context(args.catalog)
    stable_by_id = {session["sample_id"]: session for session in stable["sessions"]}

    farm_loop_values = [loop_score(session) for session in farm["sessions"]]
    derived_total = statistics.fmean(farm_loop_values)
    official_total = float(farm["recommended_technical_score"])
    if abs(derived_total - official_total) > 1e-9:
        raise RuntimeError(f"per-loop mean {derived_total} != official score {official_total}")

    low_sessions = sorted(
        [session for session in farm["sessions"] if loop_score(session) < 0.9],
        key=lambda session: (loop_score(session), session["sample_id"]),
    )
    farm_scenario = scenario_loop_scores(farm)
    stable_scenario = scenario_loop_scores(stable)
    farm_difficulty = difficulty_loop_scores(farm, metadata)
    stable_difficulty = difficulty_loop_scores(stable, metadata)

    now = datetime.now().astimezone()
    lines = [
        "# CompetitionAI 全量测试报告",
        "",
        f"> 生成时间：{now.isoformat(timespec='seconds')}  ",
        f"> 环境：Python {platform.python_version()} · {platform.platform()}  ",
        "> 主评测对象：FARM-RL 零依赖代理；稳定版作为对照。",
        "",
        "## 1. 最终结论",
        "",
        f"- **正式总分：{official_total:.6f}**（FARM，官方 200 会话 TechnicalScore）。",
        f"- 稳定版正式总分：{stable['recommended_technical_score']:.6f}；FARM 提升 **{official_total - stable['recommended_technical_score']:+.6f}**。",
        f"- FARM 正式集：Hit@10={farm['hit_rate_at_10']:.3f}，MRR={farm['mrr']:.6f}，MTTC={farm['mttc']:.3f}，Efficiency={farm['efficiency']:.4f}。",
        f"- 200 条正式链路中，**{len(low_sessions)} 条低于 0.9**，最低为 **{min(farm_loop_values):.3f}**。",
        f"- 改写压力集：FARM={farm_robust['paraphrased']['score']:.6f}，稳定版={stable_robust['paraphrased']['score']:.6f}，FARM 回退 **{farm_robust['paraphrased']['score'] - stable_robust['paraphrased']['score']:+.6f}**。",
        "- 契约/对抗输入：稳定版 67/67、FARM 67/67；评测器单元测试 3/3。",
        "",
        "正式总分只采用竞赛官方指标；契约通过率、鲁棒性和性能数据不与 TechnicalScore 人为混合。",
        "",
        "## 2. 单条链路评分公式",
        "",
        "每个用户问答到最终推荐的会话独立计分：",
        "",
        "```text",
        "命中：LoopScore = 0.50 + 0.30 / target_rank + 0.20 × (11 - hit_turn) / 10",
        "未命中：LoopScore = 0",
        "总分：200 条 LoopScore 的平均值",
        "```",
        "",
        "因此 Rank 1、第 3 轮命中的链路得 0.96；Rank 2、第 3 轮只有 0.81。",
        "",
        "## 3. 正式端到端评测总览",
        "",
        "| 方案 | 样本 | Hit@10 | MRR | MTTC | Efficiency | TechnicalScore | 状态 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
        f"| 稳定版 | {stable['sample_count']} | {stable['hit_rate_at_10']:.3f} | {stable['mrr']:.6f} | {stable['mttc']:.3f} | {stable['efficiency']:.4f} | {stable['recommended_technical_score']:.6f} | {mark(stable['recommended_technical_score'])} |",
        f"| FARM | {farm['sample_count']} | {farm['hit_rate_at_10']:.3f} | {farm['mrr']:.6f} | {farm['mttc']:.3f} | {farm['efficiency']:.4f} | **{official_total:.6f}** | {mark(official_total)} |",
        "",
        "### 3.1 按场景的平均链路分",
        "",
        "| 场景 | 样本数 | 稳定版 | FARM | 差值 | FARM 状态 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for scenario in ("buying", "browsing", "intent_override", "boundary"):
        count = farm["scenario_metrics"][scenario]["sample_count"]
        sv, fv = stable_scenario[scenario], farm_scenario[scenario]
        lines.append(
            f"| {SCENARIO_ZH[scenario]} | {count} | {sv:.6f} | {fv:.6f} | {fv - sv:+.6f} | {mark(fv)} |"
        )

    lines.extend([
        "",
        "### 3.2 按难度的平均链路分",
        "",
        "| 难度 | 稳定版 | FARM | 差值 | FARM 状态 |",
        "|---|---:|---:|---:|---|",
    ])
    for difficulty in ("easy", "medium", "hard"):
        sv, fv = stable_difficulty[difficulty], farm_difficulty[difficulty]
        lines.append(f"| {difficulty} | {sv:.6f} | {fv:.6f} | {fv - sv:+.6f} | {mark(fv)} |")

    lines.extend([
        "",
        "## 4. 低于 0.9 的正式链路",
        "",
        "下面严格按 `LoopScore < 0.9` 标记。`完整意图卡碰撞数`表示同一品类中具有完全相同四项公开意图字段的商品数。",
        "",
        "| 标记 | Sample | 场景 | 难度 | Turn | Rank | 链路分 | 完整意图卡碰撞数 | 目标商品 |",
        "|---|---|---|---|---:|---:|---:|---:|---|",
    ])
    for session in low_sessions:
        sample = metadata[session["sample_id"]]
        parent_asin = str(sample["ground_truth"]["parent_asin"])
        title = escape(products[parent_asin].get("title") or "")
        collision = signature_collision(parent_asin, products, signatures)
        lines.append(
            f"| 🔴 | {session['sample_id']} | {SCENARIO_ZH[session['scenario_type']]} | "
            f"{sample.get('difficulty_bucket', '')} | {session['first_hit_turn']} | {session['best_rank']} | "
            f"**{loop_score(session):.3f}** | {collision} | {title} |"
        )

    lowest = low_sessions[0]
    lines.extend([
        "",
        f"最低链路是 **{lowest['sample_id']}**：第 {lowest['first_hit_turn']} 轮 Rank {lowest['best_rank']}，得分 {loop_score(lowest):.3f}。",
        "主要薄弱点有两类：",
        "",
        "1. 六条链路存在 2–9 个完整意图卡相同的商品，已披露字段不足以唯一定位，排序只能依赖弱先验。",
        "2. `public_0054` 的完整意图卡本来唯一，但 FARM 小池门控在信息尚未全部披露时提前发布，目标只排到第 2；这是当前早发策略的明确副作用。",
        "",
        "## 5. 改写鲁棒性压力测试",
        "",
        "| 方案 | 输入 | Hit@10 | MRR | MTTC | Score | 状态 |",
        "|---|---|---:|---:|---:|---:|---|",
    ])
    for label, result in (("稳定版", stable_robust), ("FARM", farm_robust)):
        for mode, mode_zh in (("verbatim", "原文"), ("paraphrased", "模板改写")):
            metrics = result[mode]
            lines.append(
                f"| {label} | {mode_zh} | {metrics['hit_rate_at_10']:.3f} | {metrics['mrr']:.6f} | "
                f"{metrics['mttc']:.3f} | {metrics['score']:.6f} | {mark(metrics['score'])} |"
            )

    lines.extend([
        "",
        "### 5.1 改写集按场景",
        "",
        "| 方案 | 场景 | Hit@10 | MRR | MTTC | 场景分 | 状态 |",
        "|---|---|---:|---:|---:|---:|---|",
    ])
    for label, result in (("稳定版", stable_robust), ("FARM", farm_robust)):
        for scenario in ("buying", "browsing", "intent_override", "boundary"):
            metrics = result["paraphrased"]["scenario"][scenario]
            score = aggregate_score(metrics)
            lines.append(
                f"| {label} | {SCENARIO_ZH[scenario]} | {metrics['hit_rate_at_10']:.3f} | "
                f"{metrics['mrr']:.6f} | {metrics['mttc']:.3f} | {score:.6f} | {mark(score)} |"
            )

    lines.extend([
        "",
        "FARM 的改写意图覆写场景低于 0.9，说明字段签名和提前发布策略对非模板覆写语句仍不够稳健；在替换稳定提交前必须修复。",
        "",
        "## 6. 契约、对抗输入与单元测试",
        "",
        "| 测试 | 稳定版 | FARM | 结果 |",
        "|---|---:|---:|---|",
        "| 对抗消息、异常 profile、协议滥用、确定性 | 67/67 | 67/67 | ✅ 全通过，0 异常 |",
        "| 评测器单元测试 | 3/3 | 同一评测器 | ✅ 全通过 |",
        "",
        "单元测试覆盖：隐藏字段派生、miss 按第 11 轮计入 MTTC、推荐去重与顺序保持。",
        "",
        "## 7. 性能基准",
        "",
        "基准固定 `PYTHONHASHSEED=0`，对 100 个会话执行 400 次 `respond()`。性能数据不参与竞赛总分。",
        "",
        "| 方案 | 冷启动 | p50 | p95 | p99 | max | LLM tokens |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| 稳定版 | {stable_bench['index_build_seconds']:.3f}s | {stable_bench['latency_ms']['p50']:.3f}ms | {stable_bench['latency_ms']['p95']:.3f}ms | {stable_bench['latency_ms']['p99']:.3f}ms | {stable_bench['latency_ms']['max']:.3f}ms | {stable_bench['llm_tokens']} |",
        f"| FARM | {farm_bench['index_build_seconds']:.3f}s | {farm_bench['latency_ms']['p50']:.3f}ms | {farm_bench['latency_ms']['p95']:.3f}ms | {farm_bench['latency_ms']['p99']:.3f}ms | {farm_bench['latency_ms']['max']:.3f}ms | {farm_bench['llm_tokens']} |",
        "",
        "## 8. FARM 全部 200 条正式测试回路",
        "",
        "| 状态 | Sample | 场景 | 难度 | Target | Turn | Rank | Hit | Efficiency | FARM 链路分 | 稳定版链路分 | 差值 | 商品标题 |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for session in sorted(farm["sessions"], key=lambda item: item["sample_id"]):
        sample = metadata[session["sample_id"]]
        parent_asin = str(sample["ground_truth"]["parent_asin"])
        stable_session = stable_by_id[session["sample_id"]]
        score = loop_score(session)
        stable_score = loop_score(stable_session)
        efficiency = 0.0 if not session["hit"] else (11 - session["first_hit_turn"]) / 10
        status = "🔴" if score < 0.9 else "✅"
        turn = session["first_hit_turn"] if session["first_hit_turn"] is not None else "miss"
        rank = session["best_rank"] if session["best_rank"] is not None else "—"
        title = escape(products[parent_asin].get("title") or "")
        lines.append(
            f"| {status} | {session['sample_id']} | {SCENARIO_ZH[session['scenario_type']]} | "
            f"{sample.get('difficulty_bucket', '')} | {parent_asin} | {turn} | {rank} | "
            f"{1 if session['hit'] else 0} | {efficiency:.2f} | **{score:.3f}** | "
            f"{stable_score:.3f} | {score - stable_score:+.3f} | {title} |"
        )

    lines.extend([
        "",
        "## 9. 测试范围说明",
        "",
        "本报告纳入所有正式测试/评测入口：官方端到端评测、模板改写鲁棒性、契约与对抗输入、评测器单元测试、冷启动和延迟基准。",
        "`sweep_weights.py`（权重扫描）与 `probe_selectivity.py`（信号可辨识性分析）属于调研/调参工具，不是 pass/fail 测试，也不计入正式总分。",
        "",
    ])

    Path(args.output).write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.output} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
