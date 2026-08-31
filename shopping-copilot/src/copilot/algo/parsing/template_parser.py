"""Tier-1 deterministic parser anchored on the simulator's message templates."""
from __future__ import annotations

import re

from copilot.core.registry import register
from copilot.core.types import ParseResult

RE_OVERRIDE = re.compile(
    r"^Actually, ignore my earlier preference\. What I need is: (?P<new>.+)\.$")
RE_REVEAL = re.compile(r"^For that, what matters is: (?P<body>.+)\.$")
RE_NOPREF = re.compile(
    r"^I don't have (?P<kind>a|an additional) preference for (?P<attr>\w+)[;.]")
RE_ASKME = re.compile(r"^Those options are not quite right yet\.")
RE_BUYING = re.compile(
    r"^I'm looking for (?P<cat>.+?)\. A key requirement is: (?P<c1>.+)\.$")
RE_BROWSING = re.compile(r"^I'm looking for (?P<cat>.+?), but I'm still exploring\.$")
RE_OVERRIDE_INIT = re.compile(r"^I'm looking for (?P<cat>.+?)\. (?P<old>.+)$")


@register("parser", "template")
class TemplateParser:
    def parse(self, message: str, turn: int) -> ParseResult | None:
        msg = message.strip()
        m = RE_OVERRIDE.match(msg)
        if m:
            return ParseResult(event="override", constraints=[m.group("new")])
        m = RE_REVEAL.match(msg)
        if m:
            parts = [p.strip() for p in m.group("body").split("; ") if p.strip()]
            return ParseResult(event="reveal", constraints=parts)
        m = RE_NOPREF.match(msg)
        if m:
            event = "no_pref" if m.group("kind") == "an additional" else "boundary_no_pref"
            return ParseResult(event=event, attr=m.group("attr"))
        if RE_ASKME.match(msg):
            return ParseResult(event="ask_prompt")
        m = RE_BUYING.match(msg)
        if m:
            return ParseResult(event="initial_buying", category=m.group("cat"),
                               constraints=[m.group("c1")])
        m = RE_BROWSING.match(msg)
        if m:
            return ParseResult(event="initial_browsing", category=m.group("cat"))
        if turn == 1:
            m = RE_OVERRIDE_INIT.match(msg)
            if m:
                return ParseResult(event="initial_override", category=m.group("cat"),
                                   constraints=[m.group("old")])
        return None
