"""Portable TechJam Agent entry point."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from copilot.agent.competition_agent import CompetitionAgent as Agent  # noqa: E402

__all__ = ["Agent"]
