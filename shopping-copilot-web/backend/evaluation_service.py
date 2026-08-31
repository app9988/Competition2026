"""Presentation adapter over the stable Shopping Copilot public interface.

This module owns Web-oriented report shapes and background jobs.  It never
imports algorithm internals; all catalog, dialogue and evaluation operations
cross :mod:`copilot.public_api`.
"""
from __future__ import annotations

import csv
import math
import sys
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = APP_ROOT.parent.resolve()
CORE_ROOT = (WORKSPACE / "shopping-copilot").resolve()
KIT_ROOT = (WORKSPACE / "techjam-conversational-search").resolve()
RUNS_ROOT = (CORE_ROOT / "runs").resolve()
DEFAULT_CONFIG = (CORE_ROOT / "configs" / "default.json").resolve()

core_source = str(CORE_ROOT / "src")
if core_source not in sys.path:
    sys.path.insert(0, core_source)

from copilot.public_api import ShoppingCopilotRuntime  # noqa: E402


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def session_score(hit: bool, rank: int | None, turns: int) -> dict[str, float]:
    reciprocal = 0.0 if not rank else 1.0 / rank
    efficiency = max(0.0, min(1.0, (11.0 - turns) / 10.0))
    score = 0.50 * float(hit) + 0.30 * reciprocal + 0.20 * efficiency
    return {
        "hit": float(hit),
        "reciprocalRank": round(reciprocal, 4),
        "efficiency": round(efficiency, 4),
        "score": round(score, 4),
    }


