"""Per-link (L1..L6) aggregation over per-turn instrumentation records."""
from __future__ import annotations

import statistics


def _mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 4) if xs else None


def _rate(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(1 for x in xs if x) / len(xs), 4) if xs else None


def aggregate_links(turn_rows: list[dict], session_rows: list[dict]) -> dict:
    reveal_rows = [r for r in turn_rows if r.get("expected_constraints")]
    parse_hits = sum(r["parsed_constraints_matched"] for r in reveal_rows)
    parse_total = sum(r["expected_constraints"] for r in reveal_rows)
    t1 = [r for r in turn_rows if r["turn"] == 1]
    eligible = [r for r in turn_rows if r.get("eligible", True)]

    return {
        "L1_parsing": {
            "constraint_parse_recall": round(parse_hits / parse_total, 4) if parse_total else None,
            "parser_coverage": _rate([r.get("event") not in (None, "", "unknown")
                                      and r.get("parser") not in (None, "", "none")
                                      for r in turn_rows]),
            "template_hit_rate": _rate([r["parser"] == "template" for r in turn_rows]),
        },
        "L2_routing": {
            "turn1_route_accuracy": _rate([r.get("route_correct") for r in t1]),
            "override_detected_rate": _rate([s.get("override_detected") for s in session_rows
                                             if s["scenario"] == "intent_override"]),
        },
        "L3_belief": {
            "target_in_belief_top10": _rate([r.get("target_in_belief_top10")
                                             for r in eligible]),
            "belief_rank_mean": _mean([r["belief_rank"] for r in eligible
                                       if r.get("belief_rank")]),
        },
        "L3_recall": {
            "category_pool_size_mean_t1": _mean([r["cat_pool"] for r in t1]),
            "target_in_category_pool_t1": _rate([r["target_in_cat"] for r in t1]),
            "cascade_pool_size_mean": _mean([r["cascade_pool"] for r in turn_rows]),
            "target_in_cascade_pool": _rate([r["target_in_cascade"] for r in turn_rows]),
            "target_in_candidates": _rate([r.get("target_in_candidates") for r in turn_rows]),
        },
        "L4_ranking": {
            "target_rank_mean_when_present": _mean([r["target_rank"] for r in eligible]),
            "target_rank_t1_mean": _mean([r["target_rank"] for r in t1]),
            "rank_le10_rate": _rate([(r["target_rank"] is not None and r["target_rank"] <= 10)
                                     for r in eligible]),
        },
        "L5_asking": {
            "eig_max_mean": _mean([r["eig_max"] for r in turn_rows]),
            "gate_mean": _mean([r["gate"] for r in turn_rows]),
            "wasted_ask_rate": _rate([s.get("wasted_asks", 0) > 0 for s in session_rows]),
            "info_constraints_per_ask": _mean([s.get("constraints_per_ask") for s in session_rows]),
        },
        "L6_session": {
            "mean_latency_ms": _mean([r["latency_ms"] for r in turn_rows]),
            "mean_turns_used": _mean([s["turns_used"] for s in session_rows]),
        },
    }
