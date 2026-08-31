# 3W1Y ShoppingBot — Conversational Product Search Agent

3W1Y ShoppingBot is a deterministic, multi-turn shopping agent built for the
TechJam Conversational Search challenge. It tracks evolving user intent,
retrieves from a 50,000-product Amazon catalog, asks targeted clarification
questions, and recommends products without an LLM or external API.

## 1. Results

| Evaluation | TechnicalScore | Hit@10 | MRR | MTTC |
|---|---:|---:|---:|---:|
| Official evaluator · 200 public sessions | **0.9801** | **1.000** | **1.000** | **1.995** |
| Paraphrase stress · Level 1 | **0.9801** | **1.000** | **1.000** | **1.995** |
| Paraphrase stress · Level 2 | **0.9800** | **1.000** | **1.000** | **2.000** |

| Runtime profile | Value |
|---|---|
| Core runtime | Python 3.10+ standard library |
| Inference | Deterministic and fully offline |
| LLM / external API | None |
| Token usage / model cost | 0 / $0 |
| Typical turn latency | Approximately 100–200 ms |
| First index build | Approximately 30–60 seconds |

## 2. Architecture

```mermaid
flowchart TB
    Browser["HTML + CSS + JavaScript"] <-->|"/api/*"| Web["FastAPI"]
    Web --> Runtime["ShoppingCopilotRuntime<br/>public algorithm interface"]

    Evaluator["Official Evaluator"] --> Entry["root agent.py<br/>Agent interface"]
    Kit[("Official catalog<br/>sessions and evaluator")]
    Index[("In-memory metadata<br/>SQLite FTS5 index")]
    Config["configs/default.json"]

    Kit --> Evaluator
    Kit --> Runtime
    Kit --> Index

    subgraph Pipeline["Seven-stage conversational search pipeline"]
        Parse["1 · Intent and constraint parsing"] --> State["2 · Dialogue state and override handling"]
        State --> Belief["3 · Catalog-grounded belief update"]
        Belief --> Retrieve["4 · Hybrid retrieval"]
        Retrieve --> Rank["5 · Belief-aware ranking"]
        Rank --> Decide{"6 · Clarify or recommend"}
        Decide -->|"clarify"| Ask["Expected-information-gain question"]
        Decide -->|"recommend"| Expose["7 · Sequential product exposure"]
        Ask -.-> Parse
        Expose -.-> Parse
    end

    Runtime --> Parse
    Entry --> Parse
    Index --> Belief
    Index --> Retrieve
    Index --> Rank
    Config --> Parse
    Config --> Rank
    Config --> Decide
```

A simplified view of the per-turn agent pipeline:

![Simplified pipeline](docs/architecture.png)

The official Agent interface and Web console use the same search pipeline. The
Web layer accesses the algorithm only through `ShoppingCopilotRuntime`, keeping
the interface independent from parsing, retrieval, ranking, and dialogue logic.

## 3. Core algorithm

1. **Hybrid parsing** combines high-precision templates with fuzzy parsing for
   free-form queries, browsing intent, constraints, and intent overrides.
2. **Dynamic dialogue state** accumulates typed slots and resets incompatible
   state when the user changes direction.
3. **Catalog-grounded belief updates** compare ordered observations with the
   customer-response policy to refine candidate likelihoods.
4. **Hybrid retrieval** combines category filtering, constraint cascades, and
   BM25 while retaining candidates when uncertain constraints become too strict.
5. **Belief-aware ranking** combines belief, constraint coverage, intent-card
   overlap, category, BM25, quality, popularity, and profile signals.
6. **Active clarification** uses expected information gain and a deterministic
   confidence gate to decide whether another question is useful.
7. **Metric-aware exposure** uses sequential Top-1 recommendations and a final
   Top-10 fallback to balance precision, recall, and conversion speed.

## 4. Setup and installation

Requirements: **Python 3.10+**.