class EvaluationService:
    """Lazy process-local owner of the public algorithm runtime."""

    def __init__(self) -> None:
        self._load_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._ready = False
        self._loading = False
        self._error = ""
        self._phase = "idle"
        self._progress = 0
        self._message = "Waiting to build the catalog index"
        self._started_at: float | None = None
        self._finished_at: float | None = None
        self.runtime = ShoppingCopilotRuntime(
            catalog_path=KIT_ROOT / "data" / "catalog.jsonl",
            public_set_path=KIT_ROOT / "data" / "public_set.jsonl",
            config_path=DEFAULT_CONFIG,
            toolkit_root=KIT_ROOT,
            runs_root=RUNS_ROOT,
        )

    @property
    def status(self) -> dict[str, Any]:
        with self._status_lock:
            elapsed = (
                0.0
                if self._started_at is None
                else (self._finished_at or time.monotonic()) - self._started_at
            )
            return {
                "ready": self._ready,
                "loading": self._loading,
                "error": self._error,
                "phase": self._phase,
                "progress": self._progress,
                "message": self._message,
                "elapsedSeconds": round(elapsed, 1),
                "interfaceVersion": self.runtime.interface_version,
            }

    def _set_status(self, **changes: Any) -> None:
        with self._status_lock:
            for name, value in changes.items():
                setattr(self, f"_{name}", value)

    def _on_build_progress(self, phase: str, progress: int, message: str) -> None:
        self._set_status(phase=phase, progress=progress, message=message)

    def start_loading(self) -> None:
        with self._status_lock:
            if self._ready or self._loading:
                return
            self._loading = True
            self._phase = "starting"
            self._progress = 2
            self._message = "Starting the in-memory catalog builder"
            self._started_at = time.monotonic()
            self._finished_at = None
        threading.Thread(
            target=self.ensure_ready,
            daemon=True,
            name="catalog-loader",
        ).start()

    def ensure_ready(self) -> None:
        if self._ready:
            return
        with self._load_lock:
            if self._ready:
                return
            if not self._loading:
                self._set_status(
                    loading=True,
                    phase="starting",
                    progress=2,
                    message="Starting the in-memory catalog builder",
                    started_at=time.monotonic(),
                )
            self._set_status(error="")
            try:
                self.runtime.build(self._on_build_progress)
                self._set_status(
                    ready=True,
                    phase="ready",
                    progress=100,
                    message="Catalog index is ready",
                    finished_at=time.monotonic(),
                )
            except Exception as exc:  # pragma: no cover - surfaced through HTTP
                self._set_status(
                    error=repr(exc),
                    phase="error",
                    message="The catalog index could not be built",
                    finished_at=time.monotonic(),
                )
            finally:
                self._set_status(loading=False)

    def require_ready(self) -> None:
        if not self._ready:
            raise RuntimeError("Catalog index is still building")

    def list_samples(self) -> list[dict[str, Any]]:
        self.require_ready()
        return self.runtime.list_samples()

    def run_single(self, sample_id: str, paraphrase_level: int = 0) -> dict[str, Any]:
        self.require_ready()
        return self.runtime.run_single(sample_id, paraphrase_level)

    def best_completed_run(self) -> dict[str, Any] | None:
        self.require_ready()
        summary = self.runtime.best_completed_summary()
        return None if summary is None else self.report_view(summary)

    def report_view(self, summary: dict[str, Any]) -> dict[str, Any]:
        self.require_ready()
        run_dir = Path(str(summary.get("run_dir") or ""))
        session_rows = self._read_csv(run_dir / "per_session.csv")
        metadata = self.runtime.sample_metadata()
        results: list[dict[str, Any]] = []
        for raw in session_rows:
            sample_id = str(raw.get("sample_id", ""))
            meta = metadata.get(sample_id, {})
            hit = _is_true(raw.get("hit"))
            rank = _as_int(raw.get("best_rank")) or None
            turns = _as_int(raw.get("turns_used"), 10)
            score = session_score(hit, rank, turns)
            asin = meta.get("target", "")
            product = self.runtime.product_view(asin)
            results.append(
                {
                    "status": "Pass" if hit else "Miss",
                    "sampleId": sample_id,
                    "scenario": raw.get("scenario", "-"),
                    "category": meta.get("category", "-"),
                    "difficulty": meta.get("difficulty", "-"),
                    "turn": turns,
                    "rank": rank,
                    "hit": hit,
                    "reciprocalRank": score["reciprocalRank"],
                    "efficiency": score["efficiency"],
                    "loopScore": score["score"],
                    "targetAsin": asin,
                    "title": product["title"],
                }
            )

        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in results:
            grouped[str(row["scenario"])].append(row)
        scenarios = []
        summary_scenarios = summary.get("scenario_metrics", {})
        for name, rows in sorted(grouped.items()):
            metrics = summary_scenarios.get(name, {})
            scenarios.append(
                {
                    "name": name,
                    "sampleCount": len(rows),
                    "hitRate": round(_as_float(metrics.get("hit_rate_at_10")), 4),
                    "mrr": round(_as_float(metrics.get("mrr")), 4),
                    "mttc": round(_as_float(metrics.get("mttc")), 4),
                    "rank1": sum(row["rank"] == 1 for row in rows),
                    "loopScore": round(
                        sum(row["loopScore"] for row in rows) / len(rows), 4
                    ),
                }
            )

        link_views = self._link_views(
            summary.get("link_metrics", {}), _as_float(summary.get("efficiency"))
        )
        rank1 = sum(row["rank"] == 1 for row in results)
        weak = sum(row["loopScore"] < 0.9 for row in results)
        created = (
            datetime.fromtimestamp(run_dir.stat().st_mtime).isoformat(timespec="seconds")
            if run_dir.exists()
            else ""
        )
        return {
            "summary": {
                "technicalScore": round(_as_float(summary.get("technical_score")), 6),
                "hitRate": round(_as_float(summary.get("hit_rate_at_10")), 6),
                "mrr": round(_as_float(summary.get("mrr")), 6),
                "mttc": round(_as_float(summary.get("mttc")), 4),
                "efficiency": round(_as_float(summary.get("efficiency")), 6),
                "sampleCount": len(results),
                "rank1": rank1,
                "weak": weak,
                "elapsedSeconds": _as_float(summary.get("elapsed_seconds")),
                "config": "default.json",
                "paraphraseLevel": _as_int(summary.get("paraphrase_level")),
                "runDir": str(run_dir),
                "createdAt": created,
            },
            "links": link_views,
            "scenarios": scenarios,
            "results": results,
        }

    @staticmethod
    def _link_views(metrics: dict[str, dict], efficiency: float) -> list[dict[str, Any]]:
        l1 = metrics.get("L1_parsing", {})
        l2 = metrics.get("L2_routing", {})
        l3b = metrics.get("L3_belief", {})
        l3 = metrics.get("L3_recall", {})
        l4 = metrics.get("L4_ranking", {})
        l5 = metrics.get("L5_asking", {})
        l6 = metrics.get("L6_session", {})
        specs = [
            (
                "L1",
                "Parsing",
                (
                    _as_float(l1.get("constraint_parse_recall"))
                    + _as_float(
                        l1.get("parser_coverage"), _as_float(l1.get("template_hit_rate"))
                    )
                )
                / 2,
                l1,
            ),
            (
                "L2",
                "Dialogue state",
                (
                    _as_float(l2.get("turn1_route_accuracy"))
                    + _as_float(l2.get("override_detected_rate"), 1.0)
                )
                / 2,
                l2,
            ),
            (
                "L3",
                "Belief update",
                _as_float(l3b.get("target_in_belief_top10")),
                l3b,
            ),
            (
                "L4",
                "Retrieval",
                sum(
                    _as_float(l3.get(key))
                    for key in (
                        "target_in_category_pool_t1",
                        "target_in_cascade_pool",
                        "target_in_candidates",
                    )
                )
                / 3,
                l3,
            ),
            ("L5", "Ranking", _as_float(l4.get("rank_le10_rate")), l4),
            (
                "L6",
                "Ask policy",
                (
                    1.0
                    - _as_float(l5.get("wasted_ask_rate"))
                    + min(1.0, _as_float(l5.get("info_constraints_per_ask")) / 2.0)
                )
                / 2,
                l5,
            ),
            ("L7", "Exposure & session", max(0.0, min(1.0, efficiency)), l6),
        ]
        return [
            {
                "id": identifier,
                "name": name,
                "score": round(score, 4),
                "healthy": score >= 0.75,
                "metrics": [
                    {
                        "name": key,
                        "value": round(value, 4) if isinstance(value, float) else value,
                    }
                    for key, value in raw.items()
                ],
            }
            for identifier, name, score, raw in specs
        ]

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as handle:
            return list(csv.DictReader(handle))


