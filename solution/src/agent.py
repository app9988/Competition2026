"""Shopping Copilot - conversational retrieval agent for the TechJam challenge.

Architecture (see ../../TECHJAM_SOLUTION_DESIGN.md):
  L0  offline indexes : category buckets, attribute-span sets, rare-token index, FTS5, prior
  L1  NLU             : Layer A templates -> Layer B span recovery -> Layer C lexical
  L2  dialogue state  : slot accumulation, intent override, boundary refusal, exhaustion
  L3  retrieval       : dual-track routing, pool construction, hard filter, fused scoring
  L4  ask policy      : information-gain-maximising probe sequence
  L5  emission gate   : decision-theoretic "answer or ask"

Stdlib only. No network. Runs unmodified inside the official local evaluator.

Ablation knobs (unset in submission; hard-code the defaults before submitting):
  TJ_MODE   = general | mirror                   (default: general)
  TJ_GATE   = ev | greedy | turn3 | singleton    (default: ev)
  TJ_FLOOR  = forced-emission turn               (default: 3)
  TJ_PRIOR  = pop_price | pop | logrn            (default: pop_price)
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

SEARCH_FIELDS = ("title", "features", "details", "description", "categories", "store")
MATERIAL_RE = re.compile(r"\b(cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric)\b", re.I)
COLOR_RE = re.compile(r"\b(black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange)\b", re.I)
TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
STOP = {"a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "i", "in", "is", "it",
        "me", "my", "of", "on", "or", "please", "some", "that", "the", "this", "to", "want", "with",
        "would", "you", "looking", "im", "need", "what", "matters", "key", "requirement", "still",
        "exploring", "prefer"}

# --- L3 fusion weights (module-level so tools/sweep_weights.py can perturb them) ---
W_SPAN    = 12.0   # constraint matches an indexed attribute span exactly
W_SUB     =  5.0   # constraint appears verbatim in the product copy
W_PARTIAL =  2.5   # per-unit token overlap between constraint and copy
W_SLOT0   =  6.0   # mirror mode only: constraint occupies card slot 0
W_BM25    =  0.50  # normalised BM25 rank
W_PRIOR   =  0.30  # popularity prior
W_PROFILE =  0.05  # anonymised profile tag affinity
W_PRICE   =  0.70  # prior bonus for a non-null price field

MODE = os.environ.get("TJ_MODE", "general")
GATE = os.environ.get("TJ_GATE", "ev")
FLOOR = int(os.environ.get("TJ_FLOOR", "3"))
PRIOR = os.environ.get("TJ_PRIOR", "pop_price")


# --------------------------------------------------------------- catalog view
def searchable_text(product):
    parts = []
    for field in SEARCH_FIELDS:
        value = product.get(field)
        if isinstance(value, dict):
            parts.extend(f"{k} {v}" for k, v in value.items())
        elif isinstance(value, list):
            parts.extend(str(i) for i in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts).strip()


def flatten_values(value):
    if isinstance(value, dict):
        return [f"{k}: {v}" for k, v in value.items() if v not in (None, "", [])]
    if isinstance(value, list):
        return [str(i) for i in value if i not in (None, "")]
    return [str(value)] if value not in (None, "") else []


def clean(value, limit=180):
    return re.sub(r"\s+", " ", value).strip(" -;,.\t\n")[:limit].rstrip()


def intent_card(product, limit=180):
    """Mirror-mode span set: the first four attribute slots, in catalog order."""
    title = clean(str(product.get("title") or "product"), limit)
    candidates = [*flatten_values(product.get("features")), *flatten_values(product.get("details"))]
    corpus = searchable_text(product)
    material = MATERIAL_RE.search(corpus)
    color = COLOR_RE.search(corpus)
    if material:
        candidates.insert(0, material.group(1).lower())
    if color:
        candidates.insert(1, "color: " + color.group(1).lower())
    if product.get("price") not in (None, ""):
        candidates.append("budget around $" + str(product["price"]))
    cleaned = list(dict.fromkeys(clean(i, limit) for i in candidates if clean(i, limit)))
    if not cleaned:
        cleaned = [title]
    return cleaned[:4]


def attribute_spans(product):
    """General-mode span set: every quotable attribute span of a product.

    Makes no assumption about how the customer simulator builds its intent card -
    it simply indexes what the product copy actually says.
    """
    spans = [*flatten_values(product.get("features")), *flatten_values(product.get("details"))]
    corpus = searchable_text(product)
    material = MATERIAL_RE.search(corpus)
    color = COLOR_RE.search(corpus)
    if material:
        spans.append(material.group(1).lower())
    if color:
        spans.append("color: " + color.group(1).lower())
    if product.get("price") not in (None, ""):
        spans.append("budget around $" + str(product["price"]))
    return {norm(clean(s)) for s in spans if clean(s)}


def coarse_category(values):
    excluded = {"clothing", "clothing shoes & jewelry", "clothing, shoes & jewelry"}
    cleaned = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part and part.lower() not in excluded:
                cleaned.append(part)
    return " ".join(cleaned[-2:]) if cleaned else "clothing item"


def norm(text):
    return re.sub(r"\s+", " ", str(text).lower()).strip(" -;,.")


def terms(text):
    return [t.lower() for t in TOKEN_RE.findall(text) if len(t) > 1 and t.lower() not in STOP]


# ------------------------------------------------------------- L1 Layer A NLU
P_BUY = re.compile(r"looking for (.+?)\.\s*a key requirement is:\s*(.+?)\.?\s*$", re.I | re.S)
P_BROWSE = re.compile(r"looking for (.+?),\s*but i'?m still exploring", re.I | re.S)
P_OVERRIDE = re.compile(r"ignore my earlier preference.*?what i need is:\s*(.+?)\.?\s*$", re.I | re.S)
P_OPEN = re.compile(r"looking for (.+?)\.\s*(.+?)\s*$", re.I | re.S)
P_REVEAL = re.compile(r"what matters is:\s*(.+?)\.?\s*$", re.I | re.S)
P_NOPREF = re.compile(r"don'?t have an additional preference for\s+(\w+)", re.I)
P_BOUNDARY = re.compile(r"don'?t have a preference for\s+(\w+);\s*please use your judgment", re.I)

PIVOT_RE = re.compile(r"(actually|instead|scratch that|forget|change of plan|wait)", re.I)
NOPREF_RE = re.compile(r"(no strong opinion|don'?t care|isn'?t something i care|easy on|"
                       r"your call|you pick|up to you|leave .* to you)", re.I)

ATTR_ORDER = ["other", "other", "other", "feature", "material", "style", "use_case",
              "color", "brand", "budget", "size", "category"]


class SessionState:
    def __init__(self, profile):
        self.category = None
        self.constraints = []          # normalized attribute spans, observation order
        self.slot0 = None              # primary / pivoted constraint
        self.parsed = False            # did any layer recover structure?
        self.dead = set()              # attributes known to be exhausted
        self.asked = []
        self.turn = 0
        self.no_new_info_turns = 0
        self.boundary_hit = False
        self.exhausted = False
        self.nlu_layer = "C"
        self.cat_from_recovery = False
        self.diag = {}
        self.trace = []
        self.profile = profile or {}


class Agent:
    def __init__(self, catalog_path="data/catalog.jsonl", enable_trace=False):
        self.catalog_path = Path(catalog_path)
        self.enable_trace = enable_trace
        self.products = {}             # populated only when tracing (UI needs product detail)
        self.card = {}
        self.card_set = {}
        self.cat_index = defaultdict(list)
        self.cat_set = set()
        self.cat_strings = []
        self.corpus = {}
        self.tok_index = defaultdict(set)
        self.cs_df = defaultdict(int)
        self.cs_inv = defaultdict(list)
        self.prior = {}
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.sessions = {}
        self.build_seconds = 0.0
        self._build()

    # ------------------------------------------------------------ L0 indexes
    def _build(self):
        t0 = time.perf_counter()
        cur = self.conn.cursor()
        cur.execute("CREATE VIRTUAL TABLE products USING fts5(parent_asin UNINDEXED, title,"
                    " categories, features, details, store, description,"
                    " tokenize='unicode61 remove_diacritics 2')")
        batch = []
        with self.catalog_path.open(encoding="utf-8") as fh:
            for line in fh:
                p = json.loads(line)
                a = str(p["parent_asin"])
                if self.enable_trace:
                    self.products[a] = p
                cat = coarse_category([str(v) for v in (p.get("categories") or [])])
                self.cat_index[norm(cat)].append(a)
                self.card[a] = [norm(x) for x in intent_card(p)]
                self.card_set[a] = attribute_spans(p) if MODE == "general" else set(self.card[a])
                self.corpus[a] = norm(searchable_text(p))
                rn = float(p.get("rating_number") or 0)
                ar = float(p.get("average_rating") or 0)
                base = math.log1p(rn) * ar / 5.0
                if PRIOR == "logrn":
                    base = math.log1p(rn)
                elif PRIOR == "pop_price":
                    base += W_PRICE if p.get("price") not in (None, "") else 0.0
                self.prior[a] = base
                for t in set(terms(cat)):
                    self.tok_index[t].add(a)
                batch.append((a, self._t(p.get("title")), self._t(p.get("categories")),
                              self._t(p.get("features")), self._t(p.get("details")),
                              self._t(p.get("store")), self._t(p.get("description"))))
                if len(batch) >= 2000:
                    cur.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?)", batch)
                    batch.clear()
        if batch:
            cur.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?)", batch)
        self.conn.commit()
        self._build_recovery()
        self.global_top10 = sorted(self.prior, key=lambda a: -self.prior[a])[:10]
        self.build_seconds = round(time.perf_counter() - t0, 2)

    def _build_recovery(self):
        """Layer-B index: closed category vocabulary + rare-token index over spans."""
        self.cat_strings = sorted(self.cat_index.keys(), key=len, reverse=True)
        self.cat_set = set(self.cat_index.keys())
        # loose (punctuation-free) form -> original category keys; paraphrases keep the
        # words of a category but not necessarily its "&"s and commas
        self.cat_loose = {}
        for key in self.cat_index:
            lk = " ".join(TOKEN_RE.findall(key))
            self.cat_loose.setdefault(lk, []).append(key)
        uniq = set()
        for spans in self.card_set.values():
            uniq.update(spans)
        for c in uniq:
            for t in set(terms(c)):
                self.cs_df[t] += 1
        for c in uniq:
            for t in sorted(set(terms(c)), key=lambda x: self.cs_df[x])[:3]:
                if self.cs_df[t] <= 4000:
                    self.cs_inv[t].append(c)

    @staticmethod
    def _t(v):
        if v is None:
            return ""
        if isinstance(v, dict):
            return " ".join(f"{k} {i}" for k, i in v.items())
        if isinstance(v, list):
            return " ".join(str(i) for i in v)
        return str(v)

    # ------------------------------------------------------------- public API
    def reset(self, session_id, user_profile):
        self.sessions[session_id] = SessionState(user_profile)

    def respond(self, session_id, user_message, turn, top_k):
        try:
            return self._respond(session_id, user_message, turn, top_k)
        except Exception:                       # never raise: the harness scores a throw as a miss
            return {"message": "Here are some options.",
                    "ask_attribute": "other",
                    "recommendations": [{"parent_asin": a} for a in self.global_top10[:top_k]],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    def _respond(self, session_id, user_message, turn, top_k):
        st = self.sessions.get(session_id)
        if st is None:
            self.reset(session_id, {})
            st = self.sessions[session_id]
        st.turn = turn
        t0 = time.perf_counter()
        before = len(st.constraints)
        self._ingest(st, user_message)
        if len(st.constraints) != before:
            st.no_new_info_turns = 0
        elif turn >= 2 and not st.boundary_hit:
            st.no_new_info_turns += 1
        boundary_this_turn = st.boundary_hit
        st.boundary_hit = False

        pool, ranked = self._rank(st, top_k)
        attr = self._next_ask(st)
        gated, why = self._emit(st, pool, ranked)
        shown = ranked if gated else []

        if self.enable_trace:
            st.trace.append({
                "turn": turn,
                "user_message": user_message,
                "nlu_layer": st.nlu_layer,
                "route": st.diag.get("route"),
                "category": st.category,
                "constraints": list(st.constraints),
                "new_constraints": st.constraints[before:],
                "boundary": boundary_this_turn,
                "exhausted": st.exhausted,
                "pool_catalog": len(self.card_set),
                "pool_stage1": st.diag.get("pool_stage1", 0),
                "pool_stage2": st.diag.get("pool_stage2", 0),
                "gate": gated,
                "gate_reason": why,
                "ask_attribute": attr,
                "scores": st.diag.get("scores", {}),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            })
        return {"message": self._say(attr, bool(shown)),
                "ask_attribute": attr,
                "recommendations": [{"parent_asin": a} for a in shown[:top_k]],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    # ---------------------------------------------------------------- L1 NLU
    def _ingest(self, st, msg):
        st.nlu_layer = "A"
        m = P_OVERRIDE.search(msg)
        if m:
            st.parsed = True
            st.slot0 = norm(m.group(1))
            self._add(st, m.group(1))
            return
        m = P_BOUNDARY.search(msg)
        if m:
            st.parsed = True
            st.boundary_hit = True          # scripted one-off refusal, not an exhausted slot
            return
        m = P_NOPREF.search(msg)
        if m:
            st.parsed = True
            attr = m.group(1).lower()
            st.dead.add(attr)
            if attr == "other":
                st.exhausted = True
            return
        m = P_REVEAL.search(msg)
        if m:
            st.parsed = True
            for part in m.group(1).split(";"):
                self._add(st, part)
            return
        m = P_BUY.search(msg)
        if m:
            st.parsed = True
            st.category = st.category or m.group(1).strip()
            st.slot0 = norm(m.group(2))
            self._add(st, m.group(2))
            return
        m = P_BROWSE.search(msg)
        if m:
            st.parsed = True
            st.category = st.category or m.group(1).strip()
            return
        m = P_OPEN.search(msg)
        if m:
            st.parsed = True
            st.category = st.category or m.group(1).strip()
            self._add(st, m.group(2))
            return
        st.nlu_layer = "C"
        self._ingest_fallback(st, msg)

    def _ingest_fallback(self, st, msg):
        """Layer B: template-free recovery. Survives any paraphrase that keeps the
        catalog-derived category and attribute spans intact."""
        if st.category is None:
            cat = self._recover_category(msg)
            if cat:
                st.category = cat
                st.parsed = True
                st.nlu_layer = "B"
                st.cat_from_recovery = True
        found = self._recover_constraints(msg)
        if st.category:                         # never re-ingest the category as a constraint
            found = [c for c in found if c != norm(st.category)]
        for c in found:
            self._add(st, c)
        # Closed-vocabulary fast path: material/colour words are too common for the
        # rare-token span index (df cap), yet they are the simulator's own attribute
        # vocabulary - a paraphrase like "Sure - leather." must still register.
        mm = MATERIAL_RE.search(msg)
        if mm:
            self._add(st, mm.group(1).lower())
            st.parsed = True
            if st.nlu_layer == "C":
                st.nlu_layer = "B"
        cm = COLOR_RE.search(msg)
        if cm:
            self._add(st, "color: " + cm.group(1).lower())
            st.parsed = True
            if st.nlu_layer == "C":
                st.nlu_layer = "B"
        if found:
            st.parsed = True
            st.nlu_layer = "B"
            if PIVOT_RE.search(msg):
                st.slot0 = found[0]
        if NOPREF_RE.search(msg):
            st.boundary_hit = True
            st.parsed = True
            if st.nlu_layer == "C":
                st.nlu_layer = "B"

    def _recover_category(self, msg):
        """Longest known coarse-category string appearing in the message.

        Matching is punctuation-free (loose): a trailing period or a dropped "&"
        must not break the lookup. Ambiguity (several category strings sharing
        the same loose form, or several coverage ties) resolves to the LARGEST
        bucket - recall-safest, since a too-small bucket silently excludes the
        target for the rest of the session.
        """
        lw = [t.lower() for t in TOKEN_RE.findall(msg)]
        for n in range(min(8, len(lw)), 0, -1):
            best = None
            for i in range(len(lw) - n + 1):
                gram = " ".join(lw[i:i + n])
                for key in self.cat_loose.get(gram, ()):
                    if best is None or len(self.cat_index[key]) > len(self.cat_index[best]):
                        best = key
            if best:
                return best
        mt = set(terms(msg))                    # token-coverage fallback
        if mt:
            cands = [c for c in self.cat_strings if (ct := set(terms(c))) and ct <= mt]
            if cands:
                mx = max(len(set(terms(c))) for c in cands)
                tied = [c for c in cands if len(set(terms(c))) == mx]
                return max(tied, key=lambda c: len(self.cat_index[c]))
        return None

    def _recover_constraints(self, msg):
        """Attribute spans quoted verbatim in the message (rare-token candidate generation)."""
        m = norm(msg)
        seen, out = set(), []
        for t in set(terms(m)):
            for c in self.cs_inv.get(t, ()):
                if c in seen:
                    continue
                seen.add(c)
                if len(c) >= 4 and c in m:
                    out.append(c)
        out.sort(key=len, reverse=True)
        kept = []
        for c in out:                           # drop spans subsumed by a longer match
            if not any(c in k for k in kept):
                kept.append(c)
        return kept[:4]

    @staticmethod
    def _add(st, raw):
        c = norm(raw)
        if c and c not in st.constraints:
            st.constraints.append(c)

    # ---------------------------------------------------------- L3 retrieval
    def _pool(self, st):
        pool = []
        if st.category:
            pool = self.cat_index.get(norm(st.category), [])
        if not pool and st.category:            # token-vote recovery for deformed category
            want = set(terms(st.category))
            if want:
                sc = defaultdict(int)
                for t in want:
                    for a in self.tok_index.get(t, ()):
                        sc[a] += 1
                if sc:
                    best = max(sc.values())
                    pool = [a for a, v in sc.items() if v == best]
        if not pool:
            pool = self._lexical(st, 1000)
        return pool

    def _lexical(self, st, limit=400):
        q = list(dict.fromkeys(terms(" ".join([st.category or ""] + st.constraints))))[:48]
        if not q:
            return []
        expr = " OR ".join('"' + t.replace('"', "") + '"' for t in q)
        try:
            rows = self.conn.execute(
                "SELECT parent_asin FROM products WHERE products MATCH ?"
                " ORDER BY bm25(products,0.0,6.0,4.0,2.5,2.5,1.5,1.0) LIMIT ?",
                (expr, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [str(r[0]) for r in rows]

    def _rank(self, st, top_k):
        """Returns (survivors_of_hard_filter, ranked_top_k)."""
        pool = self._pool(st)
        st.diag = {"route": "PRECISION" if st.constraints else "DISCOVERY",
                   "pool_stage1": len(pool), "pool_stage2": len(pool), "scores": {}}
        if not pool:
            return [], []
        known = st.constraints
        exact = pool
        if known:
            kset = set(known)
            exact = [a for a in pool if kset <= self.card_set[a]]
            if not exact and st.cat_from_recovery:
                # No product in this bucket satisfies every constraint AND the
                # bucket came from Layer-B recovery - the category may be wrong.
                # Re-inject lexical candidates into the SCORING pool so the true
                # target can outrank the mis-recovered bucket. The gate keeps
                # seeing an uncertain pool (exact stays empty -> fallback below),
                # so this never fabricates a false "Rank-1 certain" signal.
                pool = list(dict.fromkeys(pool + self._lexical(st, 600)))
                exact = [a for a in pool if kset <= self.card_set[a]]
            if st.slot0 and MODE == "mirror":
                s0 = [a for a in exact if self.card[a] and self.card[a][0] == st.slot0]
                if s0:
                    exact = s0
            exact = exact or pool               # never let the hard filter empty the pool
            st.diag["pool_stage2"] = len(exact)
        if not known:                           # DISCOVERY track: prior-ordered bucket
            ranked = sorted(pool, key=lambda a: (-self.prior[a], a))[:top_k]
            st.diag["scores"] = {a: round(self.prior[a], 3) for a in ranked}
            return pool, ranked

        lex_list = self._lexical(st, 300)
        lex = {a: 1.0 - i / max(len(lex_list), 1) for i, a in enumerate(lex_list)}
        tags = [norm(t) for t in (st.profile.get("preference_tags") or [])]
        scored = []
        for a in pool:
            cs, corp, cd = self.card_set[a], self.corpus[a], self.card[a]
            s = 0.0
            for c in known:
                if c in cs:
                    s += W_SPAN                 # exact attribute-span hit
                elif c in corp:
                    s += W_SUB                  # verbatim in product copy
                else:
                    ct = set(terms(c))
                    if ct:
                        s += W_PARTIAL * (sum(1 for t in ct if t in corp) / len(ct))
            if MODE == "mirror" and st.slot0 and cd and cd[0] == st.slot0:
                s += W_SLOT0
            s += W_BM25 * lex.get(a, 0.0)
            s += W_PRIOR * self.prior[a]
            s += W_PROFILE * sum(1 for t in tags if t and t in corp)
            scored.append((-s, -self.prior[a], a))
        scored.sort()
        top = [a for _, _, a in scored[:top_k]]
        st.diag["scores"] = {a: round(-neg, 3) for neg, _, a in scored[:top_k]}
        return exact, top

    # -------------------------------------------------------- L5 emission gate
    def _emit(self, st, exact, ranked):
        """Emit only when Rank-1 is near certain.

        V(t, r) = 0.50 + 0.30/r + 0.20*(11-t)/10
        Emitting now at rank r beats waiting one turn for rank 1 iff
            0.30/r + 0.02 > 0.30   <=>   r < 1.07
        i.e. only a near-certain Rank-1 is worth answering; otherwise ask.
        """
        if not ranked:
            return False, "no candidates"
        if not st.parsed:
            return True, "Layer C fallback - no further information expected"
        if GATE == "greedy":
            return True, "greedy policy"
        if GATE == "singleton":
            return len(exact) == 1, "singleton-only policy"
        if GATE == "turn3":
            return st.turn >= FLOOR, f"fixed floor {FLOOR}"
        if len(exact) == 1:
            return True, "candidate pool collapsed to 1 - Rank-1 certain"
        if st.exhausted:
            return True, "intent card exhausted - no more information available"
        if st.turn >= FLOOR:
            return True, f"turn {st.turn} >= emit floor {FLOOR} - information saturated"
        if st.turn >= 2 and st.no_new_info_turns >= 2:
            return True, "no new information for 2 turns"
        return False, f"{len(exact)} candidates remain - E[rank] > 1, asking instead of answering"

    # ------------------------------------------------------------ L4 ask policy
    def _next_ask(self, st):
        for attr in ATTR_ORDER:
            if attr in st.dead:
                continue
            if attr == "other":
                if st.asked.count("other") >= 3:
                    continue
                st.asked.append(attr)
                return attr
            if attr in st.asked:
                continue
            st.asked.append(attr)
            return attr
        return "other"

    @staticmethod
    def _say(attr, showing):
        head = ("Here are my top picks. " if showing
                else "I want to get this right before I show you a shortlist. ")
        friendly = {"other": "anything else that matters most to you",
                    "feature": "a specific feature you need",
                    "material": "a material preference",
                    "style": "a style or fit preference",
                    "use_case": "where you plan to use it",
                    "color": "a colour preference",
                    "brand": "a preferred brand",
                    "budget": "your budget",
                    "size": "your size",
                    "category": "the kind of item you have in mind"}.get(attr, attr)
        if attr is None:
            return head.strip()
        return head + "Could you tell me " + friendly + "?"
