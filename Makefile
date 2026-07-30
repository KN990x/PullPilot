SHELL := /bin/sh
IMAGE_NAME ?= ghcr.io/kn990x/pullpilot

# Intérprete Python. Usa el venv del repo si existe (lo crea `make setup` con la
# versión de .python-version); si no, cae en el `python` del PATH, que con pyenv
# ya resuelve a la versión fijada. Así funciona con el venv activado o sin él.
# Sin pyenv y sin venv: PY=python3.11 make test
PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python)

# El frontend usa pnpm. La versión exacta la fija `packageManager` en
# web/package.json, así que `corepack pnpm` da el mismo pnpm a todo el mundo.
PNPM ?= corepack pnpm

.PHONY: dev-server dev-web setup setup-web build up lint test

# Prepara el entorno de backend con la versión de Python de .python-version.
setup:
	pyenv install -s "$$(cat .python-version)"
	pyenv exec python -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"
	@echo "Listo. Actívalo con: source .venv/bin/activate"

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

# `$(PY) -m ruff` en vez de `ruff` a secas: así usa el ruff del venv aunque no
# esté activado, en lugar de depender de que haya uno en el PATH.
lint:
	$(PY) -m ruff check server tests && $(PY) -m compileall server && cd web && $(PNPM) run lint && $(PNPM) run build

test:
	$(PY) -m pytest tests/
