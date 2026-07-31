<p align="center">
  <img src="./web/public/assets/logo.png" alt="pullpilot" width="200"/>
</p>

<div align="center">

<h3>
  <a href="#english">English</a> | <a href="#español">Español</a>
</h3>

<p align="center">
  <a href="https://github.com/KN990x/PullPilot/stargazers">
    <img src="https://img.shields.io/github/stars/KN990x/PullPilot?style=social" alt="GitHub stars"/>
  </a>
  &nbsp;
  <a href="https://github.com/KN990x/PullPilot/issues">
    <img src="https://img.shields.io/github/issues/KN990x/PullPilot" alt="GitHub issues"/>
  </a>
  &nbsp;
  <a href="./LICENSE">
    <img src="https://img.shields.io/github/license/KN990x/PullPilot" alt="License"/>
  </a>
  &nbsp;
  <img src="https://img.shields.io/github/last-commit/KN990x/PullPilot" alt="Last commit"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/frontend-React%20%2B%20Vite-61DAFB?logo=react&logoColor=white" alt="React + Vite"/>
  &nbsp;
  <img src="https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI"/>
  &nbsp;
  <img src="https://img.shields.io/badge/infra-Docker-2496ED?logo=docker&logoColor=white" alt="Docker"/>
</p>

</div>

<p align="center">
  <img src="./web/public/assets/dashboard.gif" alt="dashboard" width="auto" height="auto">
</p>


---

<a name="english"></a>
# PullPilot

PullPilot is an app aimed at homelab and personal deployments. It lets you manage updates for your Docker images and services (status, logs, deployment modes) from a single UI.

## Quick install

```bash
sudo mkdir -p /srv/docker-stacks
mkdir -p ~/pullpilot && cd ~/pullpilot
curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/KN990x/PullPilot/main/docker-compose.yml
curl -fsSL -o .env.example https://raw.githubusercontent.com/KN990x/PullPilot/main/.env.example
docker compose up -d
```

Open **http://your-server-ip:8000** (or the host port from `PULLPILOT_PORT` in `.env`).

**First run:** the browser shows a setup wizard. Pick a username and a password, type the password twice, and you are in. The credentials are stored hashed (scrypt) in PullPilot's own database and the session signing secret is generated and persisted automatically — **there is nothing to configure and no secret to put in a file**.

