"""Tier-2 robust fallback for paraphrased messages (private-set B mode).

Cue-word scoring instead of exact templates. Constraint payloads are cleaned
of carrier phrases so downstream substring/containment matching stays sharp.
"""
from __future__ import annotations

import re

from copilot.core.registry import register
from copilot.core.types import ParseResult, ASKABLE_ATTRIBUTES

_LOOKING = re.compile(
    r"\b(?:looking for|want|need|searching for|shopping for|browsing for|browse for|"
    r"show me|find me|pull up|check out|"
    r"thinking about|interested in|after)\b[:\s]*(?P<rest>.+)", re.I)
# Delimiters that end the category phrase and start the carrier text.  A bare
# hyphen/"and" is deliberately not a delimiter: both occur inside real catalog
# categories (for example ``T-Shirts`` and ``Shoes & Jewelry``).  The previous
# broad split silently routed those categories to a smaller, incorrect pool.
_CAT_STOP = re.compile(
    r"\s+and\s+one\s+thing\b|\s+but\b|,\s*(?:still|nothing)\b|"
    r"\.\s+|\s+[-\u2013\u2014]\s+|\s+(?:still|just)\b|\bfor\s+now\b|[;:!?]",
    re.I,
)
_OVERRIDE_CUES = ("actually", "ignore", "instead", "changed my mind", "forget",
                  "scratch", "never mind", "on second thought", "rather have",
                  "switch to")
_NOPREF_CUES = ("no preference", "no more preference", "don't have a preference",
                "don't care", "doesn't matter", "your judgment", "you decide",
                "up to you", "anything works", "nothing else", "does not matter",
                "not important", "irrelevant", "no strong feelings", "whatever works")
_EXPLORE_CUES = ("exploring", "browsing", "just looking", "not sure", "open to",
                 "nothing specific", "no rush", "looking around", "comparing",
                 "window shopping", "no strong requirements")
_BOUNDARY_CUES = ("your judgment", "you decide", "up to you", "whatever works")
# carrier phrases that precede the actual constraint payload
_REQ_SPLIT = re.compile(
    r"(?:requirement is|need is|needs? to be|matters is|matters to me(?: here)?|"
    r"one thing really matters|must have|must be|has to be|it must(?: have| be)?|"
    r"care about|important things are|"
    r"key things|what i need is|i need|rather have|switch to|prefer)\s*:?\s*", re.I)
_PART_SPLIT = re.compile(r";|,\s*and\s+|\s+plus\s+|\s+and\s+also\s+", re.I)
_LEAD_JUNK = re.compile(r"^(?:it|its|is|are|the|a|an|my|honestly|mostly|really|here)\s+", re.I)


def _clean_payload(text: str) -> str:
    text = _REQ_SPLIT.split(text)[-1]
    text = text.strip(" .;,:-")
    prev = None
    while prev != text:
        prev = text
        text = _LEAD_JUNK.sub("", text)
    return text.strip(" .;,:-")


def _category_phrase(text: str) -> str:
    phrase = _CAT_STOP.split(text, maxsplit=1)[0].strip(" .;,:-")
    return re.sub(r"^(?:some|a|an|the)\s+", "", phrase, flags=re.I)


@register("parser", "fuzzy")
class FuzzyParser:
    def parse(self, message: str, turn: int) -> ParseResult | None:
        msg = message.strip()
        if not msg:
            return None
        low = msg.lower()

        if any(cue in low for cue in _NOPREF_CUES):
            attr = next((a for a in ASKABLE_ATTRIBUTES if a in low), "other")
            event = ("boundary_no_pref"
                     if any(cue in low for cue in _BOUNDARY_CUES) else "no_pref")
            return ParseResult(event=event, attr=attr, parser="fuzzy", confidence=0.7)

        if turn > 1 and any(cue in low for cue in _OVERRIDE_CUES):
            tail = _clean_payload(msg)
            return ParseResult(event="override", constraints=[tail] if tail else [],
                               parser="fuzzy", confidence=0.7)

        if turn == 1:
            category, cons = None, []
            m = _LOOKING.search(msg)
            rest = m.group("rest").strip() if m else msg
            category = _category_phrase(rest)
            category_at = rest.lower().find(category.lower()) if category else -1
            remainder = rest[category_at + len(category):] if category_at >= 0 else rest
            payload = _clean_payload(remainder)
            explore = any(cue in low for cue in _EXPLORE_CUES)
            if payload and not explore and payload.lower() != category.lower():
                cons = [payload]
            # Stress-mode initial-override messages have a category sentence
            # followed by an old preference, while buying messages contain an
            # explicit requirement carrier.  Preserve that distinction even
            # when the exact simulator template has been paraphrased.
            buying_cue = any(cue in remainder.lower() for cue in (
                "requirement", "must have", "must be", "one thing really matters",
                "key need", "key thing",
            ))
            sentence_then_preference = remainder.lstrip().startswith(".") and not buying_cue
            if explore or not cons:
                event = "initial_browsing"
            elif sentence_then_preference:
                event = "initial_override"
            else:
                event = "initial_buying"
            return ParseResult(event=event, category=category or None, constraints=cons,
                               parser="fuzzy", confidence=0.6)

        # mid-session free text: clauses are (possibly reworded) constraints
        parts = [_clean_payload(p) for p in _PART_SPLIT.split(_clean_payload(msg))]
        parts = [p for p in parts if len(p) > 1]
        if parts:
            return ParseResult(event="reveal", constraints=parts[:4], parser="fuzzy",
                               confidence=0.5)
        return ParseResult(event="unknown", parser="fuzzy", confidence=0.0)
