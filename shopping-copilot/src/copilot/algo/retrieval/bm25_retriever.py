"""Stage C: lexical channel over the cached FTS5 index (independent of A/B)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

BM25_WEIGHTS = (0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0)


class BM25Retriever:
    def __init__(self, db_path: str | Path) -> None:
        self.connection = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True,
                                          check_same_thread=False)

    def search(self, terms: list[str], top: int) -> list[str]:
        if not terms:
            return []
        expression = " OR ".join(f'"{t}"' for t in terms)
        try:
            rows = self.connection.execute(
                "SELECT parent_asin FROM products WHERE products MATCH ? "
                f"ORDER BY bm25(products, {', '.join(str(w) for w in BM25_WEIGHTS)}) LIMIT ?",
                (expression, top),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [str(r[0]) for r in rows]
