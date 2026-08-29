"""Collision-aware tail-repair experiment for the FARM ranker.

The public evaluator has a small number of sessions where several products
share the complete four-value intent card.  At that point another clarification
turn cannot add evidence, so this module makes the ambiguity explicit and
optionally applies a conservative, profile-conditioned tie-break *only inside*
the exact full-card equivalence class.

This remains an experiment rather than the submission default.  Failed metadata
tie-breaks are documented in ``RESULTS_TAIL_REPAIR.md`` but deliberately omitted
from this implementation: the active policy never guesses a hidden target.
"""
from __future__ import annotations

import os

from experimental.farm_rl_proxy import Agent as FarmAgent
from src.agent import Agent as BaselineAgent, P_BROWSE, P_BUY


TAIL_MARGIN = float(os.environ.get("TJ_TAIL_MARGIN", "0.75"))
COLLISION_RULE = os.environ.get("TJ_COLLISION_RULE", "none")
PROGRESSIVE_BATCHING = os.environ.get("TJ_PROGRESSIVE_BATCHING", "0") == "1"


class Agent(FarmAgent):
    """FARM with NLU protection and an explicit full-card collision policy."""

    def _rank(self, st, top_k):
        # Field provenance is trustworthy for the official templates (Layer A).
        # For paraphrases, retain the baseline scorer: substring-based FARM
        # coverage otherwise amplifies partial Layer-B recovery errors.
        if st.nlu_layer == "A":
            exact, ranked = FarmAgent._rank(self, st, top_k)
        else:
            exact, ranked = BaselineAgent._rank(self, st, top_k)

        if st.nlu_layer != "A" or len(st.constraints) < 4 or len(ranked) < 2:
            return exact, ranked

        known = frozenset(st.constraints)
        collision = [
            parent_asin
            for parent_asin in exact
            if len(self.card[parent_asin]) == len(st.constraints)
            and frozenset(self.card[parent_asin]) == known
        ]
        collision_set = set(collision)
        visible_collision = [item for item in ranked if item in collision_set]
        st.diag["full_card_collision"] = len(collision)
        st.diag["collision_rule"] = COLLISION_RULE
        if len(visible_collision) < 2 or COLLISION_RULE == "none":
            return exact, ranked

        base_order = {item: index for index, item in enumerate(ranked)}
        if COLLISION_RULE == "prior_only":
            # Once every visible candidate has the exact same complete intent
            # card, lexical score differences are incidental: the dialogue did
            # not disclose the title terms that caused them.  Fall back to the
            # catalog prior instead of letting BM25 manufacture confidence.
            def collision_key(parent_asin):
                return (-self.prior[parent_asin], parent_asin)

        else:
            raise ValueError(f"unknown collision rule: {COLLISION_RULE}")

        reordered = iter(sorted(visible_collision, key=collision_key))
        ranked = [next(reordered) if item in collision_set else item for item in ranked]
        st.diag["collision_order"] = visible_collision
        st.diag["collision_order_after"] = [item for item in ranked if item in collision_set]
        return exact, ranked

    def _emit(self, st, exact, ranked):
        # Replace FARM's small-pool trigger with a score-margin trigger.  This is
        # evaluated before the baseline turn floor and works for both Layer-A
        # FARM scores and Layer-B/C baseline scores.
        if TAIL_MARGIN and st.turn >= 2 and st.constraints and len(ranked) >= 2:
            scores = st.diag.get("scores", {})
            if (
                ranked[0] in scores
                and ranked[1] in scores
                and scores[ranked[0]] - scores[ranked[1]] >= TAIL_MARGIN
            ):
                return True, "tail-repair score-margin gate"
        return BaselineAgent._emit(self, st, exact, ranked)

    def _has_complete_ambiguity(self, st, ranked):
        """Whether the shortlist contains a genuinely indistinguishable group.

        FARM can split one catalog field into several recovered constraints, so
        ``len(st.constraints)`` may exceed the evaluator's four intent slots.
        Group by the original four-slot signature and require every observed
        constraint to be covered by each member of a repeated signature.
        """
        groups = {}
        for parent_asin in ranked:
            if not all(self._covers(parent_asin, value) for value in st.constraints):
                continue
            groups.setdefault(tuple(self.card[parent_asin]), []).append(parent_asin)
        return any(len(items) >= 2 for items in groups.values())

    def _respond(self, session_id, user_message, turn, top_k):
        st = self.sessions[session_id]
        if turn == 1:
            if P_BUY.search(user_message):
                st.opening_mode = "buying"
            elif P_BROWSE.search(user_message):
                st.opening_mode = "browsing"
            else:
                # The official intent-override opening matches the generic
                # P_OPEN template.  Never freeze its pre-override ranking.
                st.opening_mode = "other"
        response = super()._respond(session_id, user_message, turn, top_k)
        if not PROGRESSIVE_BATCHING:
            return response

        frozen = getattr(st, "progressive_ranking", None)
        if frozen is not None:
            # Round-robin exposure compresses every original rank 2..10 while
            # keeping the original Rank 1 untouched at turn three:
            #   turn 4 -> original ranks 2,4,6,8,10
            #   turn 5 -> original ranks 3,5,7,9
            indices = (1, 3, 5, 7, 9) if turn == 4 else (2, 4, 6, 8)
            batch = [frozen[index] for index in indices if index < len(frozen)]
            if batch:
                response["recommendations"] = [
                    {"parent_asin": parent_asin} for parent_asin in batch[:top_k]
                ]
            return response

        recommendations = [
            str(item.get("parent_asin"))
            for item in response.get("recommendations", [])
            if isinstance(item, dict) and item.get("parent_asin")
        ]
        if (
            turn == 3
            and getattr(st, "opening_mode", None) in {"buying", "browsing"}
            and st.nlu_layer == "A"
            and len(st.constraints) >= 4
            and len(recommendations) >= 2
            and self._has_complete_ambiguity(st, recommendations)
        ):
            st.progressive_ranking = tuple(recommendations)
            st.diag["progressive_batching"] = True
            response["recommendations"] = [{"parent_asin": recommendations[0]}]
        return response

    def __init__(self, catalog_path="data/catalog.jsonl", enable_trace=False):
        super().__init__(catalog_path, enable_trace=enable_trace)
