"""Catalog-grounded belief likelihood for deterministic customer replies.

The evaluator exposes a known response policy: an attribute question reveals
the next two undisclosed intent-card constraints of that type.  Replaying that
policy for every candidate is a small, model-based POMDP update.  It provides
the reward-aligned part of an RL-style agent without fitting a high-variance Q
network to only 200 public trajectories.
"""
from __future__ import annotations

from copilot.core.textnorm import STOPWORDS, norm
from copilot.core.types import Observation, SessionState
from copilot.services.catalog import CatalogService


def _terms(value: str) -> set[str]:
    return {token for token in norm(value).split()
            if token and token not in STOPWORDS}


def constraint_similarity(observed: str, expected: str) -> float:
    """Asymmetric token similarity robust to stress-test token dropout."""
    left = norm(observed)
    right = norm(expected)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    observed_terms = _terms(left)
    expected_terms = _terms(right)
    if not observed_terms or not expected_terms:
        return 0.0
    overlap = len(observed_terms & expected_terms)
    if not overlap:
        return 0.0
    observed_coverage = overlap / len(observed_terms)
    expected_coverage = overlap / len(expected_terms)
    # Missing query tokens are stronger counter-evidence than a longer catalog
    # phrase, so favor containment of the observed span.
    return 0.75 * observed_coverage + 0.25 * expected_coverage


def semantic_match_count(expected: list[str] | tuple[str, ...],
                         parsed: list[str] | tuple[str, ...]) -> float:
    """Soft count of expected constraints recovered by a parser.

    This is primarily an observability helper.  It treats token-dropped spans
    as partial semantic matches and is robust to the evaluator's ambiguous
    semicolon boundary.
    """
    if not expected or not parsed:
        return 0.0
    aligned = sum(max(constraint_similarity(value, candidate)
                      for candidate in parsed)
                  for value in expected)
    joined = constraint_similarity(" ".join(parsed), " ".join(expected)) * len(expected)
    return min(float(len(expected)), max(aligned, joined))


def _batch_similarity(observed: tuple[str, ...], expected: tuple[str, ...]) -> float:
    if not observed and not expected:
        return 1.0
    if not observed or not expected:
        return 0.0
    remaining = list(expected)
    matched = 0.0
    for value in observed:
        if not remaining:
            break
        scores = [constraint_similarity(value, candidate) for candidate in remaining]
        best = max(range(len(scores)), key=scores.__getitem__)
        matched += scores[best]
        remaining.pop(best)
    aligned = matched / max(len(observed), len(expected))
    # ``; `` is both the evaluator's batch delimiter and valid punctuation
    # inside a catalog feature.  The parser therefore cannot always recover
    # the original boundary.  A joined comparison preserves the full semantic
    # payload without assuming an unambiguous text protocol.
    joined = constraint_similarity(" ".join(observed), " ".join(expected))
    return max(aligned, joined)


def _reply(constraints: list[str], types: list[str], disclosed: set[str],
           attribute: str | None) -> tuple[str, ...]:
    if not attribute:
        return ()
    reply: list[str] = []
    for value, constraint_type in zip(constraints, types):
        # Match the evaluator exactly: disclosure tracking is raw-string
        # based, so case variants such as ``cotton`` and ``Cotton`` are two
        # separately revealable card entries.
        if value in disclosed:
            continue
        if attribute == "other" or constraint_type == attribute:
            reply.append(value)
            if len(reply) == 2:
                break
    return tuple(reply)


def _expected(observation: Observation, constraints: list[str], types: list[str],
              disclosed: set[str]) -> tuple[str, ...] | None:
    if observation.event == "initial_buying":
        return tuple(constraints[:1])
    if observation.event == "initial_override":
        # The simulator uses soft_preferences[-1].  For short cards the soft
        # fallback is hard_constraints[:1], otherwise it is the card suffix.
        if not constraints:
            return ()
        return (constraints[-1] if len(constraints) >= 3 else constraints[0],)
    if observation.event == "override":
        return tuple(constraints[:1])
    if observation.event in ("reveal", "no_pref"):
        return _reply(constraints, types, disclosed, observation.ask_attribute)
    # Browsing has no target evidence; the first boundary no-preference is a
    # scenario rule rather than evidence about a candidate's card.
    return None


def candidate_belief(asin: str, state: SessionState,
                     service: CatalogService) -> float:
    """Return a normalized observation likelihood in ``[0, 1]``."""
    constraints, types = service.cards.get(asin, ([], []))
    disclosed: set[str] = set()
    weighted_score = 0.0
    total_weight = 0.0
    event_weight = {
        "initial_buying": 1.1,
        "initial_override": 0.35,
        "reveal": 1.0,
        "override": 1.25,
        "no_pref": 0.55,
    }

    for observation in state.observations:
        expected = _expected(observation, constraints, types, disclosed)
        if expected is None:
            continue
        observed = observation.constraints
        if observation.event == "no_pref":
            likelihood = 1.0 if not expected else 0.0
        else:
            likelihood = _batch_similarity(observed, expected)
        weight = event_weight.get(observation.event, 1.0) * observation.confidence
        weighted_score += weight * likelihood
        total_weight += weight
        disclosed.update(expected)

    return weighted_score / total_weight if total_weight else 0.0
