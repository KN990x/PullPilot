FROM --platform=$BUILDPLATFORM node:24-alpine AS frontend-builder

# corepack installs exactly the pnpm from `packageManager`, so image, CI and local
# development agree. Node 25 dropped corepack — see the pins in .github/dependabot.yml.
RUN corepack enable

WORKDIR /app-web

# Manifests first so the dependency layer survives source changes.
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml web/.npmrc ./

RUN pnpm install --frozen-lockfile

COPY web/ ./
RUN pnpm run build

# Keep this version in step with .python-version (pyenv) at the repo root.
FROM python:3.11-slim

# Only `git` needs installing: `git pull` runs on stacks that are clones.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI and Compose plugin from the official image, not apt's `docker.io`: that
# package drags in the whole engine (dockerd, containerd), which never runs here. It also
# puts the Compose version under Dependabot instead of a hand-pinned curl.
COPY --from=docker:28-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker:28-cli /usr/local/libexec/docker/cli-plugins/docker-compose \
     /usr/local/libexec/docker/cli-plugins/docker-compose

# Build in a scratch directory and throw it away, so the only surviving copy of the code
# is the one pip installs. There used to be two, and a STATIC_DIR variable to tell them apart.
WORKDIR /build

COPY pyproject.toml .
COPY server/ ./server
# Inside the package (see [tool.setuptools.package-data]), next to config.py's BASE_DIR,
# so nothing has to be told where the frontend is.
COPY --from=frontend-builder /app-web/dist ./server/static

RUN pip install --no-cache-dir . && rm -rf /build

WORKDIR /app
RUN mkdir -p /app/data

EXPOSE 8000

# /api/auth/status answers 200 in all three states (unconfigured, no session, session), so
# a 401 never has to count as healthy. python instead of curl: one less package.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/auth/status', timeout=4)"

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
