FROM --platform=$BUILDPLATFORM node:24-alpine AS frontend-builder

# corepack installs exactly the pnpm declared in `packageManager`, so the image uses
# the same version as local development and CI.
# Node 24 still bundles corepack; if a future Dependabot bump raises the base image
# and this step fails, corepack has to be installed separately.
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

RUN apt-get update && apt-get install -y \
    docker.io \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        items="x86_64"; \
    elif [ "$ARCH" = "aarch64" ]; then \
        items="aarch64"; \
    else \
        echo "Arquitectura no soportada: $ARCH" && exit 1; \
    fi && \
    mkdir -p /usr/local/lib/docker/cli-plugins && \
    curl -SL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-${items}" -o /usr/local/lib/docker/cli-plugins/docker-compose && \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose && \
    ln -s /usr/local/lib/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose

WORKDIR /app

COPY pyproject.toml .
COPY server/ ./server
RUN pip install --no-cache-dir .

COPY --from=frontend-builder /app-web/dist ./server/static

# pip install puts `server` in site-packages; dist lives under /app/server/static.
ENV STATIC_DIR=/app/server/static

RUN mkdir -p /app/data

EXPOSE 8000

# /api/auth/status responde 200 en los tres estados (sin configurar, sin sesión y con
# sesión), así que ya no hace falta aceptar un 401 como "sano" — que enmascaraba
# cualquier fallo real de autenticación.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS -o /dev/null http://127.0.0.1:8000/api/auth/status

WORKDIR /app/server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
