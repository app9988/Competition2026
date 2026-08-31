"""Thin adapter implementing the official competition Agent interface.

Never raises from respond(); on internal failure it degrades to an empty but
schema-valid response so a single bad turn cannot invalidate a session.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from copilot.agent.pipeline import Pipeline
from copilot.services.catalog import CatalogService

_ROOT = Path(__file__).resolve().parents[3]
_SVC_CACHE: dict[str, CatalogService] = {}


def load_config(config_path: str | Path | None = None) -> dict:
    path = Path(config_path or os.environ.get("COPILOT_CONFIG")
                or _ROOT / "configs" / "default.json")
    with Path(path).open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def get_catalog_service(catalog_path: str | Path) -> CatalogService:
    key = str(Path(catalog_path).resolve())
    if key not in _SVC_CACHE:
        _SVC_CACHE[key] = CatalogService(catalog_path)
    return _SVC_CACHE[key]


class CompetitionAgent:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl",
                 config_path: str | Path | None = None) -> None:
        self.config = load_config(config_path)
        self.pipeline = Pipeline(get_catalog_service(catalog_path), self.config)

    def reset(self, session_id: str, user_profile: dict) -> None:
        self.pipeline.reset(session_id, user_profile)

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        try:
            return self.pipeline.respond(session_id, user_message, turn, top_k)
        except Exception as exc:  # degrade, never raise
            print(f"[agent] respond failed on turn {turn}: {exc!r}", file=sys.stderr)
            self.pipeline.last_trace = {"turn": turn, "error": repr(exc)}
            return {"message": "Let me refine that.", "ask_attribute": "other",
                    "recommendations": [],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    @property
    def last_trace(self) -> dict | None:
        return self.pipeline.last_trace


Agent = CompetitionAgent
