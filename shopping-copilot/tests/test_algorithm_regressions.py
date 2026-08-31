from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copilot.algo.dialog.belief import candidate_belief, semantic_match_count  # noqa: E402
from copilot.algo.parsing.fuzzy_parser import FuzzyParser  # noqa: E402
from copilot.algo.retrieval.constraint_matcher import ConstraintMatcher  # noqa: E402
from copilot.core.types import Observation, SessionState, Slot  # noqa: E402


class FuzzyParserRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = FuzzyParser()

    def test_hyphenated_category_is_not_truncated(self) -> None:
        result = self.parser.parse(
            "Thinking about Shoes Loafers & Slip-Ons, nothing specific yet.", 1
        )
        self.assertEqual("Shoes Loafers & Slip-Ons", result.category)
        self.assertEqual("initial_browsing", result.event)

    def test_paraphrased_initial_override_keeps_its_route(self) -> None:
        result = self.parser.parse(
            "I want Shoes Loafers & Slip-Ons. A previously preferred soft feature", 1
        )
        self.assertEqual("initial_override", result.event)

    def test_internal_colon_does_not_drop_an_earlier_constraint(self) -> None:
        result = self.parser.parse(
            "The important things are Cowhide Sole,Hand-Sewn Loafers for Women, "
            "and Leather Loafers Women:can bend in 360 degrees.",
            3,
        )
        self.assertEqual(2, len(result.constraints))
        self.assertTrue(result.constraints[0].startswith("Cowhide Sole"))


class BeliefRegressionTests(unittest.TestCase):
    def test_raw_case_variants_remain_separately_revealable(self) -> None:
        service = SimpleNamespace(cards={
            "target": (
                ["cotton", "color: black", "Cotton", "Imported"],
                ["material", "color", "material", "feature"],
            )
        })
        state = SessionState(session_id="s", profile={})
        state.observations = [
            Observation("initial_buying", ("cotton",), None, 1),
            Observation("reveal", ("color: black", "Cotton"), "other", 2),
        ]
        self.assertAlmostEqual(1.0, candidate_belief("target", state, service))

    def test_semicolon_boundary_is_scored_semantically(self) -> None:
        expected = [
            "color: grey",
            "Solid colors: 100% Cotton; Heather Grey: 90% Cotton, 10% Polyester",
        ]
        parsed = [
            "color grey",
            "Solid colors 100 Cotton",
            "Heather Grey 90 Cotton 10 Polyester",
        ]
        self.assertGreater(semantic_match_count(expected, parsed), 1.9)


class CascadeRegressionTests(unittest.TestCase):
    def test_low_confidence_single_exact_hit_cannot_evict_fuzzy_target(self) -> None:
        service = SimpleNamespace(
            norm_text={
                "wrong": " red shoe ",
                "target": " red waterproof shoe ",
                "other": " blue boot ",
            },
            price={},
        )
        matcher = ConstraintMatcher(service, {
            "fuzzy_threshold": 0.6,
            "min_keep": 2,
            "min_keep_frac": 0.0,
            "filter_weight_min": 0.5,
        })
        slot = Slot.from_text("red shoe", "feature", "reveal", 2, weight=0.6)
        pool, _ = matcher.cascade(["wrong", "target", "other"], [slot])
        self.assertEqual(["wrong", "target"], pool)


if __name__ == "__main__":
    unittest.main()
