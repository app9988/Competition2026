"""Instrumented full-set evaluation.

Replays the exact official session protocol by importing the participant kit's
own simulator helpers (message templates, customer policy, scoring), while
additionally collecting per-turn, per-stage traces from the agent. Official
scores must always be confirmed with `python -m evaluator.local_evaluator`;
this runner reproduces the same numbers and adds the L1..L6 link metrics.
"""
from __future__ import annotations

import csv
import json
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from copilot.agent.competition_agent import CompetitionAgent
from copilot.algo.dialog.belief import semantic_match_count
from copilot.core.textnorm import norm
from copilot.eval.link_metrics import aggregate_links

ROUTE_EXPECT = {
    "buying": "initial_buying",
    "browsing": "initial_browsing",
    "boundary": "initial_browsing",
    "intent_override": "initial_override",
}


def run(config_path: str | None, catalog: str, dataset: str, runs_dir: str,
        limit: int | None = None, only: str | None = None, tag: str = "",
        paraphrase_level: int = 0, sample_ids: set[str] | None = None,
        progress_cb=None) -> dict:
    import random

    from evaluator import local_evaluator as ev  # participant kit on sys.path

    from copilot.eval.paraphraser import paraphrase

    samples = ev.load_jsonl(dataset)
    if sample_ids:
        samples = [s for s in samples if s.get("sample_id") in sample_ids]
    if only:
        samples = [s for s in samples if s["scenario_type"] == only]
    if limit:
        samples = samples[:limit]

    print(f"[eval] {len(samples)} sessions | config={config_path or 'default'}")
    t_load = time.perf_counter()
    catalog_ids, categories, products = ev.catalog_index(catalog)
    agent = CompetitionAgent(catalog, config_path)
    print(f"[eval] catalog + agent ready in {time.perf_counter() - t_load:.1f}s")

    turn_rows: list[dict] = []
    session_rows: list[dict] = []
    t_run = time.perf_counter()

    for idx, sample in enumerate(samples, 1):
        session_id = f"inst_{uuid.uuid4().hex}"
        agent.reset(session_id, sample["user_profile"])
        target = str(sample["ground_truth"]["parent_asin"])
        card, behavior = ev.materialize_hidden_fields(sample, products)
        eff = {**sample, "intent_card": card, "behavior": behavior}
        disclosed: set = set()
        boundary_used = False
        override_applied = sample["scenario_type"] != "intent_override"
        override_turn = int((behavior.get("override") or {}).get("turn", 0))
        user_message = ev.initial_message(
            eff, ev.coarse_category(categories.get(target, [])), disclosed)

        hit_turn = None
        best_rank = None
        override_detected = False
        wasted_asks = 0
        asks = 0
        constraints_gained = 0
        ask_seq: list[str] = []
        expected_next = list(disclosed)     # constraints embedded in the pending message

        pp_rng = random.Random(f"{sample['sample_id']}:{paraphrase_level}")

        for turn in range(1, ev.MAX_TURNS + 1):
            agent_message = paraphrase(user_message, paraphrase_level, pp_rng)
            try:
                response = agent.respond(session_id, agent_message, turn, ev.TOP_K)
            except Exception:
                response = {"message": "", "ask_attribute": None, "recommendations": []}
            if not isinstance(response, dict) or not isinstance(response.get("message"), str):
                response = {"message": "", "ask_attribute": None, "recommendations": []}
            ranked_valid = ev.normalize_recommendations(response.get("recommendations"), catalog_ids)

            trace = agent.last_trace or {}
            full_ranked = trace.get("ranked") or []
            target_rank = full_ranked.index(target) + 1 if target in full_ranked else None
            raw_ranked = trace.get("raw_ranked") or []
            raw_target_rank = raw_ranked.index(target) + 1 if target in raw_ranked else None
            cat_set = trace.get("cat_pool_set")
            casc_set = trace.get("cascade_pool_set")
            expected_norms = [norm(str(v)) for v in expected_next]
            # Parsed constraints and newly inserted slots are different facts:
            # a repeated/override constraint may parse perfectly while merging
            # into an existing slot.  L1 measures parsing, not insertion.
            parsed_norms = list(trace.get("parsed_constraints") or
                                trace.get("slots_added") or [])
            matched = semantic_match_count(expected_norms, parsed_norms)
            belief_top = trace.get("belief_top") or []
            belief_rank = belief_top.index(target) + 1 if target in belief_top else None
            if trace.get("event") == "override":
                override_detected = True
            turn_rows.append({
                "sample_id": sample["sample_id"], "scenario": sample["scenario_type"],
                "turn": turn, "event": trace.get("event"), "parser": trace.get("parser"),
                "route_correct": (trace.get("event") == ROUTE_EXPECT.get(sample["scenario_type"]))
                                 if turn == 1 else None,
                "cat_pool": trace.get("cat_pool"),
                "target_in_cat": (target in cat_set) if cat_set is not None else True,
                "cascade_pool": trace.get("cascade_pool"),
                "target_in_cascade": (target in casc_set) if casc_set is not None else True,
                "n_candidates": trace.get("n_candidates"),
                "target_in_candidates": (
                    target in trace.get("candidate_set")
                    if trace.get("candidate_set") is not None
                    else target_rank is not None
                ),
                "raw_target_rank": raw_target_rank,
                "target_rank": target_rank,
                "belief_rank": belief_rank,
                "target_in_belief_top10": belief_rank is not None,
                "eligible": override_applied,
                "shown_asins": "|".join(trace.get("shown_asins") or []),
                "ask_attribute": trace.get("ask_attribute"),
                "gate": trace.get("gate"),
                "eig_max": max(trace.get("eig", {}).values(), default=None),
                "latency_ms": trace.get("latency_ms"),
                "expected_constraints": len(expected_next),
                "parsed_constraints_matched": matched,
            })
            ask_seq.append(str(trace.get("ask_attribute")))

            if override_applied and target in ranked_valid:
                best_rank = ranked_valid.index(target) + 1
                hit_turn = turn
                break
            if turn == ev.MAX_TURNS:
                break

            override = eff.get("behavior", {}).get("override") or {}
            if not override_applied and turn + 1 == int(override.get("turn", 3)):
                override_applied = True
                new_value = str(override.get("new_value", ""))
                if new_value:
                    disclosed.add(new_value)
                user_message = str(override.get("message",
                                                "Actually, please ignore my earlier preference."))
                expected_next = [new_value] if new_value else []
            else:
                before = set(disclosed)
                user_message, boundary_used = ev.customer_reply(
                    eff, response.get("ask_attribute"), disclosed, boundary_used)
                expected_next = sorted(disclosed - before)
                if response.get("ask_attribute"):
                    asks += 1
                    constraints_gained += len(expected_next)
                    if not expected_next:
                        wasted_asks += 1

        session_rows.append({
            "sample_id": sample["sample_id"], "scenario": sample["scenario_type"],
            "hit": hit_turn is not None, "first_hit_turn": hit_turn, "best_rank": best_rank,
            "reciprocal_rank": 0.0 if best_rank is None else 1.0 / best_rank,
            "turns_used": hit_turn or ev.MAX_TURNS, "ask_seq": "|".join(ask_seq),
            "override_detected": override_detected if sample["scenario_type"] == "intent_override" else None,
            "wasted_asks": wasted_asks,
            "constraints_per_ask": constraints_gained / asks if asks else None,
        })
        if progress_cb is not None:
            progress_cb(idx, len(samples))
        if idx % 25 == 0:
            print(f"[eval] {idx}/{len(samples)} sessions done")

    elapsed = time.perf_counter() - t_run
    overall = ev.metric_summary(session_rows)
    efficiency = max(0.0, min(1.0, (11.0 - float(overall["mttc"])) / 10.0))
    technical = 0.50 * overall["hit_rate_at_10"] + 0.30 * overall["mrr"] + 0.20 * efficiency
    grouped = defaultdict(list)
    for row in session_rows:
        grouped[row["scenario"]].append(row)

    summary = {
        "config": str(config_path or "configs/default.json"), "tag": tag,
        "paraphrase_level": paraphrase_level,
        "dataset": dataset, "n_sessions": len(samples),
        "elapsed_seconds": round(elapsed, 1),
        **overall,
        "efficiency": round(efficiency, 6),
        "technical_score": round(technical, 6),
        "scenario_metrics": {name: ev.metric_summary(rows) for name, rows in sorted(grouped.items())},
        "link_metrics": aggregate_links(turn_rows, session_rows),
    }

    out = Path(runs_dir) / (datetime.now().strftime("%m%d_%H%M%S") + (f"_{tag}" if tag else ""))
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_csv(out / "per_session.csv", session_rows)
    _write_csv(out / "per_turn.csv", turn_rows)
    summary["run_dir"] = str(out)
    return summary


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
