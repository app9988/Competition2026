"""Ask policy: wildcard-first elicitation constrained by a GRU-style gate.

The gate g_t = sigmoid(wH*H + wE*maxEIG - wt*turn/10 - wc*conf@10 + b) decides
between elicit-style and confirm-style behavior; hard constraints cap repeat
questions and respect attributes the customer declared no preference for.
"""
from __future__ import annotations

import math

from copilot.algo.dialog.eig import eig_table, entropy, softmax
from copilot.core.registry import register
from copilot.core.types import Ask, ASKABLE_ATTRIBUTES, SessionState
from copilot.services.catalog import CatalogService

QUESTION_TEXT = {
    "other": "To narrow things down: is there anything specific that matters to you about it?",
    "category": "Which exact type of item are you shopping for?",
    "material": "Do you have a material preference?",
    "color": "Is there a color you want?",
    "size": "Any size or fit requirement?",
    "style": "Any particular style you prefer?",
    "brand": "Do you prefer a specific brand or store?",
    "budget": "What budget range are you thinking of?",
    "feature": "Is there a specific feature it must have?",
    "use_case": "What will you mainly use it for?",
}


@register("ask_policy", "gru_gate")
class GruGatePolicy:
    def __init__(self, svc: CatalogService, config: dict | None = None) -> None:
        self.svc = svc
        cfg = config or {}
        self.mode = cfg.get("mode", "wildcard_first")
        self.max_other = cfg.get("max_other_asks", 3)
        self.max_attr = cfg.get("max_attr_asks", 2)
        self.cap = cfg.get("eig_pool_cap", 300)
        self.eps = cfg.get("eps_stop", 0.05)
        self.full_list_turn = cfg.get("full_list_turn", 7)
        self.sequential_top1 = cfg.get("sequential_top1", False)
        self.late_turn_top_k: dict[int, int] = {}
        for raw_turn, raw_k in (cfg.get("late_turn_top_k") or {}).items():
            try:
                turn = int(raw_turn)
                show_k = int(raw_k)
            except (TypeError, ValueError):
                continue
            if 1 <= turn <= 10 and 1 <= show_k <= 10:
                self.late_turn_top_k[turn] = show_k
        gate = cfg.get("gate", {})
        self.w_h = gate.get("w_H", 1.0)
        self.w_e = gate.get("w_EIG", 2.0)
        self.w_t = gate.get("w_turn", 0.6)
        self.w_c = gate.get("w_conf", 1.5)
        self.bias = gate.get("bias", 0.0)

    def decide(self, state: SessionState, ranked: list[tuple[str, float]]) -> Ask:
        eig = eig_table(ranked, self.svc, state.disclosed_norms, cap=self.cap)
        probs = softmax([s for _, s in ranked[: self.cap]])
        h_norm = entropy(probs) / math.log(len(probs)) if len(probs) > 1 else 0.0
        conf10 = sum(probs[:10])
        max_eig = max(eig.values()) if eig else 0.0
        gate = 1.0 / (1.0 + math.exp(-(self.w_h * h_norm + self.w_e * max_eig
                                       - self.w_t * state.turn / 10.0
                                       - self.w_c * conf10 + self.bias)))

        attr = self._choose_attr(state, eig)
        if attr is None:
            text = ("Based on everything so far these are my top picks - "
                    "the first one should be very close.")
            return Ask(attribute=None, text=text, gate=gate, eig=eig, show_k=10)

        if self.mode == "never":
            return Ask(attribute=None, text="Here are the closest matches I found.",
                       gate=gate, eig=eig,
                       show_k=self._sequential_show_k(state.turn)
                       if self.sequential_top1 else 10)

        # Rank-confidence truncation: while more information is still expected
        # (EIG above threshold), a hit at rank r>=2 locks in 0.3/r + efficiency,
        # which is worth less than converging to a rank-1 hit one turn later.
        # So expose only the top pick early and the full list once the customer
        # has confirmed exhaustion (all_disclosed), the leading hypothesis has
        # nothing left to reveal (its card is fully disclosed), or EIG dries up.
        top1_exhausted = False
        if ranked and len(state.disclosed_norms) >= 3:
            card = self.svc.card_norms.get(ranked[0][0])
            top1_exhausted = bool(card) and card <= state.disclosed_norms
        more_info_expected = (not state.all_disclosed
                              and not top1_exhausted
                              and max_eig >= self.eps
                              and state.turn < self.full_list_turn)
        # Sequential Top-1 is a small-list exploration policy: a continuing
        # session rejects the exposed item, and Pipeline promotes the next
        # unseen candidate on the next turn.  Late in a session, gradually
        # widen the list so a lower-ranked hidden target is not stranded past
        # the ten-turn deadline.  The default empty schedule preserves the
        # original Top-1 behavior.
        if self.sequential_top1:
            show_k = self._sequential_show_k(state.turn)
        else:
            show_k = 1 if more_info_expected else 10

        if gate > 0.5 and max_eig >= self.eps:
            text = QUESTION_TEXT.get(attr, QUESTION_TEXT["other"])
        else:
            text = ("Here are my current best matches - "
                    f"and one more check: {QUESTION_TEXT.get(attr, QUESTION_TEXT['other'])}")
        return Ask(attribute=attr, text=text, gate=gate, eig=eig, show_k=show_k)

    def _sequential_show_k(self, turn: int) -> int:
        show_k = 1
        for start_turn, configured_k in sorted(self.late_turn_top_k.items()):
            if turn >= start_turn:
                show_k = configured_k
        return show_k

    def _choose_attr(self, state: SessionState, eig: dict[str, float]) -> str | None:
        if self.mode == "never":
            return None
        if (self.mode == "wildcard_first" and "other" not in state.exhausted
                and state.asked.get("other", 0) < self.max_other):
            return "other"
        avail = [a for a in ASKABLE_ATTRIBUTES
                 if a not in state.exhausted and state.asked.get(a, 0) < self.max_attr]
        if not avail:
            return None
        ranked_attrs = sorted(avail, key=lambda a: -eig.get(a, 0.0))
        return ranked_attrs[0]
