"""Shopping Copilot demo service.

NOTE: this HTTP layer is NOT part of the scored submission - the challenge is
evaluated head-lessly through evaluator/local_evaluator.py. It exists so the
agent's reasoning can be shown end-to-end in the demo video.

Run:
    uvicorn server.app:app --port 8000        (from solution/)
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent          # solution/
sys.path.insert(0, str(ROOT))

from src.agent import Agent, coarse_category          # noqa: E402
from server import simulator as sim                   # noqa: E402
from server.paraphrase import paraphrase as para_msg  # noqa: E402
import random                                          # noqa: E402

DEFAULT_CATALOG = ROOT.parent / "techjam-conversational-search" / "data" / "catalog.jsonl"
DEFAULT_DATASET = ROOT.parent / "techjam-conversational-search" / "data" / "public_set.jsonl"
CATALOG = Path(os.environ.get("TJ_CATALOG", DEFAULT_CATALOG))
DATASET = Path(os.environ.get("TJ_DATASET", DEFAULT_DATASET))

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.perf_counter()
    print(f"[boot] building indexes from {CATALOG} ...", flush=True)
    agent = Agent(str(CATALOG), enable_trace=True)
    samples = [json.loads(l) for l in DATASET.open(encoding="utf-8") if l.strip()] \
        if DATASET.exists() else []
    STATE.update(agent=agent, samples=samples,
                 sample_by_id={s["sample_id"]: s for s in samples},
                 boot_seconds=round(time.perf_counter() - t0, 2))
    print(f"[boot] ready in {STATE['boot_seconds']}s - "
          f"{len(agent.card_set)} products, {len(agent.cat_index)} categories, "
          f"{len(samples)} labeled sessions", flush=True)
    yield
    STATE.clear()


app = FastAPI(title="Shopping Copilot", lifespan=lifespan)
WEB = ROOT / "web"


# --------------------------------------------------------------------- models
class NewSession(BaseModel):
    profile: dict | None = None


class Turn(BaseModel):
    session_id: str
    message: str


class Replay(BaseModel):
    sample_id: str
    paraphrase: bool = False


# ---------------------------------------------------------------- helpers
def product_view(agent: Agent, asin: str, score=None) -> dict:
    p = agent.products.get(asin, {})
    return {
        "parent_asin": asin,
        "title": p.get("title") or asin,
        "store": p.get("store"),
        "price": p.get("price"),
        "average_rating": p.get("average_rating"),
        "rating_number": p.get("rating_number"),
        "category": coarse_category([str(v) for v in (p.get("categories") or [])]),
        "features": (p.get("features") or [])[:3],
        "score": score,
    }


def enrich(agent: Agent, recs: list[dict], scores: dict) -> list[dict]:
    return [product_view(agent, r["parent_asin"], scores.get(r["parent_asin"])) for r in recs]


DEFAULT_PROFILE = {"purchase_frequency": "3-4 prior purchases", "average_prior_rating": 4.5,
                   "rating_style": "usually positive",
                   "preference_tags": ["fit", "comfort", "durability"],
                   "summary": "Prior purchases emphasize fit, comfort, durability; "
                              "ratings are usually positive."}


# ------------------------------------------------------------------- routes
@app.get("/api/meta")
def meta():
    agent: Agent = STATE["agent"]
    results = ROOT / "results_public_set.json"
    bench = {}
    if results.exists():
        d = json.loads(results.read_text(encoding="utf-8"))
        bench = {k: d[k] for k in ("hit_rate_at_10", "mrr", "mttc", "efficiency",
                                   "recommended_technical_score", "sample_count") if k in d}
        bench["scenario_metrics"] = d.get("scenario_metrics", {})
    return {"products": len(agent.card_set), "categories": len(agent.cat_index),
            "span_index_keys": len(agent.cs_inv), "build_seconds": agent.build_seconds,
            "boot_seconds": STATE["boot_seconds"], "labeled_sessions": len(STATE["samples"]),
            "baseline": {"technical_score": 0.10671, "hit_rate_at_10": 0.125,
                         "mrr": 0.068034, "mttc": 9.81},
            "benchmark": bench}


@app.get("/api/samples")
def samples():
    agent: Agent = STATE["agent"]
    out = []
    for s in STATE["samples"]:
        t = s["ground_truth"]["parent_asin"]
        p = agent.products.get(t, {})
        out.append({"sample_id": s["sample_id"], "scenario_type": s["scenario_type"],
                    "difficulty": s.get("difficulty_bucket"),
                    "target": t, "target_title": (p.get("title") or "")[:90],
                    "category": coarse_category([str(v) for v in (p.get("categories") or [])])})
    return out


@app.post("/api/session")
def new_session(body: NewSession):
    agent: Agent = STATE["agent"]
    sid = uuid.uuid4().hex
    agent.reset(sid, body.profile or DEFAULT_PROFILE)
    return {"session_id": sid, "profile": body.profile or DEFAULT_PROFILE}


@app.post("/api/chat")
def chat(body: Turn):
    agent: Agent = STATE["agent"]
    st = agent.sessions.get(body.session_id)
    if st is None:
        raise HTTPException(404, "unknown session - create one via POST /api/session")
    turn = len(st.trace) + 1
    if turn > sim.MAX_TURNS:
        raise HTTPException(400, "session exhausted (10-turn hard limit)")
    r = agent.respond(body.session_id, body.message, turn, sim.TOP_K)
    tr = st.trace[-1] if st.trace else {}
    return {"reply": r["message"], "ask_attribute": r["ask_attribute"],
            "items": enrich(agent, r["recommendations"], tr.get("scores", {})),
            "trace": {k: v for k, v in tr.items() if k != "scores"}}


@app.post("/api/replay")
def replay(body: Replay):
    """Run one labeled session through the exact scoring protocol and return the transcript."""
    agent: Agent = STATE["agent"]
    sample = STATE["sample_by_id"].get(body.sample_id)
    if sample is None:
        raise HTTPException(404, "unknown sample_id")
    target = str(sample["ground_truth"]["parent_asin"])
    product = agent.products[target]
    card, behavior = sim.materialize(sample, product)
    eff = {**sample, "intent_card": card, "behavior": behavior}

    sid = uuid.uuid4().hex
    agent.reset(sid, sample["user_profile"])
    st = agent.sessions[sid]
    rng = random.Random("para|" + str(body.sample_id))
    disclosed, boundary_used = set(), False
    override_applied = sample["scenario_type"] != "intent_override"
    category = coarse_category([str(v) for v in (product.get("categories") or [])])
    user_message = sim.initial_message(eff, category, disclosed)

    turns, hit_turn, best_rank = [], None, None
    for turn in range(1, sim.MAX_TURNS + 1):
        shown_message = para_msg(user_message, rng) if body.paraphrase else user_message
        r = agent.respond(sid, shown_message, turn, sim.TOP_K)
        tr = dict(st.trace[-1])
        scores = tr.pop("scores", {})
        ranked = [x["parent_asin"] for x in r["recommendations"]]
        turns.append({"turn": turn, "user": shown_message, "reply": r["message"],
                      "ask_attribute": r["ask_attribute"],
                      "items": enrich(agent, r["recommendations"], scores),
                      "trace": tr,
                      "target_rank": (ranked.index(target) + 1) if target in ranked else None,
                      "counts": override_applied})
        if override_applied and target in ranked:
            best_rank = ranked.index(target) + 1
            hit_turn = turn
            break
        if turn == sim.MAX_TURNS:
            break
        ov = eff.get("behavior", {}).get("override") or {}
        if not override_applied and turn + 1 == int(ov.get("turn", 3)):
            override_applied = True
            if ov.get("new_value"):
                disclosed.add(str(ov["new_value"]))
            user_message = str(ov.get("message", "Actually, please ignore my earlier preference."))
        else:
            user_message, boundary_used = sim.customer_reply(
                eff, r["ask_attribute"], disclosed, boundary_used)

    return {"sample_id": body.sample_id, "scenario_type": sample["scenario_type"],
            "paraphrased": body.paraphrase,
            "profile": sample["user_profile"],
            "target": product_view(agent, target),
            "hidden_card": card, "override": behavior.get("override"),
            "hit": hit_turn is not None, "first_hit_turn": hit_turn, "best_rank": best_rank,
            "reciprocal_rank": 0.0 if best_rank is None else round(1.0 / best_rank, 4),
            "turns": turns}


if WEB.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB)), name="assets")

    @app.get("/")
    def index():
        return FileResponse(str(WEB / "index.html"))
