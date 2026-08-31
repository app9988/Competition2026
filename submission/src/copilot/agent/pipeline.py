"""Business orchestration only - every algorithmic step is a pluggable module."""
from __future__ import annotations

import time

# imports register the built-in plugins
import copilot.algo.parsing.template_parser  # noqa: F401
import copilot.algo.parsing.fuzzy_parser  # noqa: F401
import copilot.algo.routing.rule_router  # noqa: F401
import copilot.algo.ranking.linear_ranker  # noqa: F401
import copilot.algo.dialog.gru_gate_policy  # noqa: F401

from copilot.algo.dialog.state_machine import apply_event
from copilot.algo.retrieval.bm25_retriever import BM25Retriever
from copilot.algo.retrieval.category_filter import CategoryFilter
from copilot.algo.retrieval.constraint_matcher import ConstraintMatcher
from copilot.core.registry import build
from copilot.core.textnorm import norm, query_terms
from copilot.core.types import SessionState
from copilot.services.catalog import CatalogService

POOL_CAP = 1500
RANKED_TRACE_CAP = 200


class Pipeline:
    def __init__(self, svc: CatalogService, config: dict) -> None:
        self.svc = svc
        self.cfg = config
        self.router = build("router", config.get("router", "rule"),
                            parser_names=config.get("parsers", ["template", "fuzzy"]))
        self.cat_filter = CategoryFilter(svc)
        self.matcher = ConstraintMatcher(svc, config.get("cascade", {}))
        self.ranker = build("ranker", config.get("ranker_name", "linear"),
                            svc=svc, weights=config.get("ranker", {}))
        self.policy = build("ask_policy", config.get("ask_policy", "gru_gate"),
                            svc=svc, config=config.get("ask", {}))
        self.bm25 = None
        if config.get("channels", {}).get("bm25", True):
            self.bm25 = BM25Retriever(svc.fts_path)
        self.bm25_top = config.get("bm25_top", 500)
        self.sessions: dict[str, SessionState] = {}
        self.last_trace: dict | None = None

    def reset(self, session_id: str, user_profile: dict) -> None:
        state = SessionState(session_id=session_id, profile=user_profile or {})
        tags = (user_profile or {}).get("preference_tags") or []
        state.profile_tokens = [str(t).lower() for t in tags if t]
        self.sessions[session_id] = state

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        t0 = time.perf_counter()
        state = self.sessions[session_id]
        state.turn = turn

        pr = self.router.parse(user_message, turn)
        added = apply_event(state, pr)

        # An override starts a new intent.  Earlier exposures were judged
        # against the old intent and must be eligible under the new one.
        if pr.event == "override":
            state.shown_asins.clear()

        cat_pool, cat_mode = self.cat_filter.filter(state)
        pool, cascade_trace = self.matcher.cascade(cat_pool, state.slots)

        bm25_ranks: dict[str, int] = {}
        if self.bm25 is not None:
            text = " ".join([state.category_text or ""] + [s.value for s in state.slots])
            for i, asin in enumerate(self.bm25.search(query_terms(text), self.bm25_top)):
                bm25_ranks[asin] = i

        candidates: dict[str, dict] = {a: {"pool": True} for a in pool[:POOL_CAP]}
        for asin, rank in bm25_ranks.items():
            candidates.setdefault(asin, {"pool": False})["bm25_rank"] = rank

        raw_ranked = self.ranker.rank(candidates, state, self.bm25_top)
        # Reaching another turn means none of the previously exposed products
        # completed the session.  Treat that as online negative feedback and
        # promote the best unseen product.  If a hostile/very long session
        # exhausts the candidate pool, safely fall back to the original list.
        ranked = [(asin, score) for asin, score in raw_ranked
                  if asin not in state.shown_asins]
        if not ranked:
            state.shown_asins.clear()
            ranked = raw_ranked
        ask = self.policy.decide(state, ranked)
        if ask.attribute:
            state.asked[ask.attribute] = state.asked.get(ask.attribute, 0) + 1
        state.ask_history.append(ask.attribute)

        if ask.show_k >= top_k:
            # exploit phase; page through the ranking when a full list already
            # failed and the customer explicitly had nothing new to add. Any
            # other event (override, reveal, initial) resets to page 0 - in
            # intent-override sessions pre-override "misses" prove nothing.
            if pr.event in ("no_pref", "ask_prompt") and state.last_show_full and not added:
                state.page += 1
            else:
                state.page = 0
            window = ranked[state.page * top_k:(state.page + 1) * top_k]
            if not window:
                state.page = 0
                window = ranked[:top_k]
            top10 = [asin for asin, _ in window]
            state.last_show_full = True
        else:
            top10 = [asin for asin, _ in ranked[:ask.show_k]]
            state.last_show_full = False
            state.page = 0
        state.shown_asins.update(top10)
        self.last_trace = {
            "turn": turn,
            "event": pr.event,
            "parser": pr.parser,
            "parsed_constraints": [norm(value) for value in pr.constraints if value],
            "slots_added": [s.norm_value for s in added],
            "n_slots": len(state.slots),
            "cat_mode": cat_mode,
            "cat_pool": len(cat_pool),
            "cat_pool_set": set(cat_pool) if len(cat_pool) < 20000 else None,
            "cascade_pool": len(pool),
            "cascade_pool_set": set(pool) if len(pool) < 20000 else None,
            "cascade_trace": cascade_trace,
            "n_candidates": len(candidates),
            "candidate_set": set(candidates),
            "n_seen": len(state.shown_asins),
            "raw_ranked": [asin for asin, _ in raw_ranked[:RANKED_TRACE_CAP]],
            "ranked": [asin for asin, _ in ranked[:RANKED_TRACE_CAP]],
            "shown_asins": list(top10),
            "ask_attribute": ask.attribute,
            "gate": round(ask.gate, 4),
            "eig": {k: round(v, 4) for k, v in ask.eig.items()},
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
        return {
            "message": ask.text,
            "ask_attribute": ask.attribute,
            "recommendations": [{"parent_asin": asin} for asin in top10],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }
