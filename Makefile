SHELL := /bin/sh
IMAGE_NAME ?= ghcr.io/kn990x/pullpilot

# Uses the repo venv when it exists, otherwise `python` from PATH, which pyenv already
# resolves to the pinned version. Without either: PY=python3.11 make test
PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python)

# `corepack pnpm` resolves the version pinned by `packageManager` in web/package.json.
PNPM ?= corepack pnpm

.PHONY: dev dev-server dev-web setup setup-web build up lint test

setup:
	pyenv install -s "$$(cat .python-version)"
	pyenv exec python -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"
	@echo "Done. Activate it with: source .venv/bin/activate"

setup-web:
	cd web && $(PNPM) install --frozen-lockfile

# DATA_DIR is mandatory locally: the default /app/data cannot be created outside the
# container. Delete .devdata to get the setup wizard from scratch.
dev-server:
	DATA_DIR=.devdata $(PY) -m uvicorn server.app:app --reload

dev-web:
	cd web && $(PNPM) run dev

# Backend and frontend in one terminal; open http://localhost:5173. The trap kills the
# backend by PID, not `kill 0`: the `--reload` supervisor handles SIGINT itself and would
# survive Ctrl+C holding port 8000.
dev:
	DATA_DIR=.devdata $(PY) -m uvicorn server.app:app --reload & \
	API=$$!; trap "kill $$API 2>/dev/null" EXIT INT TERM; \
	cd web && $(PNPM) run dev

build:
	docker build -t $(IMAGE_NAME) -t pullpilot .

up:
	docker compose up -d

# `$(PY) -m ruff` rather than bare `ruff`: uses the venv's copy even when it is not active.
lint:
	$(PY) -m ruff check server tests && $(PY) -m compileall server && cd web && $(PNPM) run lint && $(PNPM) run build

# Both suites, because a contract change touches server/routers and web/src/lib/api.js.
test:
	$(PY) -m pytest tests/ && cd web && $(PNPM) run test
