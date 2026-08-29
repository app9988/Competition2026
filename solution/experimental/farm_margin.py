"""FARM field-alignment + Top-1 score-margin emission gate (combined experiment).

FARM's own early-emit fires whenever the aligned pool is small (len(exact) <=
EMIT_POOL_MAX), which sometimes emits a not-yet-Rank-1 result and costs MRR
(0.9808 -> 0.9783). This variant keeps FARM's field-coverage residual rank but
replaces the pool-size trigger with the score-margin trigger (Paper C top1_conf,
CIKM 2024): emit early only when Rank-1's field-coverage score dominates Rank-2
by >= TJ_MARGIN, which preserves MRR.

Env:
  TJ_MARGIN       score-margin threshold on FARM's coverage scores (default 100
                  = require Rank-1 to cover strictly more constraints).
  TJ_FARM_POOLEMIT  "1" also keep FARM's original pool<=MAX rule (default "0").
"""
from __future__ import annotations

import os

from experimental.farm_rl_proxy import Agent as FarmAgent
from src.agent import Agent as BaselineAgent

MARGIN = float(os.environ.get("TJ_MARGIN", "1"))   # tuned: 1 = best (public-200 0.9647)
KEEP_POOLEMIT = os.environ.get("TJ_FARM_POOLEMIT", "0") == "1"


class Agent(FarmAgent):
    def _emit(self, st, exact, ranked):
        # Score-margin early emit on FARM's field-coverage scores (MRR-safe).
        if MARGIN and st.turn >= 2 and st.constraints and len(ranked) >= 2:
            sc = st.diag.get("scores", {})
            if ranked[0] in sc and ranked[1] in sc and (sc[ranked[0]] - sc[ranked[1]]) >= MARGIN:
                return True, "margin gate on FARM coverage scores"
        if KEEP_POOLEMIT:
            return FarmAgent._emit(self, st, exact, ranked)     # FARM pool<=MAX + baseline
        return BaselineAgent._emit(self, st, exact, ranked)     # skip FARM pool rule
