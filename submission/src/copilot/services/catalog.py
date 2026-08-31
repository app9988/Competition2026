"""Catalog loading, derived-index building and disk caching.

Derived structures (all in memory, all pickled once):
  norm_text[asin]   normalized searchable text, padded with spaces for token checks
  coarse[asin]      normalized coarse category (same function as the simulator)
  cat_pool[cat]     asin list per normalized coarse category
  cards[asin]       (constraints, constraint_types) from the simulated intent card
  price/rating_n/rating_avg[asin]
An FTS5 BM25 index is built once into a SQLite file for the lexical channel.
"""
from __future__ import annotations

import json
import pickle
import sqlite3
from pathlib import Path

from copilot.algo.dialog.simulator_model import (
    card_constraints, coarse_category, searchable_text,
)
from copilot.core.textnorm import norm

CACHE_VERSION = 2


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


class CatalogService:
    def __init__(self, catalog_path: str | Path, cache_dir: str | Path | None = None,
                 verbose: bool = True) -> None:
        self.catalog_path = Path(catalog_path).resolve()
        root = Path(__file__).resolve().parents[3]
        self.cache_dir = Path(cache_dir) if cache_dir else root / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.pickle_path = self.cache_dir / "derived.pkl"
        self.fts_path = self.cache_dir / "fts5.db"
        self.verbose = verbose

        self.ids: set[str] = set()
        self.norm_text: dict[str, str] = {}
        self.coarse: dict[str, str] = {}
        self.cat_pool: dict[str, list[str]] = {}
        self.cards: dict[str, tuple[list[str], list[str]]] = {}
        self.price: dict[str, float] = {}
        self.rating_n: dict[str, int] = {}
        self.rating_avg: dict[str, float] = {}
        self._all_ids_sorted: list[str] = []

        if not self._load_cache():
            self._build()
        self._all_ids_sorted = sorted(self.ids)
        # normalized intent-card constraint sets, for dialogue-consistency scoring
        self.card_norms: dict[str, frozenset[str]] = {
            asin: frozenset(norm(c) for c in cons)
            for asin, (cons, _types) in self.cards.items()
        }

    # ------------------------------------------------------------------ cache
    def _cache_key(self) -> dict:
        stat = self.catalog_path.stat()
        return {"version": CACHE_VERSION, "size": stat.st_size}

    def _load_cache(self) -> bool:
        if not self.pickle_path.exists() or not self.fts_path.exists():
            return False
        try:
            with self.pickle_path.open("rb") as fh:
                blob = pickle.load(fh)
        except Exception:
            return False
        if blob.get("key") != self._cache_key():
            return False
        for name in ("ids", "norm_text", "coarse", "cat_pool", "cards",
                     "price", "rating_n", "rating_avg"):
            setattr(self, name, blob[name])
        if self.verbose:
            print(f"[catalog] cache loaded: {len(self.ids)} products")
        return True

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        if self.verbose:
            print(f"[catalog] building indexes from {self.catalog_path} ...")
        if self.fts_path.exists():
            self.fts_path.unlink()
        con = sqlite3.connect(self.fts_path)
        cur = con.cursor()
        cur.execute(
            "CREATE VIRTUAL TABLE products USING fts5("
            "parent_asin UNINDEXED, title, categories, features, details, store, description, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        batch = []
        with self.catalog_path.open(encoding="utf-8") as fh:
            for line in fh:
                p = json.loads(line)
                asin = str(p["parent_asin"])
                self.ids.add(asin)
                self.norm_text[asin] = " " + norm(searchable_text(p)) + " "
                coarse = norm(coarse_category([str(v) for v in p.get("categories") or []]))
                self.coarse[asin] = coarse
                self.cat_pool.setdefault(coarse, []).append(asin)
                self.cards[asin] = card_constraints(p)
                try:
                    if p.get("price") not in (None, ""):
                        self.price[asin] = float(p["price"])
                except (TypeError, ValueError):
                    pass
                self.rating_n[asin] = int(p.get("rating_number") or 0)
                try:
                    self.rating_avg[asin] = float(p.get("average_rating") or 0.0)
                except (TypeError, ValueError):
                    self.rating_avg[asin] = 0.0
                batch.append((asin, _text(p.get("title")), _text(p.get("categories")),
                              _text(p.get("features")), _text(p.get("details")),
                              _text(p.get("store")), _text(p.get("description"))))
                if len(batch) >= 1000:
                    cur.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            cur.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
        con.commit()
        con.close()
        with self.pickle_path.open("wb") as fh:
            pickle.dump({
                "key": self._cache_key(),
                "ids": self.ids, "norm_text": self.norm_text, "coarse": self.coarse,
                "cat_pool": self.cat_pool, "cards": self.cards, "price": self.price,
                "rating_n": self.rating_n, "rating_avg": self.rating_avg,
            }, fh, protocol=pickle.HIGHEST_PROTOCOL)
        if self.verbose:
            print(f"[catalog] built {len(self.ids)} products, "
                  f"{len(self.cat_pool)} coarse categories; cache saved")

    # ------------------------------------------------------------------ views
    def all_ids(self) -> list[str]:
        return self._all_ids_sorted
