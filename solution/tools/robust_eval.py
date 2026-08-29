"""Robustness harness: re-runs the official protocol with the customer's utterances
paraphrased, to measure how much of the score depends on exact template matching.

The official evaluator is untouched; this is an ablation harness only.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys

sys.path.insert(0, ".")
import evaluator.local_evaluator as LE
from starter.agent import Agent

PARA_OPEN_BUY = [
    "Hi there - I'm after {c}. The one thing I really care about: {v}.",
    "I want to buy {c}. Must have: {v}.",
    "Shopping for {c} today. Non-negotiable for me is {v}.",
    "Could you help me find {c}? It has to be {v}.",
]
PARA_OPEN_BROWSE = [
    "Hey, just browsing {c} for now, nothing specific yet.",
    "I'm window shopping in {c}. Not sure what I want.",
    "Show me what you have in {c} - I'm undecided.",
    "Thinking about {c}, but I haven't made up my mind.",
]
PARA_OPEN_OTHER = [
    "I'm after {c}. {v}",
    "Help me shop for {c}. {v}",
    "Looking around {c}. {v}",
]
PARA_REVEAL = [
    "Sure - {v}.",
    "Honestly the things that matter are {v}.",
    "OK: {v}. That's what counts.",
    "Right, {v} - that's my priority.",
]
PARA_NOPREF = [
    "No strong opinion on {a}, sorry.",
    "{a} isn't something I care about.",
    "I'm easy on {a}.",
]
PARA_BOUNDARY = [
    "No idea about {a} - you pick.",
    "I'll leave {a} up to you.",
    "Honestly, {a}? Your call.",
]
PARA_OVERRIDE = [
    "Wait - scratch that. What I actually want is {v}.",
    "Change of plan. The real requirement is {v}.",
    "Forget what I said. I need {v}.",
]
PARA_NOASK = [
    "None of those work. Ask me something specific.",
    "Not what I meant - narrow it down with a question.",
]

R_BUY = re.compile(r"^I'm looking for (.+?)\. A key requirement is: (.+)\.$", re.S)
R_BROWSE = re.compile(r"^I'm looking for (.+?), but I'm still exploring\.$", re.S)
R_OPEN = re.compile(r"^I'm looking for (.+?)\. (.+)$", re.S)
R_REVEAL = re.compile(r"^For that, what matters is: (.+)\.$", re.S)
R_NOPREF = re.compile(r"^I don't have an additional preference for (.+)\.$", re.S)
R_BOUND = re.compile(r"^I don't have a preference for (.+); please use your judgment\.$", re.S)
R_OVER = re.compile(r"^Actually, ignore my earlier preference\. What I need is: (.+)\.$", re.S)
R_NOASK = re.compile(r"^Those options are not quite right yet\.")


def paraphrase(msg: str, rng: random.Random) -> str:
    m = R_BUY.match(msg)
    if m:
        return rng.choice(PARA_OPEN_BUY).format(c=m.group(1), v=m.group(2))
    m = R_BROWSE.match(msg)
    if m:
        return rng.choice(PARA_OPEN_BROWSE).format(c=m.group(1))
    m = R_OVER.match(msg)
    if m:
        return rng.choice(PARA_OVERRIDE).format(v=m.group(1))
    m = R_REVEAL.match(msg)
    if m:
        return rng.choice(PARA_REVEAL).format(v=m.group(1).replace("; ", ", and "))
    m = R_BOUND.match(msg)
    if m:
        return rng.choice(PARA_BOUNDARY).format(a=m.group(1))
    m = R_NOPREF.match(msg)
    if m:
        return rng.choice(PARA_NOPREF).format(a=m.group(1))
    if R_NOASK.match(msg):
        return rng.choice(PARA_NOASK)
    m = R_OPEN.match(msg)
    if m:
        return rng.choice(PARA_OPEN_OTHER).format(c=m.group(1), v=m.group(2))
    return msg


def evaluate(agent, samples, catalog_ids, categories, products, noise: bool):
    """Byte-for-byte the official loop, with an optional paraphrase layer on user_message."""
    import statistics
    import uuid
    from collections import defaultdict
    sessions = []
    for sample in samples:
        rng = random.Random("para\0" + str(sample["sample_id"]))
        session_id = f"public_{uuid.uuid4().hex}"
        agent.reset(session_id, sample["user_profile"])
        target = str(sample["ground_truth"]["parent_asin"])
        card, behavior = LE.materialize_hidden_fields(sample, products)
        eff = {**sample, "intent_card": card, "behavior": behavior}
        disclosed, boundary_used = set(), False
        override_applied = sample["scenario_type"] != "intent_override"
        user_message = LE.initial_message(eff, LE.coarse_category(categories.get(target, [])), disclosed)
        hit_turn = best_rank = None
        for turn in range(1, LE.MAX_TURNS + 1):
            shown = paraphrase(user_message, rng) if noise else user_message
            try:
                response = agent.respond(session_id, shown, turn, LE.TOP_K)
            except Exception:
                response = {"message": "", "ask_attribute": None, "recommendations": []}
            ranked = LE.normalize_recommendations(response.get("recommendations"), catalog_ids)
            if override_applied and target in ranked:
                best_rank = ranked.index(target) + 1
                hit_turn = turn
                break
            if turn == LE.MAX_TURNS:
                break
            override = eff.get("behavior", {}).get("override") or {}
            if not override_applied and turn + 1 == int(override.get("turn", 3)):
                override_applied = True
                nv = str(override.get("new_value", ""))
                if nv:
                    disclosed.add(nv)
                user_message = str(override.get("message", "Actually, please ignore my earlier preference."))
            else:
                user_message, boundary_used = LE.customer_reply(
                    eff, response.get("ask_attribute"), disclosed, boundary_used)
        sessions.append({"sample_id": sample["sample_id"], "scenario_type": sample["scenario_type"],
                         "hit": hit_turn is not None, "first_hit_turn": hit_turn, "best_rank": best_rank,
                         "reciprocal_rank": 0.0 if best_rank is None else 1.0 / best_rank})
    overall = LE.metric_summary(sessions)
    eff_m = max(0.0, min(1.0, (11.0 - float(overall["mttc"])) / 10.0))
    grouped = defaultdict(list)
    for s in sessions:
        grouped[s["scenario_type"]].append(s)
    return {**overall, "efficiency": round(eff_m, 6),
            "score": round(0.5 * overall["hit_rate_at_10"] + 0.3 * overall["mrr"] + 0.2 * eff_m, 6),
            "scenario": {k: LE.metric_summary(v) for k, v in sorted(grouped.items())}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--dataset", required=True)
    args = ap.parse_args()
    samples = LE.load_jsonl(args.dataset)
    ids, cats, prods = LE.catalog_index(args.catalog)
    agent = Agent(args.catalog)
    for noise in (False, True):
        r = evaluate(agent, samples, ids, cats, prods, noise)
        tag = "PARAPHRASED" if noise else "VERBATIM   "
        print(f"{tag}  score={r['score']:.4f} hit={r['hit_rate_at_10']:.3f} "
              f"mrr={r['mrr']:.4f} mttc={r['mttc']:.3f} eff={r['efficiency']:.4f}")
        for k, v in r["scenario"].items():
            print(f"    {k:16s} hit={v['hit_rate_at_10']:.3f} mrr={v['mrr']:.3f} mttc={v['mttc']:.3f}")
