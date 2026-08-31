"""Tiered routing: try each configured parser in order, first success wins."""
from __future__ import annotations

from copilot.core.registry import build, register
from copilot.core.types import ParseResult


@register("router", "rule")
class RuleRouter:
    def __init__(self, parser_names: list[str]) -> None:
        self.parsers = [(name, build("parser", name)) for name in parser_names]

    def parse(self, message: str, turn: int) -> ParseResult:
        for name, parser in self.parsers:
            result = parser.parse(message, turn)
            if result is not None and result.event != "unknown":
                return result
        return ParseResult(event="unknown", parser="none", confidence=0.0)
