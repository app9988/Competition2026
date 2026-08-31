"""Run the submitted Agent in the official harness — one command, no arguments.

    python run_official.py

Requires the official kit cloned at ./techjam-conversational-search with
data/catalog.jsonl downloaded (see README section 2). Standard library only.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "techjam-conversational-search"))

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402

from agent import Agent  # noqa: E402

KIT = ROOT / "techjam-conversational-search"

samples = load_jsonl(str(KIT / "data" / "public_set.jsonl"))
catalog_ids, categories, products = catalog_index(str(KIT / "data" / "catalog.jsonl"))
agent = Agent(str(KIT / "data" / "catalog.jsonl"))
result = evaluate(agent, samples, catalog_ids, categories, products)

print(f"TechnicalScore = {result['recommended_technical_score']}")
print(f"Hit@10 = {result['hit_rate_at_10']}  MRR = {result['mrr']}  MTTC = {result['mttc']}")
