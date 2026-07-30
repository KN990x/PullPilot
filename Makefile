SHELL := /bin/sh
IMAGE_NAME ?= ghcr.io/kn990x/pullpilot

# Python interpreter. Uses the repo venv when it exists (`make setup` creates it with
# the version in .python-version); otherwise falls back to `python` from PATH, which
# pyenv already resolves to the pinned version. Works with or without the venv active.
# Without pyenv and without a venv: PY=python3.11 make test
PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python)

# The frontend uses pnpm. The exact version is pinned by `packageManager` in
# web/package.json, so `corepack pnpm` gives everyone the same pnpm.
PNPM ?= corepack pnpm

.PHONY: dev-server dev-web setup setup-web build up lint test

# Sets up the backend environment with the Python version from .python-version.
setup:
	pyenv install -s "$$(cat .python-version)"
	pyenv exec python -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"
	@echo "Done. Activate it with: source .venv/bin/activate"

setup-web:
	cd web && $(PNPM) install --frozen-lockfile

dev-server:
	ALLOW_NO_AUTH=true uvicorn server.app:app --reload

dev-web:
	cd web && $(PNPM) run dev

build:
	docker build -t $(IMAGE_NAME) -t pullpilot .

up:
	docker compose up -d

# `$(PY) -m ruff` rather than a bare `ruff`: uses the venv's ruff even when the venv
# is not active, instead of relying on one being on PATH.
lint:
	$(PY) -m ruff check server tests && $(PY) -m compileall server && cd web && $(PNPM) run lint && $(PNPM) run build

test:
	$(PY) -m pytest tests/
