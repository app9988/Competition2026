"""Reciprocal-rank fusion utility (available for extra channels, e.g. dense)."""
from __future__ import annotations


def rrf(rankings: dict[str, list[str]], weights: dict[str, float] | None = None,
        k: int = 60) -> list[str]:
    weights = weights or {}
    scores: dict[str, float] = {}
    for name, ranking in rankings.items():
        w = weights.get(name, 1.0)
        for rank, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + w / (k + rank + 1)
    return sorted(scores, key=lambda item: (-scores[item], item))
