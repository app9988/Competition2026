"""Run the official local evaluation with the experimental FARM-RL proxy."""
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
from experimental.farm_margin import Agent  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=str(OFFICIAL_ROOT / "data/catalog.jsonl"))
    parser.add_argument("--dataset", default=str(OFFICIAL_ROOT / "data/public_set.jsonl"))
    parser.add_argument("--output", default=str(SOLUTION_ROOT / "results_farm_margin.json"))
    args = parser.parse_args()

    samples = load_jsonl(args.dataset)
    catalog_ids, categories, products = catalog_index(args.catalog)
    result = evaluate(Agent(args.catalog), samples, catalog_ids, categories, products)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "sessions"}, indent=2))


if __name__ == "__main__":
    main()