No `.env` is required if you use the default stacks path **`/srv/docker-stacks`**; use **`.env.example`** as reference and copy it to **`.env`** when you need overrides. See [Environment variables (reference)](#environment-variables-reference) for the optional knobs.

> Between the first start and completing the wizard, anyone who can reach the instance can claim it. Complete the wizard right away and do not publish the port before you have. See [SECURITY.md](./SECURITY.md).

**Upgrading from a version that used `AUTH_USER` / `AUTH_PASS`?** Nothing to do. On first start those values seed the database once, you keep logging in exactly as before, and the logs tell you when it is safe to delete them from `.env`.

## After startup

- **Different stacks location:** create the folder on the host, then add `.env` next to `docker-compose.yml` with **`DOCKER_ROOT_PATH=/absolute/path/to/stacks`** (same path on host and in the container). After any `.env` change, run `docker compose up -d` or `docker compose restart`.
- **Layout:** each project is a **subfolder** under that root with `docker-compose.yml` or `docker-compose.yaml` inside. Keep PullPilot’s compose folder **outside** that tree when you can.

```
/srv/docker-stacks/          # default DOCKER_ROOT_PATH
├── plex/
│   └── docker-compose.yml
└── ...
```

> Folders named `pullpilot`, `pullpilot-ui`, `docker-updater`, and `data` are ignored under the stacks root.

**Cloned repo (development):** use [`docker-compose.yml`](./docker-compose.yml) from the tree; overrides are documented in [`.env.example`](./.env.example).

## Usage Guide

- **Dashboard:** cards per project; status, per-project update, **Full stop** and **Exclude** toggles.
- **Update All:** scans non-excluded projects, `git pull` where applicable, recreates containers; summary in **History**.
- **Schedule:** default global update daily at 04:00 (container time).

## Local development (contributors)

```bash
git clone https://github.com/KN990x/PullPilot
cd PullPilot
docker compose -f docker-compose-build.yml up -d --build
```

Day-to-day: `make dev-server`, `make dev-web` (see [`Makefile`](./Makefile)).

## Important notes

- **GHCR image:** the published image is `ghcr.io/kn990x/pullpilot`. If you still pin `ghcr.io/kernel-nomad/pullpilot`, update your compose file or `docker pull` to the new path.
- **Docker socket:** treat PullPilot like root access; do not expose port 8000 to the public internet without TLS (reverse proxy), a strong password, and ideally an extra auth layer (Authelia, Authentik, etc.).
- **Stack paths:** updates and scheduled jobs only run under **`PROJECTS_ROOT`** (resolved); database paths outside that tree are rejected.
- **Single worker:** one Uvicorn worker per instance. The signing secret *is* shared across workers (it lives in a file under `DATA_DIR`), but the scheduler, the login rate limit and the progress state are per process, so **`UVICORN_WORKERS` > 1** means duplicated scheduled updates.
- **Auth:** credentials live hashed in the database and are created through the setup wizard on first run. **`ALLOW_NO_AUTH=true`** wins over everything and leaves the API open, even when credentials already exist.
- **Changing the password:** the account button in the header (next to the language switch) changes username and password. Doing so signs out every other device.
- **Password recovery:** there is no automatic reset. Stop the container, delete the stored credentials, and the wizard comes back:
  ```bash
  docker compose stop pullpilot
  docker run --rm -v pullpilot_data:/data alpine sh -c \
    "apk add --no-cache sqlite >/dev/null && sqlite3 /data/pullpilot.db 'DELETE FROM auth_credentials;'"
  docker compose start pullpilot
  ```
  Anyone able to run that already has the host and therefore the Docker socket, so this is maintenance, not a privilege escalation.
- **`session_secret.key`:** created under `DATA_DIR` with mode `0600`, owned by root (the container runs as root). Deleting it just signs everyone out.
- **HTTPS / cookies:** behind a TLS-terminating proxy, set **`SESSION_HTTPS_ONLY=true`**. **`SESSION_SAME_SITE`** defaults to `lax` (Starlette); use `strict` for stricter same-site behaviour, or `none` only with HTTPS and cross-site requirements (browsers require `Secure`).
- **PROJECTS_ROOT:** use only if the path *inside* the container must differ from the bind mount; otherwise use `DOCKER_ROOT_PATH`.
- **Proxy:** `TRUST_X_FORWARDED_FOR=true` only behind a proxy you trust (affects login rate-limit IP).

---

<a name="environment-variables-reference"></a>
## Environment variables (reference)

Single list for Compose `.env` and runtime. Details also in [`.env.example`](./.env.example).

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCKER_ROOT_PATH` | `/srv/docker-stacks` | Same absolute stacks path on host and container (bind mount). |
| `PROJECTS_ROOT` | (from `DOCKER_ROOT_PATH`) | Advanced: different path *inside* the container only. |
| `PULLPILOT_PORT` | `8000` | Published host port for the UI. |
| `TZ` | `UTC` | Container timezone. |
| `DATA_DIR` | `/app/data` | SQLite and runtime data (official compose uses volume `pullpilot_data`). |
| `ALLOW_NO_AUTH` | `false` | **Legacy.** `true` opens the whole API and disables the setup wizard. Isolated networks only. |
| `AUTH_USER` / `AUTH_PASS` | (unset) | **Legacy, optional.** Seeds the credentials on the first start only; afterwards the database wins and these are ignored. |
| `SESSION_SECRET` | (auto) | Optional. Generated and persisted at `$DATA_DIR/session_secret.key` (mode `0600`) so sessions survive restarts. Set it only to control the key yourself. |
| `SESSION_HTTPS_ONLY` | `false` | Set `true` if the app is only served over HTTPS. |
| `SESSION_SAME_SITE` | `lax` | Cookie SameSite: `lax`, `strict`, or `none` (use `none` only with HTTPS). |
| `CORS_ORIGINS` | (empty) | Comma-separated origins; empty often OK when the SPA is served by the same app. |
| `HEALTHCHECK_TIMEOUT` | `60` | Post-deploy health wait (seconds). |
| `COMMAND_TIMEOUT` | `300` | External command timeout (seconds). |
| `LOG_LOCALE` | `es` | Language for scheduled update logs and history entries (`es` or `en`). UI-triggered updates use `Accept-Language` instead. |
| `LOGIN_RATE_LIMIT_ENABLED` | `true` | In-memory login rate limit per IP. |
| `LOGIN_RATE_LIMIT_MAX` | `15` | Max attempts per window. |
| `LOGIN_RATE_LIMIT_WINDOW_SEC` | `300` | Window length (seconds). |
| `TRUST_X_FORWARDED_FOR` | `false` | Use `X-Forwarded-For` for rate limiting (trusted proxy only). |

### Advanced (copy into `.env` as needed)

```bash
# Production-style (example)
# ALLOW_NO_AUTH=false
# AUTH_USER=admin
# AUTH_PASS=your-secure-password
SESSION_HTTPS_ONLY=true
# SESSION_SAME_SITE=strict
# CORS_ORIGINS=https://pullpilot.example.com
# LOGIN_RATE_LIMIT_ENABLED=true
# LOGIN_RATE_LIMIT_MAX=15
# LOGIN_RATE_LIMIT_WINDOW_SEC=300
# HEALTHCHECK_TIMEOUT=60
# COMMAND_TIMEOUT=300
# TRUST_X_FORWARDED_FOR=true
```

---

<a name="español"></a>
# PullPilot

PullPilot es una aplicación pensada para desplegarse en homelabs y para uso personal. Permite gestionar actualizaciones de imágenes y servicios Docker (estado, logs, modos de despliegue) desde una sola interfaz.

## Instalación rápida

```bash
sudo mkdir -p /srv/docker-stacks
mkdir -p ~/pullpilot && cd ~/pullpilot
curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/KN990x/PullPilot/main/docker-compose.yml
curl -fsSL -o .env.example https://raw.githubusercontent.com/KN990x/PullPilot/main/.env.example
docker compose up -d
```

Abre **http://tu-servidor-ip:8000** (o el puerto del host definido en `PULLPILOT_PORT` en `.env`).

**Primer arranque:** el navegador muestra un asistente de configuración. Eliges usuario y contraseña, la repites, y ya estás dentro. Las credenciales se guardan hasheadas (scrypt) en la propia base de datos de PullPilot y el secreto de firma de sesión se genera y persiste solo — **no hay nada que configurar ni ningún secreto que meter en un fichero**.

No hace falta `.env` si usas la ruta por defecto de stacks **`/srv/docker-stacks`**; usa **`.env.example`** como referencia y cópialo a **`.env`** cuando necesites personalizar. En [Variables de entorno (referencia)](#variables-de-entorno-referencia) están los ajustes opcionales.

> Entre el primer arranque y completar el asistente, cualquiera que alcance la instancia puede reclamarla. Complétalo enseguida y no publiques el puerto antes de hacerlo. Véase [SECURITY.md](./SECURITY.md).

**¿Vienes de una versión con `AUTH_USER` / `AUTH_PASS`?** No tienes que hacer nada. En el primer arranque esos valores siembran la base de datos una vez, sigues entrando igual que antes, y los logs te avisan de cuándo puedes borrarlos del `.env`.

## Después del arranque

- **Otra ubicación de stacks:** crea la carpeta en el host y añade `.env` junto a `docker-compose.yml` con **`DOCKER_ROOT_PATH=/ruta/absoluta/a/stacks`** (misma ruta en host y contenedor). Tras cualquier cambio en `.env`, ejecuta `docker compose up -d` o `docker compose restart`.
- **Estructura:** cada proyecto es una **subcarpeta** bajo esa raíz con `docker-compose.yml` o `docker-compose.yaml` dentro. Cuando puedas, mantén la carpeta de compose de PullPilot **fuera** de ese árbol.

```
/srv/docker-stacks/          # DOCKER_ROOT_PATH por defecto
├── plex/
│   └── docker-compose.yml
└── ...
```

> Las carpetas llamadas `pullpilot`, `pullpilot-ui`, `docker-updater` y `data` se ignoran bajo la raíz de stacks.

**Repositorio clonado (desarrollo):** usa el [`docker-compose.yml`](./docker-compose.yml) del árbol; los overrides están documentados en [`.env.example`](./.env.example).

## Guía de uso

- **Dashboard:** tarjetas por proyecto; estado, actualización por proyecto, interruptores **Full stop** y **Excluir**.
- **Actualizar todo:** escanea proyectos no excluidos, `git pull` cuando aplique, recrea contenedores; resumen en **Historial**.
- **Programación:** actualización global diaria por defecto a las 04:00 (hora del contenedor).

## Desarrollo local (contribuidores)

```bash
git clone https://github.com/KN990x/PullPilot
cd PullPilot
docker compose -f docker-compose-build.yml up -d --build
```

Día a día: `make dev-server`, `make dev-web` (véase [`Makefile`](./Makefile)).

## Notas importantes

- **Imagen GHCR:** la imagen publicada es `ghcr.io/kn990x/pullpilot`. Si sigues usando `ghcr.io/kernel-nomad/pullpilot`, actualiza el compose o `docker pull` a la nueva ruta.
- **Socket de Docker:** trata PullPilot como acceso de nivel root; no expongas el puerto 8000 a internet pública sin TLS (proxy inverso), una contraseña robusta y, si es posible, otra capa de autenticación (Authelia, Authentik, etc.).
- **Rutas de stacks:** las actualizaciones y tareas programadas solo se ejecutan bajo **`PROJECTS_ROOT`** (resuelto); las rutas en base de datos fuera de ese árbol se rechazan.
- **Un solo worker:** un worker de Uvicorn por instancia. El secreto de firma **sí** se comparte entre workers (vive en un fichero dentro de `DATA_DIR`), pero el scheduler, el límite de intentos de login y el estado de progreso son por proceso, así que **`UVICORN_WORKERS` > 1** significa actualizaciones programadas duplicadas.
- **Autenticación:** las credenciales viven hasheadas en la base de datos y se crean con el asistente en el primer arranque. **`ALLOW_NO_AUTH=true`** gana sobre todo lo demás y deja la API abierta, incluso si ya existen credenciales.
- **Cambiar la contraseña:** el botón de cuenta de la cabecera (junto al selector de idioma) cambia usuario y contraseña. Al hacerlo se cierra la sesión en el resto de dispositivos.
- **Recuperación de la contraseña:** no hay reseteo automático. Para el contenedor, borra las credenciales guardadas y el asistente vuelve a salir:
  ```bash
  docker compose stop pullpilot
  docker run --rm -v pullpilot_data:/data alpine sh -c \
    "apk add --no-cache sqlite >/dev/null && sqlite3 /data/pullpilot.db 'DELETE FROM auth_credentials;'"
  docker compose start pullpilot
  ```
  Quien pueda ejecutar eso ya tiene el host y, por tanto, el socket de Docker: es mantenimiento, no una escalada de privilegios.
- **`session_secret.key`:** se crea bajo `DATA_DIR` con permisos `0600` y dueño root (el contenedor corre como root). Borrarlo solo cierra la sesión de todo el mundo.
- **HTTPS / cookies:** detrás de un proxy que termina TLS, define **`SESSION_HTTPS_ONLY=true`**. **`SESSION_SAME_SITE`** por defecto es `lax` (Starlette); usa `strict` para un comportamiento same-site más estricto, o `none` solo con HTTPS y requisitos cross-site (los navegadores exigen `Secure`).
- **PROJECTS_ROOT:** úsalo solo si la ruta *dentro* del contenedor debe diferir del bind mount; en caso contrario usa `DOCKER_ROOT_PATH`.
- **Proxy:** `TRUST_X_FORWARDED_FOR=true` solo detrás de un proxy en el que confíes (afecta la IP usada en el rate limit de login).

---

<a name="variables-de-entorno-referencia"></a>
## Variables de entorno (referencia)

Lista única para `.env` de Compose y tiempo de ejecución. Más detalle en [`.env.example`](./.env.example).

| Variable | Valor por defecto | Descripción |
|----------|-------------------|-------------|
| `DOCKER_ROOT_PATH` | `/srv/docker-stacks` | Misma ruta absoluta de stacks en host y contenedor (bind mount). |
| `PROJECTS_ROOT` | (desde `DOCKER_ROOT_PATH`) | Avanzado: ruta distinta *solo* dentro del contenedor. |
| `PULLPILOT_PORT` | `8000` | Puerto publicado en el host para la interfaz. |
| `TZ` | `UTC` | Zona horaria del contenedor. |
| `DATA_DIR` | `/app/data` | SQLite y datos en tiempo de ejecución (el compose oficial usa el volumen `pullpilot_data`). |
| `ALLOW_NO_AUTH` | `false` | **Heredada.** `true` abre la API entera y desactiva el asistente. Solo redes aisladas. |
| `AUTH_USER` / `AUTH_PASS` | (sin definir) | **Heredadas, opcionales.** Solo siembran las credenciales en el primer arranque; después manda la base de datos y se ignoran. |
| `SESSION_SECRET` | (automático) | Opcional. Se genera y persiste en `$DATA_DIR/session_secret.key` (permisos `0600`) para que las sesiones sobrevivan a los reinicios. Defínelo solo si quieres controlar tú la clave. |
| `SESSION_HTTPS_ONLY` | `false` | Pon `true` si la app solo se sirve por HTTPS. |
| `SESSION_SAME_SITE` | `lax` | SameSite de la cookie: `lax`, `strict` o `none` (usa `none` solo con HTTPS). |
| `CORS_ORIGINS` | (vacío) | Orígenes separados por comas; vacío suele bastar cuando el SPA lo sirve la misma app. |
| `HEALTHCHECK_TIMEOUT` | `60` | Espera de salud tras despliegue (segundos). |
| `COMMAND_TIMEOUT` | `300` | Tiempo máximo de comandos externos (segundos). |
| `LOG_LOCALE` | `es` | Idioma de logs de actualizaciones programadas e historial (`es` o `en`). Las actualizaciones desde la UI usan `Accept-Language`. |
| `LOGIN_RATE_LIMIT_ENABLED` | `true` | Límite de intentos de login en memoria por IP. |
| `LOGIN_RATE_LIMIT_MAX` | `15` | Máximo de intentos por ventana. |
| `LOGIN_RATE_LIMIT_WINDOW_SEC` | `300` | Duración de la ventana (segundos). |
| `TRUST_X_FORWARDED_FOR` | `false` | Usar `X-Forwarded-For` para el rate limit (solo proxy de confianza). |

### Avanzado (copia en `.env` según necesites)

```bash
# Estilo producción (ejemplo)
# ALLOW_NO_AUTH=false
# AUTH_USER=admin
# AUTH_PASS=tu-contraseña-segura
SESSION_HTTPS_ONLY=true
# SESSION_SAME_SITE=strict
# CORS_ORIGINS=https://pullpilot.example.com
# LOGIN_RATE_LIMIT_ENABLED=true
# LOGIN_RATE_LIMIT_MAX=15
# LOGIN_RATE_LIMIT_WINDOW_SEC=300
# HEALTHCHECK_TIMEOUT=60
# COMMAND_TIMEOUT=300
# TRUST_X_FORWARDED_FOR=true
```