class EvaluationJobs:
    """Small in-memory job registry for progress polling from the browser."""

    def __init__(self, service: EvaluationService) -> None:
        self.service = service
        self._lock = threading.Lock()
        self.jobs: dict[str, dict[str, Any]] = {}

    def create(self, paraphrase_level: int, limit: int) -> dict[str, Any]:
        self.service.require_ready()
        safe_limit = max(1, min(200, int(limit or 200)))
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self.jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "current": 0,
                "total": safe_limit,
                "startedAt": time.time(),
                "elapsedSeconds": 0.0,
                "error": "",
                "report": None,
            }
        threading.Thread(
            target=self._run,
            args=(job_id, paraphrase_level, safe_limit),
            daemon=True,
            name=f"eval-{job_id}",
        ).start()
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            row = dict(self.jobs[job_id])
        row["elapsedSeconds"] = round(time.time() - row["startedAt"], 1)
        return row

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            self.jobs[job_id].update(changes)

    def _run(self, job_id: str, paraphrase_level: int, limit: int) -> None:
        self._update(job_id, status="running")
        try:
            summary = self.service.runtime.run_evaluation(
                limit=limit,
                paraphrase_level=paraphrase_level,
                progress=lambda current, total: self._update(
                    job_id, current=current, total=total
                ),
            )
            report = self.service.report_view(summary)
            self._update(job_id, status="completed", current=limit, report=report)
        except Exception as exc:  # pragma: no cover - surfaced through HTTP
            self._update(job_id, status="failed", error=repr(exc))


service = EvaluationService()
jobs = EvaluationJobs(service)
