"""Paraphrase layer for the demo's live robustness mode.

Rewrites each simulated-customer utterance into a natural variant while keeping
the catalog-derived spans intact - the same machinery as tools/robust_eval.py,
packaged for the demo server so judges can watch the stress test live.

Demo-only: nothing here is imported by the scored agent.
"""
from __future__ import annotations

import random
import re

PARA_OPEN_BUY = [
    "Hi there - I'm after {c}. The one thing I really care about: {v}.",
    "I want to buy {c}. Must have: {v}.",
    "Shopping for {c} today. Non-negotiable for me is {v}.",
    "Could you help me find {c}? It has to be {v}.",
]
PARA_OPEN_BROWSE = [
    "Hey, just browsing {c} for now, nothing specific yet.",
    "I'm window shopping in {c}. Not sure what I want.",
    "Show me what you have in {c} - I'm undecided.",
    "Thinking about {c}, but I haven't made up my mind.",
]
PARA_OPEN_OTHER = [
    "I'm after {c}. {v}",
    "Help me shop for {c}. {v}",
    "Looking around {c}. {v}",
]
PARA_REVEAL = [
    "Sure - {v}.",
    "Honestly the things that matter are {v}.",
    "OK: {v}. That's what counts.",
    "Right, {v} - that's my priority.",
]
PARA_NOPREF = [
    "No strong opinion on {a}, sorry.",
    "{a} isn't something I care about.",
    "I'm easy on {a}.",
]
PARA_BOUNDARY = [
    "No idea about {a} - you pick.",
    "I'll leave {a} up to you.",
    "Honestly, {a}? Your call.",
]
PARA_OVERRIDE = [
    "Wait - scratch that. What I actually want is {v}.",
    "Change of plan. The real requirement is {v}.",
    "Forget what I said. I need {v}.",
]
PARA_NOASK = [
    "None of those work. Ask me something specific.",
    "Not what I meant - narrow it down with a question.",
]

R_BUY = re.compile(r"^I'm looking for (.+?)\. A key requirement is: (.+)\.$", re.S)
R_BROWSE = re.compile(r"^I'm looking for (.+?), but I'm still exploring\.$", re.S)
R_OPEN = re.compile(r"^I'm looking for (.+?)\. (.+)$", re.S)
R_REVEAL = re.compile(r"^For that, what matters is: (.+)\.$", re.S)
R_NOPREF = re.compile(r"^I don't have an additional preference for (.+)\.$", re.S)
R_BOUND = re.compile(r"^I don't have a preference for (.+); please use your judgment\.$", re.S)
R_OVER = re.compile(r"^Actually, ignore my earlier preference\. What I need is: (.+)\.$", re.S)
R_NOASK = re.compile(r"^Those options are not quite right yet\.")


def paraphrase(msg: str, rng: random.Random) -> str:
    m = R_BUY.match(msg)
    if m:
        return rng.choice(PARA_OPEN_BUY).format(c=m.group(1), v=m.group(2))
    m = R_BROWSE.match(msg)
    if m:
        return rng.choice(PARA_OPEN_BROWSE).format(c=m.group(1))
    m = R_OVER.match(msg)
    if m:
        return rng.choice(PARA_OVERRIDE).format(v=m.group(1))
    m = R_REVEAL.match(msg)
    if m:
        return rng.choice(PARA_REVEAL).format(v=m.group(1).replace("; ", ", and "))
    m = R_BOUND.match(msg)
    if m:
        return rng.choice(PARA_BOUNDARY).format(a=m.group(1))
    m = R_NOPREF.match(msg)
    if m:
        return rng.choice(PARA_NOPREF).format(a=m.group(1))
    if R_NOASK.match(msg):
        return rng.choice(PARA_NOASK)
    m = R_OPEN.match(msg)
    if m:
        return rng.choice(PARA_OPEN_OTHER).format(c=m.group(1), v=m.group(2))
    return msg
