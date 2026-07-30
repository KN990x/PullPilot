FROM --platform=$BUILDPLATFORM node:24-alpine AS frontend-builder

# corepack instala exactamente el pnpm declarado en `packageManager`, así que la
# imagen usa la misma versión que el entorno local y que CI.
# Node 24 aún trae corepack incorporado; si un futuro bump de Dependabot sube la
# imagen base y este paso falla, es que hay que instalarlo aparte.
RUN corepack enable

WORKDIR /app-web

# Solo los manifiestos primero, para que la capa de dependencias se cachee y no
# se invalide cada vez que cambia el código fuente.
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml web/.npmrc ./

RUN pnpm install --frozen-lockfile

COPY web/ ./
RUN pnpm run build

# La versión debe ir a la par con .python-version (pyenv) en la raíz del repo.
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

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD sh -c 'status=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/update-status); [ "$status" = "200" ] || [ "$status" = "401" ]'

WORKDIR /app/server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
