"""Simulator-in-the-loop expected information gain.

For every candidate in the (truncated) pool, replay the customer policy over
its precomputed intent card: if this candidate were the target and we asked
attribute `a`, which reply would come back? Candidates are partitioned by
reply; EIG(a) = H(pool) - E[H(pool | reply)].
"""
from __future__ import annotations

import math

from copilot.core.textnorm import norm
from copilot.core.types import ASKABLE_ATTRIBUTES
from copilot.services.catalog import CatalogService


def entropy(probs: list[float]) -> float:
    return -sum(p * math.log(p) for p in probs if p > 1e-12)


def softmax(scores: list[float], temp: float = 2.0) -> list[float]:
    if not scores:
        return []
    top = max(scores)
    exps = [math.exp((s - top) / temp) for s in scores]
    z = sum(exps)
    return [e / z for e in exps]


def _reply_key(cons: list[str], types: list[str], disclosed: set[str], attr: str) -> tuple:
    matches = []
    for value, ctype in zip(cons, types):
        if norm(value) in disclosed:
            continue
        if attr == "other" or ctype == attr:
            matches.append(value)
            if len(matches) == 2:
                break
    return tuple(matches)


def eig_table(ranked: list[tuple[str, float]], svc: CatalogService,
              disclosed: set[str], attrs: list[str] | None = None,
              cap: int = 300, temp: float = 2.0) -> dict[str, float]:
    pool = ranked[:cap]
    if not pool:
        return {}
    probs = softmax([s for _, s in pool], temp)
    h_now = entropy(probs)
    attrs = attrs or [a for a in ASKABLE_ATTRIBUTES if a != "category"]
    table: dict[str, float] = {}
    for attr in attrs:
        partitions: dict[tuple, list[float]] = {}
        for (asin, _), p in zip(pool, probs):
            cons, types = svc.cards.get(asin, ([], []))
            partitions.setdefault(_reply_key(cons, types, disclosed, attr), []).append(p)
        h_next = 0.0
        for members in partitions.values():
            mass = sum(members)
            if mass <= 1e-12:
                continue
            h_next += mass * entropy([p / mass for p in members])
        table[attr] = max(0.0, h_now - h_next)
    return table
