"""Stage F: interpretable linear scorer over the fused candidate set.

The slot weights maintained by the GRU-gated state machine feed directly into
the coverage term, coupling dialogue state and ranking.
"""
from __future__ import annotations

import math

from copilot.algo.dialog.belief import candidate_belief
from copilot.algo.retrieval.constraint_matcher import slot_score
from copilot.core.registry import register
from copilot.core.textnorm import norm
from copilot.core.types import SessionState
from copilot.services.catalog import CatalogService

DEFAULT_WEIGHTS = {
    "coverage": 10.0, "exact_bonus": 3.0, "popularity": 0.5, "price": 1.5,
    "quality": 0.0, "profile": 0.3, "category": 1.0, "pool": 2.0, "bm25": 1.0,
    "card_hit": 4.0, "card_clean": 2.0, "belief": 0.0,
}


@register("ranker", "linear")
class LinearRanker:
    def __init__(self, svc: CatalogService, weights: dict | None = None) -> None:
        self.svc = svc
        self.w = {**DEFAULT_WEIGHTS, **(weights or {})}

    def rank(self, candidates: dict[str, dict], state: SessionState,
             bm25_top: int) -> list[tuple[str, float]]:
        slots = state.slots
        total_w = sum(s.weight for s in slots) or 1.0
        budget_slot = next((s for s in slots if s.stype == "budget" and s.price), None)
        cat_key = norm(state.category_text) if state.category_text else None
        profile_boost = 2.0 if state.boundary_mode else 1.0
        disclosed = frozenset(state.disclosed_norms)
        scored: list[tuple[str, float]] = []

        for asin, info in candidates.items():
            cov = 0.0
            exact = 0
            for s in slots:
                v = slot_score(s, asin, self.svc)
                cov += s.weight * v
                if v >= 0.99:
                    exact += 1
            score = self.w["coverage"] * cov / total_w
            if slots:
                score += self.w["exact_bonus"] * exact / len(slots)
            score += self.w["popularity"] * math.log1p(self.svc.rating_n.get(asin, 0)) / 12.0
            # Average rating is only a tie-break prior after the customer has
            # explicitly exhausted the wildcard preference channel.  Applying
            # it earlier can overpower still-incomplete intent evidence.
            if state.all_disclosed:
                score += self.w["quality"] * self.svc.rating_avg.get(asin, 0.0) / 5.0
            if budget_slot is not None:
                score += self.w["price"] * slot_score(budget_slot, asin, self.svc)
            if state.profile_tokens:
                text = self.svc.norm_text.get(asin, " ")
                hits = sum(1 for t in state.profile_tokens if f" {t} " in text)
                score += self.w["profile"] * profile_boost * hits / len(state.profile_tokens)
            if cat_key and self.svc.coarse.get(asin) == cat_key:
                score += self.w["category"]
            # dialogue-consistency: disclosed constraints are verbatim card
            # entries of the true target, so card overlap is sharp evidence
            if disclosed:
                card = self.svc.card_norms.get(asin) or frozenset()
                score += self.w["card_hit"] * len(card & disclosed) / len(disclosed)
                if state.all_disclosed and card:
                    score -= self.w["card_clean"] * len(card - disclosed) / len(card)
            score += self.w["belief"] * candidate_belief(asin, state, self.svc)
            if info.get("pool"):
                score += self.w["pool"]
            r = info.get("bm25_rank")
            if r is not None:
                score += self.w["bm25"] * max(0.0, 1.0 - r / max(bm25_top, 1))
            scored.append((asin, score))

        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored
