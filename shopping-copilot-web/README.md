# Shopping Copilot Evaluation Console

The console is a single-process local application:

- FastAPI serves the HTTP API and the static interface.
- The interface is plain HTML, CSS and JavaScript with no build step.
- `copilot.public_api.ShoppingCopilotRuntime` is the only algorithm boundary
  used by the Web adapter.

## Start

From this directory:

### Windows

```powershell
python -m pip install -r backend/requirements.txt
python -m backend.app
```

### macOS / Linux

```bash
python3 -m pip install -r backend/requirements.txt
python3 -m backend.app
```

Open `http://127.0.0.1:8000/`. On a cold start, the page is returned
immediately and displays the catalog-index animation until `/api/health`
reports that the in-memory index is ready.

## Layout

```text
backend/              FastAPI transport and report presentation adapter
static/index.html     Immediate page shell and index-building state
static/app.css        Responsive visual system and animation
static/app.js         API client, rendering and interactions
```

The production evaluation always uses
`../shopping-copilot/configs/default.json`.
