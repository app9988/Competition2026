"""GRU-gated slot store.

Reset gate: an intent override down-weights pre-override soft slots (kept for
scoring, dropped from hard filtering) and installs the new hard constraint.
Update gate: new evidence enters with weight scaled by parser confidence;
duplicate values merge by max weight.
"""
from __future__ import annotations

from copilot.algo.dialog.simulator_model import classify_constraint
from copilot.core.textnorm import norm
from copilot.core.types import Observation, ParseResult, SessionState, Slot

RESET_DAMP = 0.25          # weight multiplier applied by the reset gate
PROFILE_DECAY = 0.9        # per-turn decay for low-trust sources


def _add_constraints(state: SessionState, values: list[str], source: str,
                     confidence: float) -> list[Slot]:
    added = []
    for raw in values:
        raw = raw.strip()
        if not raw:
            continue
        stype = classify_constraint(raw)
        slot = Slot.from_text(raw, stype, source, state.turn, weight=min(1.0, confidence))
        dup = next((s for s in state.slots if s.norm_value == slot.norm_value), None)
        if dup is not None:
            dup.weight = max(dup.weight, slot.weight)
            continue
        state.slots.append(slot)
        state.disclosed_norms.add(norm(raw))
        added.append(slot)
    return added


def apply_event(state: SessionState, pr: ParseResult) -> list[Slot]:
    state.events.append(pr.event)
    previous_ask = state.ask_history[-1] if state.ask_history else None
    state.observations.append(Observation(
        event=pr.event,
        constraints=tuple(value for value in pr.constraints if value),
        ask_attribute=pr.attr or previous_ask,
        turn=state.turn,
        confidence=pr.confidence,
    ))
    added: list[Slot] = []

    if pr.event in ("initial_buying", "initial_browsing", "initial_override"):
        state.category_text = pr.category
        state.scenario_guess = {"initial_buying": "buying",
                                "initial_browsing": "browsing",
                                "initial_override": "intent_override"}[pr.event]
        source = "initial_soft" if pr.event == "initial_override" else "initial"
        added = _add_constraints(state, pr.constraints, source, pr.confidence)

    elif pr.event == "override":
        state.scenario_guess = "intent_override"
        for slot in state.slots:                      # reset gate
            if slot.source in ("initial", "initial_soft"):
                slot.weight *= RESET_DAMP
        added = _add_constraints(state, pr.constraints, "override", pr.confidence)

    elif pr.event == "reveal":
        added = _add_constraints(state, pr.constraints, "reveal", pr.confidence)

    elif pr.event == "no_pref":
        if pr.attr:
            state.exhausted.add(pr.attr)
        # "no additional preference for other" == every card constraint of the
        # true target is already on the table (wildcard matched nothing new)
        if pr.attr == "other":
            state.all_disclosed = True

    elif pr.event == "boundary_no_pref":
        if pr.attr:
            state.exhausted.add(pr.attr)
        state.boundary_mode = True
        state.scenario_guess = "boundary?"

    # time decay for weak sources
    for slot in state.slots:
        if slot.source == "profile":
            slot.weight *= PROFILE_DECAY
    return added
