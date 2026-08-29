"""Evaluate collision-aware FARM variants, including explicit tail metrics."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SOLUTION_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SOLUTION_ROOT.parent
OFFICIAL_ROOT = REPOSITORY_ROOT / "techjam-conversational-search"
sys.path.insert(0, str(SOLUTION_ROOT))
sys.path.insert(0, str(OFFICIAL_ROOT))

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402
from experimental import tail_repair  # noqa: E402
from tools import robust_eval  # noqa: E402


def loop_score(session):
    if not session["hit"]:
        return 0.0
    rank = float(session["best_rank"])
    turn = float(session["first_hit_turn"])
    return 0.50 + 0.30 / rank + 0.20 * (11.0 - turn) / 10.0


def tail_summary(result):
    rows = [
        {**session, "loop_score": round(loop_score(session), 6)}
        for session in result["sessions"]
    ]
    rows.sort(key=lambda item: item["loop_score"])
    low = [item for item in rows if item["loop_score"] < 0.9]
    worst = rows[: max(1, round(0.05 * len(rows)))]
    return {
        "below_0_9": len(low),
        "low_sessions": low,
        "worst_5pct_mean": round(
            sum(item["loop_score"] for item in worst) / len(worst), 6
        ),
        "minimum": rows[0]["loop_score"],
    }


def compact(result):
    return {
        "score": result["recommended_technical_score"],
        "hit": result["hit_rate_at_10"],
        "mrr": result["mrr"],
        "mttc": result["mttc"],
        "efficiency": result["efficiency"],
        "scenario": result["scenario_metrics"],
        "tail": tail_summary(result),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=str(OFFICIAL_ROOT / "data/catalog.jsonl"))
    parser.add_argument("--dataset", default=str(OFFICIAL_ROOT / "data/public_set.jsonl"))
    parser.add_argument(
        "--rules",
        nargs="+",
        choices=("none", "prior_only"),
        default=["none", "prior_only"],
    )
    parser.add_argument("--margin", type=float, default=0.75)
    parser.add_argument("--progressive", action="store_true")
    parser.add_argument("--robust", action="store_true")
    args = parser.parse_args()

    samples = load_jsonl(args.dataset)
    catalog_ids, categories, products = catalog_index(args.catalog)
    tail_repair.TAIL_MARGIN = args.margin
    tail_repair.PROGRESSIVE_BATCHING = args.progressive
    agent = tail_repair.Agent(args.catalog)

    for rule in args.rules:
        tail_repair.COLLISION_RULE = rule
        result = evaluate(agent, samples, catalog_ids, categories, products)
        payload = {
            "rule": rule,
            "margin": args.margin,
            "progressive": args.progressive,
            **compact(result),
        }
        if args.robust:
            noisy = robust_eval.evaluate(
                agent, samples, catalog_ids, categories, products, noise=True
            )
            payload["paraphrased"] = {
                "score": noisy["score"],
                "hit": noisy["hit_rate_at_10"],
                "mrr": noisy["mrr"],
                "mttc": noisy["mttc"],
                "efficiency": noisy["efficiency"],
            }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
