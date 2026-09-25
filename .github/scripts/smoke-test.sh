#!/usr/bin/env bash
# Cold-start smoke: no auth variables at all, exactly the cold start a new user gets.
# Usage: smoke-test.sh <image> <container-name> [platform]
# CI calls it on the amd64 build; the release workflow also boots the arm64 image under
# emulation by passing a platform. Cleans up its own container on exit.
set -euo pipefail

IMAGE="${1:?image required}"
NAME="${2:?container name required}"
PLATFORM="${3:-}"
BASE="http://127.0.0.1:8000"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

platform_args=()
tries=30
if [ -n "$PLATFORM" ]; then
  platform_args=(--platform "$PLATFORM")
  # Emulated arm64 boots several times slower; still a hard fail if it never answers.
  tries=90
fi

docker run -d --name "$NAME" "${platform_args[@]}" -p 8000:8000 "$IMAGE"

rm -f /tmp/status.json
for _ in $(seq 1 "$tries"); do
  if curl -fsS -o /tmp/status.json "${BASE}/api/auth/status"; then
    break
  fi
  sleep 2
done
if ! [ -s /tmp/status.json ]; then
  echo "::error::Container did not respond within $((tries * 2))s"
  docker logs "$NAME"
  exit 1
fi
echo "auth status: $(cat /tmp/status.json)"
grep -q '"setup_complete":false' /tmp/status.json

# The API stays closed until the wizard is done.
code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/api/projects")
[ "$code" = "401" ] || { echo "::error::/api/projects should be 401, got $code"; exit 1; }

code=$(curl -s -o /dev/null -w "%{http_code}" \
  -H 'Content-Type: application/json' \
  -d '{"username":"ciadmin","password":"ci-only-password","password_confirm":"ci-only-password"}' \
  -c /tmp/cookies.txt "${BASE}/api/auth/setup")
[ "$code" = "201" ] || { echo "::error::setup should be 201, got $code"; docker logs "$NAME"; exit 1; }

code=$(curl -s -o /dev/null -w "%{http_code}" -b /tmp/cookies.txt "${BASE}/api/projects")
[ "$code" = "200" ] || { echo "::error::/api/projects with session should be 200, got $code"; exit 1; }

# The SPA fallback must not swallow API 404s: it used to return index.html with
# status 200 and the UI took the delete as done.
code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  -b /tmp/cookies.txt "${BASE}/api/schedules/99999")
[ "$code" = "404" ] || { echo "::error::/api/schedules/99999 should be 404, got $code"; exit 1; }

# ...but a navigation route does have to get the SPA shell.
code=$(curl -s -o /dev/null -w "%{http_code}" -b /tmp/cookies.txt "${BASE}/history")
[ "$code" = "200" ] || { echo "::error::/history should serve the SPA shell, got $code"; exit 1; }

# docker compose has to exist in the image: it runs every update, and now comes
# from the official CLI rather than the docker.io package.
docker exec "$NAME" docker compose version

echo "Cold start, setup wizard, authenticated request and 404 handling all OK${PLATFORM:+ for $PLATFORM}"
