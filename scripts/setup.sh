#!/bin/sh
# `make setup`: turns a fresh clone into a working development checkout. Idempotent, so it is
# safe to run again after pulling or when something was missing the first time.
#
#   1. Python from .python-version (mise or pyenv), Node from .nvmrc, pnpm from packageManager.
#   2. .venv with the backend and its dev tools; web/ dependencies from the frozen lockfile.
#   3. Each tracked *.example copied to its local name only when that file does not exist yet.
#
# It never prints the value of a variable, only names.
set -eu

cd "$(dirname "$0")/.."

missing=""
ok() { printf '[setup] ok   %s\n' "$1"; }
fail() {
	printf '[setup] FAIL %s\n' "$1" >&2
	exit 1
}

# Prints the interpreter's full version (3.11.15), or nothing if it cannot run.
py_version() {
	"$1" -c 'import platform; print(platform.python_version())' 2>/dev/null || true
}

# --------------------------------------------------------------------------- 1. toolchain
PY_WANT=$(tr -d '[:space:]' <.python-version)
PY=""
for candidate in .venv/bin/python python3 python; do
	if command -v "$candidate" >/dev/null 2>&1 && [ "$(py_version "$candidate")" = "$PY_WANT" ]; then
		PY=$candidate
		break
	fi
done
# Without mise on the PATH, pyenv can still provide the pinned version.
if [ -z "$PY" ] && command -v pyenv >/dev/null 2>&1; then
	pyenv install -s "$PY_WANT"
	PY=$(PYENV_VERSION="$PY_WANT" pyenv which python)
fi
[ -n "$PY" ] || fail "Python $PY_WANT (.python-version) not found. Run \`mise install\` (or \`pyenv install $PY_WANT\`) and then \`make setup\` again."
ok "Python $PY_WANT"

NODE_WANT=$(tr -d '[:space:]' <.nvmrc)
command -v node >/dev/null 2>&1 || fail "Node $NODE_WANT (.nvmrc) not found. Run \`mise install\` and then \`make setup\` again."
NODE_HAVE=$(node --version)
NODE_MAJOR=$(printf '%s' "$NODE_HAVE" | sed 's/^v//; s/\..*//')
[ "$NODE_MAJOR" = "${NODE_WANT%%.*}" ] || fail "Node $NODE_HAVE, but .nvmrc asks for $NODE_WANT. Run \`mise install\` and then \`make setup\` again."
ok "Node $NODE_HAVE"

# Node 25+ no longer ships corepack, which is what pins pnpm to packageManager.
command -v corepack >/dev/null 2>&1 || fail "corepack not found (Node 25+ no longer ships it). Run \`npm install -g corepack\` once and then \`make setup\` again."
PNPM_WANT=$(sed -n 's/.*"packageManager": *"pnpm@\([^"]*\)".*/\1/p' web/package.json)
PNPM_HAVE=$(cd web && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm --version)
[ "$PNPM_HAVE" = "$PNPM_WANT" ] || fail "corepack resolved pnpm $PNPM_HAVE, but web/package.json pins $PNPM_WANT."
ok "pnpm $PNPM_HAVE (corepack)"

# --------------------------------------------------------------------------- 2. dependencies
if [ "$(py_version .venv/bin/python)" != "$PY_WANT" ]; then
	# --clear: a leftover .venv on another Python version is rebuilt, not mixed.
	"$PY" -m venv --clear .venv
	ok ".venv created with Python $PY_WANT"
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e ".[dev]"
ok "backend installed in .venv (editable, with dev tools)"

(cd web && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm install --frozen-lockfile) ||
	fail "\`pnpm install --frozen-lockfile\` in web/ failed: see the error above."
ok "web/ dependencies installed (frozen lockfile)"

# --------------------------------------------------------------------------- 3. local files
for example in $(git ls-files '*.example'); do
	target=${example%.example}
	if [ -e "$target" ]; then
		ok "$target already exists (left untouched)"
		continue
	fi
	cp "$example" "$target"
	ok "$target created from $example"
	# Uncommented keys with no value. Names only: a value is never printed.
	empty=$(sed -n 's/^\([A-Z][A-Z0-9_]*\)=[[:space:]]*$/\1/p' "$target" | tr '\n' ' ')
	[ -z "$empty" ] || missing="$missing $target:$empty"
done

# --------------------------------------------------------------------------- summary
echo
if [ -n "$missing" ]; then
	echo "[setup] Keys to fill in by hand:$missing"
else
	echo "[setup] Done. Every variable in .env is optional (commented out): the defaults work."
fi
echo "[setup] The SQLite database and the session secret are created in .devdata on first start."
echo "[setup] Next: \`make dev\`, then open http://localhost:5173 and create the admin user."
