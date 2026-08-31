"""Stage B: typed predicate scoring + cascade filtering with backoff.

Every slot compiles to a score in [0, 1]:
  exact  (>= 0.99): normalized substring / token hit / price inside band
  fuzzy  (< 0.99):  token-containment ratio scaled by 0.9, smooth price falloff
A slot only *filters* when the surviving pool stays non-trivial; otherwise it
degrades to a ranking feature so a bad parse can never evict the target.
"""
from __future__ import annotations

import math

from copilot.core.types import Slot
from copilot.services.catalog import CatalogService


def slot_score(slot: Slot, asin: str, svc: CatalogService) -> float:
    if slot.stype == "budget" and slot.price is not None:
        price = svc.price.get(asin)
        if price is None:
            return 0.3
        band = max(0.15 * slot.price, 2.0)
        if abs(price - slot.price) <= band:
            return 1.0
        return 0.9 * math.exp(-abs(math.log(max(price, 0.01) / slot.price)))

    text = svc.norm_text.get(asin, " ")
    nv = slot.norm_value
    if not nv:
        return 0.0
    if " " not in nv:                       # single token: word-boundary check
        return 1.0 if f" {nv} " in text else 0.0
    if nv in text:
        return 1.0
    toks = list(dict.fromkeys(t for t in nv.split() if len(t) > 1))[:40]
    if not toks:
        return 0.0
    hits = sum(1 for t in toks if f" {t} " in text)
    return 0.9 * hits / len(toks)


class ConstraintMatcher:
    def __init__(self, svc: CatalogService, config: dict) -> None:
        self.svc = svc
        self.fuzzy_threshold = config.get("fuzzy_threshold", 0.6)
        self.min_keep = config.get("min_keep", 3)
        self.min_keep_frac = config.get("min_keep_frac", 0.02)
        self.filter_weight_min = config.get("filter_weight_min", 0.5)

    def cascade(self, pool: list[str], slots: list[Slot]) -> tuple[list[str], list[dict]]:
        trace: list[dict] = []
        active = [s for s in slots if s.weight >= self.filter_weight_min]
        active.sort(key=lambda s: (-s.weight, s.turn_added))
        for slot in active:
            scores = {a: slot_score(slot, a, self.svc) for a in pool}
            strict = [a for a in pool if scores[a] >= 0.99]
            min_survivors = max(self.min_keep, int(self.min_keep_frac * len(pool)))
            # Exact-template evidence can safely select a unique item.  A
            # low-confidence fuzzy span may coincidentally match one wrong
            # product exactly, so require a non-trivial survivor set before
            # turning that evidence into a hard filter.
            if strict and (slot.weight >= 0.99 or len(strict) >= min_survivors):
                pool = strict
                trace.append({"slot": slot.value[:60], "mode": "exact", "pool": len(pool)})
                continue
            loose = [a for a in pool if scores[a] >= self.fuzzy_threshold]
            if len(loose) >= min_survivors:
                pool = loose
                trace.append({"slot": slot.value[:60], "mode": "fuzzy", "pool": len(pool)})
            else:
                trace.append({"slot": slot.value[:60], "mode": "skipped", "pool": len(pool)})
        return pool, trace
