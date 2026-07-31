FROM --platform=$BUILDPLATFORM node:24-alpine AS frontend-builder

# corepack installs exactly the pnpm declared in `packageManager`, so the image uses
# the same version as local development and CI.
# Node 24 is the LTS line and still bundles corepack; node 25 dropped it, which is why
# base-image majors are pinned in .github/dependabot.yml.
RUN corepack enable

WORKDIR /app-web

# Manifests only at first, so the dependency layer is cached and is not invalidated
# every time the source code changes.
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

# The Docker CLI and the Compose plugin, copied from the official image instead of
# apt's `docker.io` — that package drags in the whole engine (dockerd, containerd),
# hundreds of MB that never run, because the work happens through the host's socket.
# Copying also retires the hand-pinned `curl` download of the Compose plugin: its
# version now moves with a base image that Dependabot already tracks.
COPY --from=docker:28-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker:28-cli /usr/local/libexec/docker/cli-plugins/docker-compose \
     /usr/local/libexec/docker/cli-plugins/docker-compose

# Build in a scratch directory and throw it away: the only copy of the code that survives
# is the one pip installs. Before, `WORKDIR /app/server` + `uvicorn app:app` left TWO
# copies in the image — `app` came from the copied tree and `server.*` from
# site-packages — and STATIC_DIR existed only to paper over the difference.
WORKDIR /build

COPY pyproject.toml .
COPY server/ ./server
# The Vite bundle goes inside the package (see [tool.setuptools.package-data]) so it
# lands next to config.py's BASE_DIR and nothing has to be told where it is.
COPY --from=frontend-builder /app-web/dist ./server/static

RUN pip install --no-cache-dir . && rm -rf /build

WORKDIR /app
RUN mkdir -p /app/data

EXPOSE 8000

# /api/auth/status responde 200 en los tres estados (sin configurar, sin sesión y con
# sesión), así que no hace falta aceptar un 401 como "sano" — que enmascararía cualquier
# fallo real de autenticación. Se usa python en vez de curl para no instalar un paquete
# más solo para esto.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/auth/status', timeout=4)"

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
