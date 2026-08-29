"""Contract & adversarial-input tests for the scored agent.

The evaluator scores an exception as a lost session (0.5 of that session's weight),
so INV-1 "respond never raises" is worth real points. These tests hammer the
public interface with inputs the simulator would never produce, and assert the
output contract holds every time.

    python tools/test_contract.py --catalog <path>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.agent import Agent                                   # noqa: E402

ALLOWED = {"category", "material", "color", "size", "style", "brand",
           "budget", "feature", "use_case", "other", None}

NASTY_MESSAGES = [
    "",                                     # empty
    " ",                                    # whitespace only
    "\n\t\r",                               # control whitespace
    "x" * 50_000,                           # very long
    "我想买一件棉质衬衫",                      # non-latin
    "🛍️👗👠",                               # emoji only
    "NULL\x00byte",                          # embedded null
    '"; DROP TABLE products; --',           # sql-ish
    "products MATCH 'a' OR 1=1",            # fts5 injection attempt
    "(((((((((((",                          # unbalanced parens -> fts5 syntax error
    "AND OR NOT NEAR",                      # fts5 reserved words
    '"unterminated quote',                  # unterminated quote
    "I'm looking for " + "レザー " * 200,      # long non-latin repeat
    "-" * 500,                              # punctuation only
    "I'm looking for . A key requirement is: .",   # empty capture groups
    "For that, what matters is: .",         # empty reveal
    "Actually, ignore my earlier preference. What I need is: .",
    "I don't have an additional preference for .",
]

NASTY_PROFILES = [
    None, {}, {"preference_tags": None}, {"preference_tags": "not-a-list"},
    {"preference_tags": [None, 123, ""]}, {"unexpected": object()},
]


def check(resp, where, top_k=10):
    assert isinstance(resp, dict), f"{where}: not a dict"
    assert isinstance(resp.get("message"), str), f"{where}: message not str"
    assert resp.get("ask_attribute") in ALLOWED, f"{where}: bad ask_attribute {resp.get('ask_attribute')!r}"
    recs = resp.get("recommendations")
    assert isinstance(recs, list), f"{where}: recommendations not a list"
    assert len(recs) <= top_k, f"{where}: {len(recs)} recommendations > top_k"
    seen = set()
    for r in recs:
        assert isinstance(r, dict) and isinstance(r.get("parent_asin"), str), f"{where}: bad rec {r!r}"
        assert r["parent_asin"] not in seen, f"{where}: duplicate {r['parent_asin']}"
        seen.add(r["parent_asin"])
    u = resp.get("usage")
    if u is not None:
        assert isinstance(u.get("prompt_tokens"), int) and u["prompt_tokens"] >= 0, f"{where}: bad usage"
        assert isinstance(u.get("completion_tokens"), int) and u["completion_tokens"] >= 0, f"{where}: bad usage"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    args = ap.parse_args()

    print("building index ...", flush=True)
    agent = Agent(args.catalog)
    valid = set(agent.card_set)
    print(f"ready ({agent.build_seconds}s)\n")

    n = 0
    print("1. adversarial messages")
    for i, msg in enumerate(NASTY_MESSAGES):
        agent.reset(f"nasty_{i}", {"preference_tags": ["fit"]})
        for turn in range(1, 4):
            resp = agent.respond(f"nasty_{i}", msg, turn, 10)
            check(resp, f"msg[{i}] turn{turn}")
            for r in resp["recommendations"]:
                assert r["parent_asin"] in valid, f"msg[{i}]: {r['parent_asin']} not in catalog"
            n += 1
    print(f"   {len(NASTY_MESSAGES)} messages x 3 turns -> OK")

    print("2. malformed profiles")
    for i, prof in enumerate(NASTY_PROFILES):
        agent.reset(f"prof_{i}", prof)
        resp = agent.respond(f"prof_{i}", "I'm looking for Shoes Sandals, but I'm still exploring.", 1, 10)
        check(resp, f"profile[{i}]")
        n += 1
    print(f"   {len(NASTY_PROFILES)} profiles -> OK")

    print("3. protocol abuse")
    agent.reset("abuse", {})
    check(agent.respond("abuse", "hello", 0, 10), "turn=0"); n += 1
    check(agent.respond("abuse", "hello", 999, 10), "turn=999"); n += 1
    check(agent.respond("abuse", "hello", 1, 0), "top_k=0", top_k=0); n += 1
    check(agent.respond("abuse", "hello", 1, 3), "top_k=3", top_k=3); n += 1
    check(agent.respond("never_reset_" + "z" * 20, "hello", 1, 10), "respond before reset"); n += 1
    print("   turn=0 / turn=999 / top_k=0 / top_k=3 / no-reset -> OK")

    print("4. determinism")
    a = [agent.respond("det_a", "I'm looking for Shoes Sandals. A key requirement is: leather.", 1, 10)
         for _ in range(1) for _ in [agent.reset("det_a", {})]]
    agent.reset("det_b", {})
    b = agent.respond("det_b", "I'm looking for Shoes Sandals. A key requirement is: leather.", 1, 10)
    assert [r["parent_asin"] for r in a[0]["recommendations"]] == \
           [r["parent_asin"] for r in b["recommendations"]], "non-deterministic output"
    n += 2
    print("   identical input -> identical ranking -> OK")

    print(f"\nALL CONTRACT TESTS PASSED  ({n} respond() calls, 0 exceptions)")


if __name__ == "__main__":
    main()
