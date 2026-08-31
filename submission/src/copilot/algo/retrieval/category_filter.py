"""Stage A: coarse-category pool. Exact match first, token-overlap fallback."""
from __future__ import annotations

from copilot.core.textnorm import norm
from copilot.core.types import SessionState
from copilot.services.catalog import CatalogService


class CategoryFilter:
    def __init__(self, svc: CatalogService) -> None:
        self.svc = svc

    def filter(self, state: SessionState) -> tuple[list[str], str]:
        if not state.category_text:
            return self.svc.all_ids(), "none"
        key = norm(state.category_text)
        pool = self.svc.cat_pool.get(key)
        if pool:
            return pool, "exact"
        want = set(key.split())
        if want:
            # containment: category tokens fully inside the extracted phrase;
            # prefer the most specific (longest) matching categories
            best: list[str] = []
            best_len = 0
            for cat, asins in self.svc.cat_pool.items():
                have = set(cat.split())
                if have and have <= want:
                    if len(have) > best_len:
                        best, best_len = list(asins), len(have)
                    elif len(have) == best_len:
                        best.extend(asins)
            if best:
                return best, "containment"
            merged: list[str] = []
            for cat, asins in self.svc.cat_pool.items():
                have = set(cat.split())
                if not have:
                    continue
                union = len(want | have)
                if union and len(want & have) / union >= 0.34:
                    merged.extend(asins)
            if merged:
                return merged, "overlap"
        return self.svc.all_ids(), "fallback_all"
