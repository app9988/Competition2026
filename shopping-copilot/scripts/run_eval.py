"""Full-set instrumented evaluation CLI.

Usage (from the shopping-copilot directory):
    python scripts/run_eval.py                          # all 200 public sessions
    python scripts/run_eval.py --limit 20               # quick slice
    python scripts/run_eval.py --only browsing          # one scenario
    python scripts/run_eval.py --paraphrase 2 --tag stress
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT.parent / "techjam-conversational-search"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(KIT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Instrumented public-set evaluation")
    parser.add_argument("--config", default=str(ROOT / "configs" / "default.json"))
    parser.add_argument("--catalog", default=str(KIT / "data" / "catalog.jsonl"))
    parser.add_argument("--dataset", default=str(KIT / "data" / "public_set.jsonl"))
    parser.add_argument("--runs-dir", default=str(ROOT / "runs"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only", choices=["buying", "browsing", "intent_override", "boundary"])
    parser.add_argument("--sample-id", action="append", default=[],
                        help="evaluate only this sample id; may be repeated")
    parser.add_argument("--tag", default="")
    parser.add_argument("--paraphrase", type=int, default=0, choices=[0, 1, 2],
                        help="B-mode stress level: 1 rewrites templates, 2 also perturbs constraints")
    args = parser.parse_args()

    from copilot.eval.instrumented_runner import run

    summary = run(args.config, args.catalog, args.dataset, args.runs_dir,
                  limit=args.limit, only=args.only, tag=args.tag,
                  paraphrase_level=args.paraphrase,
                  sample_ids=set(args.sample_id) or None)
    print(json.dumps(summary, indent=2))
    print(f"\n[eval] TechnicalScore = {summary['technical_score']}")
    print(f"[eval] reports written to {summary['run_dir']}")


if __name__ == "__main__":
    main()
