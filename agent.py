"""Official competition entry point.

Exports the `Agent` class required by the submission rules:

    from agent import Agent
    agent = Agent(catalog_path="techjam-conversational-search/data/catalog.jsonl")
    agent.reset(session_id, user_profile)
    agent.respond(session_id, user_message, turn, top_k)

Standard library only; no network access.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shopping-copilot" / "src"))

from copilot.agent.competition_agent import CompetitionAgent as Agent  # noqa: E402,F401
