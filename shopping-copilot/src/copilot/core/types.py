from __future__ import annotations

import re
from dataclasses import dataclass, field

from copilot.core.textnorm import norm

ASKABLE_ATTRIBUTES = (
    "category", "material", "color", "size", "style", "brand",
    "budget", "feature", "use_case", "other",
)

_BUDGET_RE = re.compile(r"\$\s*([0-9]+(?:\.[0-9]+)?)")
_COLOR_PREFIX_RE = re.compile(r"^color:\s*([a-z]+)\s*$", re.I)


@dataclass
class Slot:
    stype: str
    value: str
    norm_value: str
    weight: float = 1.0
    source: str = "reveal"          # initial | initial_soft | reveal | override | profile
    turn_added: int = 0
    price: float | None = None

    @classmethod
    def from_text(cls, raw: str, stype: str, source: str, turn: int, weight: float = 1.0) -> "Slot":
        raw = raw.strip()
        price = None
        # cap length so hostile/degenerate inputs cannot blow up matching cost
        nv = " ".join(norm(raw).split()[:60])
        if stype == "budget":
            m = _BUDGET_RE.search(raw)
            if m:
                price = float(m.group(1))
        m = _COLOR_PREFIX_RE.match(raw)
        if m:
            stype = "color"
            nv = m.group(1).lower()
        return cls(stype=stype, value=raw, norm_value=nv, weight=weight,
                   source=source, turn_added=turn, price=price)


@dataclass
class ParseResult:
    event: str                      # initial_buying | initial_browsing | initial_override |
                                    # override | reveal | no_pref | boundary_no_pref |
                                    # ask_prompt | unknown
    category: str | None = None
    constraints: list[str] = field(default_factory=list)
    attr: str | None = None
    parser: str = "template"
    confidence: float = 1.0


@dataclass
class Ask:
    attribute: str | None
    text: str
    gate: float = 0.0
    eig: dict = field(default_factory=dict)
    show_k: int = 10


@dataclass(frozen=True)
class Observation:
    """One user observation together with the action that elicited it.

    Keeping this separate from the accumulated slots preserves ordering and
    negative evidence (``no_pref``), both of which a set of slot strings loses.
    """

    event: str
    constraints: tuple[str, ...]
    ask_attribute: str | None
    turn: int
    confidence: float = 1.0


@dataclass
class SessionState:
    session_id: str
    profile: dict
    category_text: str | None = None
    slots: list[Slot] = field(default_factory=list)
    asked: dict = field(default_factory=dict)
    exhausted: set = field(default_factory=set)
    disclosed_norms: set = field(default_factory=set)
    scenario_guess: str = "unknown"
    turn: int = 0
    boundary_mode: bool = False
    all_disclosed: bool = False
    page: int = 0
    last_show_full: bool = False
    profile_tokens: list[str] = field(default_factory=list)
    ask_history: list = field(default_factory=list)
    events: list = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    # A continued conversation is implicit negative feedback for every item
    # exposed on the previous turn.  Keep session-local exposure history so
    # rejected items do not occupy the first position again.
    shown_asins: set[str] = field(default_factory=set)
