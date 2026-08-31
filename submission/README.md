# CompetitionAI submission bundle

- Python 3.10+; standard library only. Use `python` on Windows and `python3`
  on macOS/Linux.
- Offline at scoring time; no API keys or network services are required.
- The official catalog is not bundled. The evaluator passes its catalog path
  to `Agent(...)`.
- The first clean start builds a local derived index and can take roughly
  30-60 seconds. Later starts load the cache.

## Official harness

Copy this bundle over the official kit root (preserving `starter/agent.py`) and
run:

### Windows

```powershell
python -m evaluator.local_evaluator
```

### macOS / Linux

```bash
python3 -m evaluator.local_evaluator
```

Alternatively, add this directory to `PYTHONPATH` and import `Agent` from
`agent`.

The scoring configuration is `configs/default.json`. The submission uses
sequential Top-1 exploration for early MRR and widens to Top-10 on the final
turn to protect hidden-set Hit@10 without changing any target that the
sequential policy would already reach in the first ten positions.

## Method & model choice (short report)

A deterministic seven-stage pipeline — **no LLM and no learned model**, chosen
deliberately for reproducibility, explainability, and zero inference cost:

1. Parsing: template parser for canonical phrasings, fuzzy parser for free-form
   language (browsing, overrides, no-preference cues).
2. Dialogue state machine: accumulates typed constraints and ordered user
   observations; an intent override resets the exposure history.
3. Catalog-grounded belief update: replays the published customer-response
   policy for each candidate and scores the ordered observation likelihood.
   Asymmetric token alignment remains robust when a message drops filler or
   non-essential constraint tokens.
4. Retrieval: category filter + cascade constraint matching with never-evict
   backoff — a constraint only filters while the surviving pool stays
   non-trivial, so one bad parse cannot evict the true target.
5. Ranking: interpretable belief-aware linear scorer (ordered response
   likelihood, constraint coverage, intent-card overlap, BM25 and popularity;
   the quality prior activates only after stated preferences are exhausted).
6. Ask policy: expected-information-gain question selection behind a sigmoid
   confidence gate.
7. Exposure: sequential Top-1 with a final-turn Top-10 fallback (see above).

Result on the public set (official evaluator): TechnicalScore 0.9801,
Hit@10 1.0, MRR 1.0, MTTC 1.995.

## Limitations

- Tuned against the official deterministic customer simulator; sequential
  Top-1 exposure is metric-aligned and sits behind config switches
  (`sequential_top1`, `late_turn_top_k`) for production-style widening.
- The belief likelihood intentionally models the published deterministic
  response policy. A production agent with unconstrained human replies would
  need a learned semantic likelihood or a calibrated fallback channel.
- Free-form paraphrase robustness beyond our two stress sets remains an active
  workstream (a span-recovery parsing layer is the planned next step).
- English-only.

## Disclosure (latency, tokens, cost)

- Latency: roughly 100–200 ms per `respond()` depending on hardware and pool
  size; one-time index build
  30-60 s on first start, cached afterwards.
- Token usage: 0 prompt / 0 completion tokens (no LLM is ever called).
- Estimated model cost: $0. No network access and no credentials are required
  for scoring.

## Environment variables

None required. `COPILOT_CONFIG` may optionally point to an alternative config
file; unset, the agent uses `configs/default.json`.
