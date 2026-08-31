# Evaluation Console Instructions

Run the local server yourself and open the preview in the browser available to
this environment when the user asks to see or test it.

## Durable product direction

- Use one lightweight FastAPI process for both JSON APIs and static assets.
- The browser implementation must remain framework-free HTML, CSS and
  JavaScript under `static/`; do not add React, Vite, Node packages or a second
  frontend development server.
- The browser may call only `/api/*`. The FastAPI presentation adapter may
  call only `copilot.public_api`; it must not import algorithm internals.
- `default.json` is the sole production configuration.
- Preserve the light evaluation command center: cobalt primary actions, green
  chain-health states, a dense results grid, and the right-side detail drawer.
- Full Evaluation is the default tab. Single Test remains a first-class tab and
  is reachable from any result row.
- Do not restore the former single-test presentation-mode toggle. Detailed
  diagnostics are always visible.
- The static HTML must contain the cold-start index animation before JavaScript
  performs any network request. Poll `/api/health`, then request
  `/api/bootstrap` only after `ready` becomes true.

## Validation

- Run Python compilation, the Web contract tests and algorithm regression
  tests after changes.
- Confirm `/`, `/static/app.css`, `/static/app.js`, and `/api/health` respond
  from the same FastAPI process.
- Keep all generated caches and evaluation reports inside the workspace.
