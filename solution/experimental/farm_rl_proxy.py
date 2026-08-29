"""Executable proxy for the FARM-RL architecture.

This deliberately stays stdlib-only.  It validates two hypotheses from the full
architecture without pretending to implement the neural retriever or the learned
RL policy:

1. Field-signature alignment should dominate generic popularity when a dialogue
   constraint is known to come from a product's salient attribute fields.
2. A calibrated action policy can emit before the fixed turn-three floor when the
   aligned candidate set is already small.

The production candidate described in ``FARM_RL_ARCHITECTURE.md`` replaces the
substring alignment with neural field matching and replaces the small-pool rule
with a learned, reward-aligned policy.
"""
from __future__ import annotations

import os

from src.agent import Agent as BaselineAgent


RERANK_LIMIT = int(os.environ.get("TJ_FARM_RERANK_LIMIT", "50"))
EMIT_POOL_MAX = int(os.environ.get("TJ_FARM_EMIT_POOL_MAX", "3"))


class Agent(BaselineAgent):
    """Baseline plus a field-alignment residual and an early-emission proxy."""

    def _covers(self, parent_asin, constraint):
        """Whether a salient field value covers a recovered dialogue constraint.

        Both directions are intentional.  The evaluator can reveal a semicolon-
        separated field value that Layer-A NLU splits into smaller constraints.
        Exact equality alone therefore throws away useful field provenance.
        """
        if len(constraint) < 3:
            return False
        return any(
            constraint == value or constraint in value or value in constraint
            for value in self.card[parent_asin]
        )

    def _field_coverage(self, parent_asin, constraints):
        return sum(self._covers(parent_asin, value) for value in constraints)

    def _rank(self, st, top_k):
        exact, baseline_ranked = super()._rank(st, max(top_k, RERANK_LIMIT))
        if not st.constraints or not baseline_ranked:
            return exact, baseline_ranked[:top_k]

        base_order = {parent_asin: rank for rank, parent_asin in enumerate(baseline_ranked)}
        base_scores = dict(st.diag.get("scores") or {})

        # Re-rank the baseline shortlist by the number of dialogue constraints
        # aligned to salient product fields.  The baseline order remains the
        # deterministic tie-break, so this layer is a residual rather than a
        # replacement for exact/BM25/prior scoring.
        baseline_ranked.sort(
            key=lambda parent_asin: (
                -self._field_coverage(parent_asin, st.constraints),
                base_order[parent_asin],
            )
        )

        # The full exact set is also checked for complete field alignment.  This
        # gives the emission gate a better uncertainty set than generic attribute-
        # span containment while retaining the baseline set if parsing was noisy.
        aligned = [
            parent_asin
            for parent_asin in exact
            if all(self._covers(parent_asin, value) for value in st.constraints)
        ]
        if aligned:
            exact = aligned

        st.diag["field_aligned_candidates"] = len(aligned)
        st.diag["base_scores"] = base_scores
        st.diag["scores"] = {
            parent_asin: round(
                100.0 * self._field_coverage(parent_asin, st.constraints)
                + float(base_scores.get(parent_asin, 0.0)),
                3,
            )
            for parent_asin in baseline_ranked[:top_k]
        }
        return exact, baseline_ranked[:top_k]

    def _emit(self, st, exact, ranked):
        # This is a deliberately transparent proxy for the future RL emit head.
        # Turn one remains conservative; from turn two onward, a small aligned
        # posterior support is allowed to beat the fixed turn-three floor.
        if ranked and st.turn >= 2 and len(exact) <= EMIT_POOL_MAX:
            return True, f"FARM proxy: aligned pool <= {EMIT_POOL_MAX}"
        return super()._emit(st, exact, ranked)

