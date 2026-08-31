"""Stable public interface for applications embedding Shopping Copilot.

UI and transport layers should import only this module.  The implementation
details of parsing, routing, retrieval, ranking and dialogue management remain
behind :class:`ShoppingCopilotRuntime`.
"""
from __future__ import annotations

import json
import math
import random
import sys
import threading
from pathlib import Path
from typing import Any, Callable


ProgressCallback = Callable[[str, int, str], None]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _session_score(hit: bool, rank: int | None, turns: int) -> dict[str, float]:
    reciprocal = 0.0 if not rank else 1.0 / rank
    efficiency = max(0.0, min(1.0, (11.0 - turns) / 10.0))
    score = 0.50 * float(hit) + 0.30 * reciprocal + 0.20 * efficiency
    return {
        "hit": float(hit),
        "reciprocalRank": round(reciprocal, 4),
        "efficiency": round(efficiency, 4),
        "score": round(score, 4),
    }


ROUTE_EXPECT = {
    "buying": "initial_buying",
    "browsing": "initial_browsing",
    "boundary": "initial_browsing",
    "intent_override": "initial_override",
}


class ShoppingCopilotRuntime:
    """Owns catalog indexes and exposes JSON-friendly algorithm operations.

    Paths are supplied by the host application, so the algorithm package has no
    knowledge of the Web project's location or framework.
    """

    interface_version = "1.0"

    def __init__(
        self,
        *,
        catalog_path: str | Path,
        public_set_path: str | Path,
        config_path: str | Path,
        toolkit_root: str | Path,
        runs_root: str | Path,
    ) -> None:
        self.catalog_path = Path(catalog_path).resolve()
        self.public_set_path = Path(public_set_path).resolve()
        self.config_path = Path(config_path).resolve()
        self.toolkit_root = Path(toolkit_root).resolve()
        self.runs_root = Path(runs_root).resolve()

        self._build_lock = threading.Lock()
        self._agent_lock = threading.Lock()
        self._ready = False
        self.agent: Any = None
        self.ev: Any = None
        self.catalog_ids: set[str] = set()
        self.categories: dict[str, Any] = {}
        self.products: dict[str, dict] = {}
        self.samples: list[dict] = []
        self.sample_map: dict[str, dict] = {}

    @property
    def ready(self) -> bool:
        return self._ready

    def build(self, progress: ProgressCallback | None = None) -> None:
        """Build all in-memory indexes once, reporting coarse build phases."""
        if self._ready:
            return
        notify = progress or (lambda _phase, _percent, _message: None)
        with self._build_lock:
            if self._ready:
                return

            toolkit_value = str(self.toolkit_root)
            if toolkit_value not in sys.path:
                sys.path.insert(0, toolkit_value)

            notify("preparing", 5, "Preparing catalog and evaluation resources")
            from copilot.agent.competition_agent import CompetitionAgent
            from evaluator import local_evaluator as ev

            notify("algorithm_index", 18, "Building retrieval and ranking indexes")
            self.agent = CompetitionAgent(str(self.catalog_path), str(self.config_path))

            notify("catalog_index", 76, "Indexing product metadata and categories")
            self.ev = ev
            self.catalog_ids, self.categories, self.products = ev.catalog_index(
                str(self.catalog_path)
            )

            notify("sessions", 92, "Loading public evaluation sessions")
            self.samples = ev.load_jsonl(str(self.public_set_path))
            self.sample_map = {str(row["sample_id"]): row for row in self.samples}
            self._ready = True
            notify("ready", 100, "Catalog index is ready")

    def _require_ready(self) -> None:
        if not self._ready:
            raise RuntimeError("Shopping Copilot indexes are not ready")

    def list_samples(self) -> list[dict[str, Any]]:
        self._require_ready()
        return [
            {
                "id": sample["sample_id"],
                "scenario": sample["scenario_type"],
                "category": sample.get("category_bucket", "-"),
                "difficulty": sample.get("difficulty_bucket", "-"),
                "targetAsin": sample["ground_truth"]["parent_asin"],
                "profile": sample.get("user_profile", {}).get("summary", ""),
            }
            for sample in self.samples
        ]

    def sample_metadata(self) -> dict[str, dict[str, str]]:
        self._require_ready()
        return {
            sample_id: {
                "difficulty": str(row.get("difficulty_bucket", "-")),
                "category": str(row.get("category_bucket", "-")),
                "target": str(row["ground_truth"]["parent_asin"]),
            }
            for sample_id, row in self.sample_map.items()
        }

    def product_view(self, asin: str) -> dict[str, Any]:
        self._require_ready()
        product = self.products.get(asin) or {}
        return {
            "asin": asin,
            "title": str(product.get("title") or asin)[:160],
            "price": product.get("price"),
            "rating": product.get("average_rating"),
            "ratingCount": product.get("rating_number"),
            "store": str(product.get("store") or "")[:60],
        }

    def run_single(self, sample_id: str, paraphrase_level: int = 0) -> dict[str, Any]:
        """Run one official simulator session and return its observable trace."""
        self._require_ready()
        sample = self.sample_map.get(sample_id)
        if sample is None:
            raise KeyError(f"Unknown sample_id: {sample_id}")

        from copilot.algo.dialog.belief import semantic_match_count
        from copilot.core.textnorm import norm
        from copilot.eval.paraphraser import paraphrase

        with self._agent_lock:
            rng = random.Random(f"ui:{sample_id}:{paraphrase_level}")
            session_id = f"api_{random.getrandbits(96):024x}"
            target = str(sample["ground_truth"]["parent_asin"])
            card, behavior = self.ev.materialize_hidden_fields(sample, self.products)
            effective = {**sample, "intent_card": card, "behavior": behavior}
            disclosed: set[str] = set()
            boundary_used = False
            override_applied = sample["scenario_type"] != "intent_override"
            self.agent.reset(session_id, sample["user_profile"])
            next_message = self.ev.initial_message(
                effective,
                self.ev.coarse_category(self.categories.get(target, [])),
                disclosed,
            )
            expected_next = list(disclosed)
            transcript: list[dict[str, Any]] = []
            best_rank: int | None = None
            hit_turn: int | None = None

            for turn in range(1, self.ev.MAX_TURNS + 1):
                user_message = paraphrase(next_message, paraphrase_level, rng)
                response = self.agent.respond(session_id, user_message, turn, self.ev.TOP_K)
                ranked = self.ev.normalize_recommendations(
                    response.get("recommendations"), self.catalog_ids
                )
                trace = self.agent.last_trace or {}
                full_ranked = trace.get("ranked") or []
                target_rank = full_ranked.index(target) + 1 if target in full_ranked else None
                expected_norms = [norm(str(value)) for value in expected_next]
                parsed_norms = list(
                    trace.get("parsed_constraints") or trace.get("slots_added") or []
                )
                matched = semantic_match_count(expected_norms, parsed_norms)
                cat_set = trace.get("cat_pool_set")
                cascade_set = trace.get("cascade_pool_set")
                hit = override_applied and target in ranked
                if hit:
                    best_rank = ranked.index(target) + 1
                    hit_turn = turn

                products = []
                for index, asin in enumerate(ranked):
                    view = self.product_view(asin)
                    view.update({"rank": index + 1, "isTarget": asin == target})
                    products.append(view)

                ranked_preview = []
                for index, asin in enumerate(full_ranked[:5]):
                    view = self.product_view(asin)
                    view.update({"rank": index + 1, "isTarget": asin == target})
                    ranked_preview.append(view)

                state = self.agent.pipeline.sessions.get(session_id)
                slots = [
                    {
                        "type": slot.stype,
                        "value": slot.value[:72],
                        "weight": round(slot.weight, 2),
                        "source": slot.source,
                    }
                    for slot in (state.slots if state else [])
                ]
                transcript.append(
                    {
                        "turn": turn,
                        "userMessage": user_message,
                        "agentMessage": response.get("message", ""),
                        "askAttribute": response.get("ask_attribute"),
                        "event": trace.get("event", ""),
                        "parser": trace.get("parser", ""),
                        "routeCorrect": (
                            trace.get("event") == ROUTE_EXPECT.get(sample["scenario_type"])
                            if turn == 1
                            else None
                        ),
                        "catPool": trace.get("cat_pool", 0),
                        "targetInCategory": target in cat_set if cat_set is not None else True,
                        "cascadePool": trace.get("cascade_pool", 0),
                        "targetInCascade": target in cascade_set if cascade_set is not None else True,
                        "targetRank": target_rank,
                        "shownRank": best_rank if hit else None,
                        "gate": round(_as_float(trace.get("gate")), 4),
                        "eigMax": round(
                            max((trace.get("eig") or {}).values(), default=0.0), 4
                        ),
                        "latencyMs": round(_as_float(trace.get("latency_ms")), 1),
                        "expectedConstraints": len(expected_next),
                        "parsedConstraints": matched,
                        "slots": slots,
                        "products": products,
                        "rankedPreview": ranked_preview,
                        "hit": hit,
                    }
                )
                if hit or turn == self.ev.MAX_TURNS:
                    break

                override = effective.get("behavior", {}).get("override") or {}
                if not override_applied and turn + 1 == int(override.get("turn", 3)):
                    override_applied = True
                    new_value = str(override.get("new_value", ""))
                    if new_value:
                        disclosed.add(new_value)
                    next_message = str(override.get("message", ""))
                    expected_next = [new_value] if new_value else []
                else:
                    before = set(disclosed)
                    next_message, boundary_used = self.ev.customer_reply(
                        effective,
                        response.get("ask_attribute"),
                        disclosed,
                        boundary_used,
                    )
                    expected_next = sorted(disclosed - before)

        turns_used = hit_turn or self.ev.MAX_TURNS
        score = _session_score(hit_turn is not None, best_rank, turns_used)
        expected_total = sum(row["expectedConstraints"] for row in transcript)
        parsed_total = sum(row["parsedConstraints"] for row in transcript)
        parse_recall = 1.0 if expected_total == 0 else parsed_total / expected_total
        route_score = float(transcript[0]["routeCorrect"] is not False)
        recall_score = sum(float(row["targetInCascade"]) for row in transcript) / len(transcript)
        rank_score = 0.0 if not best_rank else 1.0 / best_rank
        gate_score = sum(row["gate"] for row in transcript) / len(transcript)
        latency_mean = sum(row["latencyMs"] for row in transcript) / len(transcript)
        fallback = transcript[-1]["products"][0]["asin"] if transcript[-1]["products"] else target
        selected = self.product_view(target if hit_turn else fallback)
        selected.update({"rank": best_rank, "isTarget": bool(hit_turn)})
        # The public interface owns session lifecycle; callers never touch the
        # pipeline's internal session dictionary and long-running Web processes
        # do not accumulate completed replay state.
        self.agent.pipeline.sessions.pop(session_id, None)
        return {
            "sample": {
                "id": sample_id,
                "scenario": sample["scenario_type"],
                "category": sample.get("category_bucket", "-"),
                "difficulty": sample.get("difficulty_bucket", "-"),
                "profile": sample.get("user_profile", {}).get("summary", ""),
                "tags": sample.get("user_profile", {}).get("preference_tags", []),
                "targetAsin": target,
            },
            "transcript": transcript,
            "selectedProduct": selected,
            "result": {
                **score,
                "hit": bool(hit_turn),
                "turns": turns_used,
                "rank": best_rank,
                "latencyMeanMs": round(latency_mean, 1),
            },
            "chainMetrics": [
                {"id": "L1", "name": "Constraint Parsing", "value": round(parse_recall, 4), "detail": f"{parsed_total}/{expected_total or 0} constraints hit"},
                {"id": "L2", "name": "Routing", "value": round(route_score, 4), "detail": transcript[0]["event"]},
                {"id": "L3", "name": "Candidate Recall", "value": round(recall_score, 4), "detail": "target retention rate"},
                {"id": "L4", "name": "Ranking", "value": round(rank_score, 4), "detail": f"final rank {best_rank or '-'}"},
                {"id": "L5", "name": "Ask Gating", "value": round(gate_score, 4), "detail": "mean gate"},
                {"id": "L6", "name": "Session Efficiency", "value": score["efficiency"], "detail": f"done in {turns_used} turns"},
            ],
        }

    def run_evaluation(
        self,
        *,
        limit: int,
        paraphrase_level: int,
        progress: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Run the instrumented evaluator with the sole production config."""
        self._require_ready()
        from copilot.eval.instrumented_runner import run

        return run(
            str(self.config_path),
            str(self.catalog_path),
            str(self.public_set_path),
            str(self.runs_root),
            limit=limit,
            tag=f"web_pp{paraphrase_level}",
            paraphrase_level=paraphrase_level,
            progress_cb=progress,
        )

    def best_completed_summary(self) -> dict[str, Any] | None:
        """Return the highest-scoring complete local run, if one exists."""
        candidates: list[tuple[float, Path, dict[str, Any]]] = []
        for summary_path in self.runs_root.glob("*/summary.json"):
            try:
                payload = json.loads(summary_path.read_text(encoding="utf-8"))
                sample_count = int(payload.get("n_sessions") or payload.get("sample_count") or 0)
                config_name = Path(str(payload.get("config") or "")).name
                if sample_count == 200 and config_name == self.config_path.name:
                    candidates.append(
                        (_as_float(payload.get("technical_score")), summary_path, payload)
                    )
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        if not candidates:
            return None
        _, path, summary = max(
            candidates, key=lambda row: (row[0], row[1].stat().st_mtime)
        )
        return {**summary, "run_dir": str(path.parent)}


__all__ = ["ShoppingCopilotRuntime"]
