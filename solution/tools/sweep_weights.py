"""L3 fusion-weight sensitivity analysis.

Builds the index ONCE, then re-runs the full official evaluation loop for each
weight setting. Answers "how much does this coefficient actually matter?"
rather than asserting a tuned value without evidence.

Usage (from the official repo root, with solution/ on the path):
    python sweep_weights.py --catalog data/catalog.jsonl --dataset data/public_set.jsonl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # solution/
sys.path.insert(0, str(HERE.parent.parent / "techjam-conversational-search"))

import evaluator.local_evaluator as LE        # noqa: E402
from src import agent as A                    # noqa: E402


def run(agent, samples, ids, cats, prods):
    r = LE.evaluate(agent, samples, ids, cats, prods)
    return (r["recommended_technical_score"], r["hit_rate_at_10"], r["mrr"],
            r["mttc"], r["efficiency"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--dataset", required=True)
    args = ap.parse_args()

    samples = LE.load_jsonl(args.dataset)
    ids, cats, prods = LE.catalog_index(args.catalog)

    # W_PRICE feeds the prior, which is baked in at index build -> needs its own agent.
    print("building index ...", flush=True)
    agent = A.Agent(args.catalog)
    print(f"ready ({agent.build_seconds}s)\n", flush=True)

    base = dict(W_SPAN=A.W_SPAN, W_SUB=A.W_SUB, W_PARTIAL=A.W_PARTIAL,
                W_BM25=A.W_BM25, W_PRIOR=A.W_PRIOR, W_PROFILE=A.W_PROFILE)

    grids = {
        "W_PRIOR":   [0.0, 0.10, 0.20, 0.30, 0.40, 0.60, 1.00, 2.00],
        "W_BM25":    [0.0, 0.25, 0.50, 1.00, 2.00, 5.00],
        "W_PROFILE": [0.0, 0.05, 0.25, 1.00],
        "W_SUB":     [0.0, 2.5, 5.0, 8.0, 11.9],
        "W_PARTIAL": [0.0, 1.0, 2.5, 5.0, 11.9],
        "W_SPAN":    [3.0, 6.0, 12.0, 24.0, 100.0],
    }

    print(f"{'weight':<11}{'value':>8} | {'score':>8} {'hit':>6} {'mrr':>7} {'mttc':>6} {'eff':>6}")
    print("-" * 62)
    for name, values in grids.items():
        for v in values:
            for k, dv in base.items():
                setattr(A, k, dv)
            setattr(A, name, v)
            sc, hit, mrr, mttc, eff = run(agent, samples, ids, cats, prods)
            mark = "  <- default" if abs(v - base[name]) < 1e-9 else ""
            print(f"{name:<11}{v:>8.2f} | {sc:>8.5f} {hit:>6.3f} {mrr:>7.4f} "
                  f"{mttc:>6.3f} {eff:>6.3f}{mark}", flush=True)
        print()
    for k, dv in base.items():
        setattr(A, k, dv)


if __name__ == "__main__":
    main()
