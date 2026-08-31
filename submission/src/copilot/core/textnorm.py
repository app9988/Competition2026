from __future__ import annotations

import re

_NORM_RE = re.compile(r"[^a-z0-9]+")
TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "some",
    "that", "the", "this", "to", "want", "with", "would", "you", "looking",
}


def norm(text: str) -> str:
    return _NORM_RE.sub(" ", text.lower()).strip()


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def query_terms(text: str, cap: int = 40) -> list[str]:
    out = []
    for tok in tokens(text):
        if len(tok) > 1 and tok not in STOPWORDS and tok not in out:
            out.append(tok)
            if len(out) >= cap:
                break
    return out
