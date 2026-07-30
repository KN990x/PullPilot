# Contributing to PullPilot

Thanks for your interest in improving PullPilot. This guide covers how to set up your environment, coding conventions, and how to propose changes.

You can open issues for bugs or ideas, and pull requests for fixes or features.

## Requirements

- **[pyenv](https://github.com/pyenv/pyenv)** to get the Python version pinned in
  `.python-version` (3.11.15 — the same line as the published `python:3.11-slim` image).
  Any Python 3.11+ works, but pyenv is what CI parity assumes.
- **Node.js** 22.12 or newer, and **pnpm** for the frontend in `web/`. Do not use npm or
  Yarn: the lockfile is `web/pnpm-lock.yaml`.
- **Docker** and **Docker Compose** (optional but useful to validate the production image or real compose workflows).

## Development setup

The quickest path is `make setup` (backend) and `make setup-web` (frontend). Both are
described below if you prefer to run the steps yourself.

### Backend

From the repository root:

```bash
pyenv install -s "$(cat .python-version)"
pyenv exec python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

pyenv reads `.python-version` automatically inside the repository, so `python` resolves to
the pinned interpreter once the shim is on your `PATH`.

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
corepack enable        # once per machine
cd web
pnpm install --frozen-lockfile
pnpm run dev
```

Or from the repo root: `make setup-web` and `make dev-web`.

`web/package.json` pins the pnpm version in `packageManager`, so corepack (and pnpm
itself) will switch to it automatically — you get the same pnpm as CI and the Docker
build regardless of what you have installed globally.

Two pnpm settings in `web/pnpm-workspace.yaml` are deliberate and worth knowing about:

- `allowBuilds` — pnpm blocks dependency install scripts by default, the classic npm
  supply-chain vector. Each one is allowed explicitly (only `esbuild` needs it, for its
  native binary). If an install warns about ignored build scripts, add the package here
  after checking why it needs one.
- `minimumReleaseAge: 10080` — a new resolution will not pick a version published less
  than 7 days ago, which is the window in which malicious publishes are usually caught.
  It matches the `cooldown` in `.github/dependabot.yml` and does not affect
  `--frozen-lockfile`, so CI and Docker stay deterministic. If an install fails with
  `ERR_PNPM_NO_MATURE_MATCHING_VERSION`, lower the range in `package.json` to the newest
  version that has aged in — do not add an exclusion just to get the newest release.

pnpm uses a strict `node_modules`: a package can only import what it declares. That is
intentional — it is what surfaced the missing `workbox-window` declaration that npm's
hoisting had been hiding. If an import fails to resolve, the fix is almost always to
declare the dependency, not to hoist it.

In development, Vite **proxies** `/api` (and related auth routes) to `http://localhost:8000`. Keep the backend on port 8000 and use Vite’s dev port for the UI (typically 5173).

### Verify the build

```bash
make lint
```

Invokes Ruff on `server/` and `tests/`, byte-compiles `server/` using the Make variable `PY` (defaults to `pyenv exec python`), then runs `pnpm run lint` and `pnpm run build` in `web/`.

### Tests

```bash
make test
```

Runs `pytest` via `PY -m pytest tests/`, where `PY` defaults to `pyenv exec python` so the
interpreter comes from `.python-version` whether or not the venv is active. Without pyenv,
point it at your own interpreter: `PY=python3.11 make test`.

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