The official participant kit and catalog are required at runtime. Place them at
the expected paths using the following PowerShell commands.

```powershell
# 1. clone this repo and enter it
git clone https://github.com/app9988/Competition2026.git
cd Competition2026

# 2. clone the official kit INTO the repo root (exact folder name matters -
# the eval scripts look for ..\techjam-conversational-search)
git clone https://github.com/TechJam2026/techjam-conversational-search.git

# 3. download the catalog from the kit's GitHub Release and decompress it
# (Python-only, no extra tools; each command prints a confirmation.
# Alternatively download catalog.jsonl.gz from the Release page in a
# browser into techjam-conversational-search\data\ and run the second
# command to decompress.)
cd techjam-conversational-search
python -c "import urllib.request as u; u.urlretrieve('https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit/catalog.jsonl.gz','data/catalog.jsonl.gz'); print('downloaded')"
python -c "import gzip,shutil; shutil.copyfileobj(gzip.open('data/catalog.jsonl.gz','rb'), open('data/catalog.jsonl','wb')); print('decompressed')"
cd ..

# 4. create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

The core Agent has no third-party dependencies.

## 5. Run the evaluation

Run the official 200-session evaluation from the repository root:

```powershell
python run_official.py
```

Run the instrumented evaluator for per-session and L1–L6 reports:

```powershell
cd shopping-copilot
python scripts\run_eval.py
```

Optional paraphrase stress evaluation:

```powershell
python scripts\run_eval.py --paraphrase 1
python scripts\run_eval.py --paraphrase 2
```

## 6. Web evaluation console

```powershell
python -m pip install -r shopping-copilot-web\backend\requirements.txt
cd shopping-copilot-web
python -m backend.app
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

The console supports full 20/50/100/200-session evaluation and turn-by-turn
single-session replay with recommendations, candidate rankings, metrics, and
diagnostics. During the first index build, an animated loading screen displays
progress and automatically enters the console when the runtime is ready.

## 7. Repository structure

```text
├─ agent.py                         # Official Agent export
├─ run_official.py                  # Official evaluation entry point
├─ shopping-copilot/
│  ├─ configs/default.json          # Runtime configuration
│  ├─ src/copilot/                  # Core algorithms and public runtime
│  ├─ scripts/run_eval.py           # Instrumented evaluator
│  └─ tests/                        # Algorithm regression tests
├─ shopping-copilot-web/
│  ├─ backend/                      # FastAPI application
│  ├─ static/                       # HTML, CSS and JavaScript
│  └─ tests/                        # Web/API contract tests
└─ submission/                      # Competition submission bundle
```

## 8. Limitations and future work

- The catalog-grounded belief update is designed around the official
  deterministic simulator; its generalization to unrestricted human dialogue
  requires further validation.
- Retrieval currently relies on category, constraint, and BM25 signals. A
  lightweight in-memory dense retriever could improve open-ended browsing.
- The current system focuses on English text and isolated sessions. Future work
  could add multilingual understanding and cross-session user profiles.

## 9. Team member contributions

- **Yang Nan** — core algorithm and system architecture: redesigned the agent as
  the seven-stage hybrid pipeline; implemented dynamic dialogue/override state,
  catalog-grounded belief updates, never-evict constraint retrieval,
  belief-aware ranking and active clarification; repaired L1–L6 observability;
  introduced the stable public runtime boundary that decouples the algorithm
  from the Web presentation layer.
- **Zheng Yiting** — evaluation and robustness: paraphrase stress testing,
  cross-harness validation, ablation studies, adversarial/contract checks, and
  cross-platform reproducibility verification.
- **Weng Peng Ju** — evaluation experience and interface design: conversation
  replay, candidate-ranking presentation, the Full Evaluation dashboard,
  responsive UX, and the English interface.
- **Wang Chia Chi** — submission engineering and presentation: competition-rule
  compliance, submission packaging, documentation narrative, Devpost content,
  demo-video production, and voiceover.
