"""B-mode stress test: controlled paraphrasing of simulator messages.

Level 1 rewrites the template skeleton but keeps constraint payloads verbatim.
Level 2 additionally perturbs constraint text (token dropout + separator
changes), breaking exact-substring matching on purpose.
Deterministic per (session, turn) so runs are reproducible.
"""
from __future__ import annotations

import random
import re

RE_BUYING = re.compile(r"^I'm looking for (?P<cat>.+?)\. A key requirement is: (?P<c1>.+)\.$")
RE_BROWSING = re.compile(r"^I'm looking for (?P<cat>.+?), but I'm still exploring\.$")
RE_OVERRIDE = re.compile(r"^Actually, ignore my earlier preference\. What I need is: (?P<new>.+)\.$")
RE_REVEAL = re.compile(r"^For that, what matters is: (?P<body>.+)\.$")
RE_NOPREF_ADD = re.compile(r"^I don't have an additional preference for (?P<attr>\w+)\.$")
RE_NOPREF_BOUND = re.compile(r"^I don't have a preference for (?P<attr>\w+); please use your judgment\.$")
RE_OVERRIDE_INIT = re.compile(r"^I'm looking for (?P<cat>.+?)\. (?P<old>.+)$")

BUYING_TPL = [
    "I want {cat}. It must have: {c1}.",
    "Searching for {cat} - my key requirement is {c1}.",
    "I need {cat} and one thing really matters: {c1}.",
]
BROWSING_TPL = [
    "I want {cat} but I'm just browsing for now.",
    "Show me some {cat}, still exploring my options.",
    "Thinking about {cat}, nothing specific yet.",
]
OVERRIDE_TPL = [
    "Actually forget what I said before - what I need is {new}.",
    "Changed my mind, ignore that. Now I need: {new}.",
    "Scratch my earlier preference, it must be: {new}.",
]
REVEAL_TPL = [
    "What matters to me here: {body}.",
    "Honestly I mostly care about {body}.",
    "The important things are {body}.",
]
NOPREF_TPL = [
    "No more preferences about {attr} really.",
    "Nothing else on {attr}, I don't care about that.",
]
BOUND_TPL = [
    "No preference on {attr} - you decide, up to you.",
    "I really don't care about {attr}, your judgment please.",
]
OVERRIDE_INIT_TPL = [
    "I want {cat}. {old}",
    "Searching for {cat}. {old}",
]


def _dropout(text: str, rng: random.Random, p: float = 0.25) -> str:
    words = text.split()
    if len(words) <= 2:
        return text
    kept = [w for w in words if rng.random() > p]
    if len(kept) < max(2, int(0.6 * len(words))):
        kept = words[: max(2, int(0.6 * len(words)))]
    return " ".join(kept)


def paraphrase(message: str, level: int, rng: random.Random) -> str:
    if level <= 0:
        return message

    def payload(text: str) -> str:
        return _dropout(text, rng) if level >= 2 else text

    m = RE_BUYING.match(message)
    if m:
        return rng.choice(BUYING_TPL).format(cat=m.group("cat"), c1=payload(m.group("c1")))
    m = RE_BROWSING.match(message)
    if m:
        return rng.choice(BROWSING_TPL).format(cat=m.group("cat"))
    m = RE_OVERRIDE.match(message)
    if m:
        return rng.choice(OVERRIDE_TPL).format(new=payload(m.group("new")))
    m = RE_REVEAL.match(message)
    if m:
        parts = [payload(p) for p in m.group("body").split("; ")]
        sep = "; " if level < 2 else rng.choice(["; ", ", and ", " plus "])
        return rng.choice(REVEAL_TPL).format(body=sep.join(parts))
    m = RE_NOPREF_ADD.match(message)
    if m:
        return rng.choice(NOPREF_TPL).format(attr=m.group("attr"))
    m = RE_NOPREF_BOUND.match(message)
    if m:
        return rng.choice(BOUND_TPL).format(attr=m.group("attr"))
    m = RE_OVERRIDE_INIT.match(message)
    if m:
        return rng.choice(OVERRIDE_INIT_TPL).format(cat=m.group("cat"), old=m.group("old"))
    return message
