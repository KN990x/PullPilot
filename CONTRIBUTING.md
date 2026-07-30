# Contributing to PullPilot

Thanks for your interest in improving PullPilot. This guide covers how to set up your environment, coding conventions, and how to propose changes.

You can open issues for bugs or ideas, and pull requests for fixes or features.

## Requirements

- **Python** 3.11 or newer (see `requires-python` in `pyproject.toml`).
- **Node.js** (LTS recommended) and npm for the frontend in `web/`.
- **Docker** and **Docker Compose** (optional but useful to validate the production image or real compose workflows).

## Development setup

### Backend

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

The project has no Python lockfile: the exact versions of the direct dependencies are pinned
with `==` in `pyproject.toml`, and CI audits the fully resolved tree with `pip-audit`.
Install with `pip`; do not add a `uv.lock` unless the Docker build is migrated to `uv` as well.

Relevant environment variables (adjust paths for your machine):

| Variable | Description |
|----------|-------------|
| `DOCKER_ROOT_PATH` | In Docker Compose installs, the stacks root on host and container (same absolute path as the bind mount). Optional in `.env`: the official compose defaults to `/srv/docker-stacks`. |
| `PROJECTS_ROOT` | Advanced override: directory inside the container whose subfolders contain `docker-compose.yml` (defaults from `DOCKER_ROOT_PATH` or `/srv/docker-stacks`). |
| `DATA_DIR` | SQLite and runtime data (container default: `/app/data`). Locally, often a folder in the repo such as `./data`. |
| `AUTH_USER` / `AUTH_PASS` | Optional UI credentials. |
| `SESSION_SECRET` | Session cookie signing key; set a fixed value in dev so sessions survive restarts. |
| `HEALTHCHECK_TIMEOUT` | Post-deploy health check timeout (seconds). |
| `COMMAND_TIMEOUT` | External command timeout (seconds). |

Run with auto-reload:

```bash
make dev-server
```

Equivalent to `uvicorn server.app:app --reload`.

### Frontend

```bash
cd web
npm install
npm run dev
```

Or from the repo root: `make dev-web`.

In development, Vite **proxies** `/api` (and related auth routes) to `http://localhost:8000`. Keep the backend on port 8000 and use Vite’s dev port for the UI (typically 5173).

### Verify the build

```bash
make lint
```

Invokes Ruff on `server/` and `tests/`, byte-compiles `server/` using the Make variable `PY` (defaults to `python`), then runs `npm run lint` and `npm run build` in `web/`.

### Tests

```bash
make test
```

Runs `pytest` via `PY -m pytest tests/`. Activate a Python 3.11+ venv first so `python` resolves correctly. On macOS, if the system `python3` is older than 3.11, run e.g. `PY=python3.11 make test`.

### Docker image

```bash
make build
make up
```

The default `IMAGE_NAME` targets the GHCR-published image; override if needed: `make build IMAGE_NAME=pullpilot:dev`.

## Code conventions

- **Python:** `snake_case` for functions and variables; type new functions; business logic belongs in `server/services/`, not in routers.
- **React:** `camelCase`; components under `web/src/components/`; HTTP calls centralized in `web/src/lib/api.js`.
- **API:** Keep route and contract changes in sync between the backend (`server/routers/`) and `web/src/lib/api.js`.
- **i18n:** If you add UI strings, update **both** languages in `web/src/i18n.js`.

## Pull requests

1. Branch from `main` with a descriptive name.
2. Use clear commit messages.
3. Run `make lint` before opening the PR if you changed Python or the frontend.
4. In the PR, explain **what** changed and **why**; link related issues when applicable.
5. Docker or Compose changes should be reviewed together with `Dockerfile`, `.dockerignore`, or `docker-compose.yml` when relevant.

## Image publishing (maintainers)

The `.github/workflows/ghcr-publish.yml` workflow builds and pushes the image to **GitHub Container Registry** when a **release** (not a prerelease) is published on GitHub. It also uploads `docker-compose.yml` and `env.example` to the release. The latter is a copy of `.env.example` under a name without a leading dot so the asset is not renamed by GitHub / `gh` (which would otherwise produce names like `default.env.example`).

---

If anything here does not match your setup or is missing detail, open an issue and we can refine it in the repository.
