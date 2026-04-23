# Repository Guidelines

## Project Structure & Module Organization
This workspace has two active parts:

- Frontend app at the repo root: `main.jsx`, `index.html`, `vite.config.js`, and the main feature file `remixed-f545b974.tsx`.
- Backend service in `atlas-data/`: `main.py` (FastAPI app), `scoring.py`, `cache.py`, `collectors/` for external data adapters, and `dashboard.html`.

Build output goes to `dist/`. Treat `README.md` as product/spec context, not as a reliable map of the current codebase.

## Build, Test, and Development Commands
- `npm run dev` — starts the Vite frontend on `http://localhost:5173`.
- `npm run build` — creates the production frontend bundle in `dist/`.
- `npm run preview` — serves the built frontend locally.
- `cd atlas-data; .\.venv\Scripts\activate; uvicorn main:app --host 127.0.0.1 --port 8000` — runs the FastAPI service.
- `atlas-data\start.bat` — Windows helper that creates `.venv`, installs dependencies, and starts the API.

There is no configured root test, lint, or format script at the moment.

## Coding Style & Naming Conventions
Follow the existing style in each area:

- Frontend uses ES modules, React 18, double quotes, and semicolons.
- Backend uses Python with 4-space indentation, snake_case function names, and small module-level helpers.
- Keep UI text and comments in Spanish when extending existing user-facing frontend code.
- Preserve the current file layout unless a refactor is part of the task.

## Testing Guidelines
Automated tests are not set up yet. Before opening changes:

- Run `npm run build` for frontend changes.
- For backend changes, start `uvicorn` or `atlas-data\start.bat` and verify `/health` plus one context endpoint such as `/context/EURUSD`.
- If you add tests, place frontend tests beside the feature file or in a `tests/` folder, and backend tests under `atlas-data/tests/`.

## Commit & Pull Request Guidelines
Git history is not available in this workspace snapshot, so no repository-specific commit convention can be derived. Use short imperative commit subjects, for example: `Add EURUSD health-check fallback`.

Pull requests should include:

- A short description of what changed and why.
- Manual verification steps and affected commands.
- Screenshots for UI changes.
- Any new environment variables or API dependencies.

## Security & Configuration Tips
Do not commit secrets. Keep API keys in `atlas-data/.env` and document new variables near `requirements.txt` or in the PR description.
