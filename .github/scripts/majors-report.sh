#!/usr/bin/env bash
# Keeps one issue, "Pending major updates", listing every direct dependency whose latest
# release is a new major. Dependabot ignores majors on purpose (they are migrations,
# not updates), so without this they would go unnoticed until something forces them.
#
# The issue is edited in place, never reopened or duplicated: editing an issue body sends
# no notification, so the report is there when you look for it and silent otherwise.
#
# Environment:
#   PNPM_DIRS    space-separated directories with a pnpm lockfile (default ".")
#   PIP_PROJECT  directory whose pyproject.toml lists the Python pins (optional; the
#                project must already be installed in the active interpreter)
#   HELD         space-separated package globs that dependabot.yml holds back entirely;
#                they are listed whenever any newer version exists, not only a major
#   RUNTIME_ROOT directory with .nvmrc / .python-version / Dockerfile (default ".")
#   DRY_RUN=1    print the report instead of touching the issue
set -euo pipefail

TITLE="Pending major updates"
LABEL="majors"
PNPM_DIRS="${PNPM_DIRS:-.}"
PIP_PROJECT="${PIP_PROJECT:-}"
HELD="${HELD:-}"

held_json="$(jq -cn --arg held "$HELD" '$held | split(" ") | map(select(length > 0))')"
majors=""
held_rows=""

for dir in $PNPM_DIRS; do
  # `pnpm outdated` exits 1 whenever something is outdated, which is the normal case here,
  # and prints `{}` when nothing is. It also prints warnings (engines, …) on stdout ahead
  # of the JSON, hence the sed. No JSON at all means it failed (a wrong Node for
  # `engineStrict`, say): that must fail the job, not publish "Nothing pending".
  out="$(cd "$dir" && pnpm outdated --recursive --format json 2>/dev/null | sed -n '/^{/,$p')" || true
  if ! echo "$out" | jq -e 'type == "object"' >/dev/null 2>&1; then
    echo "pnpm outdated produced no report in $dir:" >&2
    (cd "$dir" && pnpm outdated --recursive --format json) >&2 || true
    exit 1
  fi

  rows="$(echo "$out" | jq -r --arg dir "$dir" --argjson held "$held_json" '
    def parts: split("-")[0] | split(".") | map(tonumber? // 0);
    # Exactly what Dependabot treats as a major, so nothing here also arrives as a PR. A
    # 0.x minor (0.52 -> 0.54) is not one: it comes in the monthly group like any minor.
    def breaking($c; $l): ($c | parts)[0] != ($l | parts)[0];
    def held($name): any($held[]; . as $g
      | $name | test("^" + ($g | gsub("\\."; "\\.") | gsub("\\*"; ".*")) + "$"));
    def where: [.value.dependentPackages[]?.name] | if length == 0 then $dir else join(", ") end;
    to_entries[]
    | select(.value.current != null and .value.latest != null and .value.current != .value.latest)
    | (if held(.key) then "held" elif breaking(.value.current; .value.latest) then "major" else empty end) as $kind
    | [$kind, .key, .value.current, .value.latest, ({"dependencies": "prod", "devDependencies": "dev", "optionalDependencies": "optional"}[.value.dependencyType // ""] // "-"), where]
    | @tsv')"

  while IFS=$'\t' read -r kind name current latest type where; do
    [ -n "$kind" ] || continue
    row="| \`$name\` | $current | $latest | $type | $where |"
    if [ "$kind" = "held" ]; then held_rows+="$row"$'\n'; else majors+="$row"$'\n'; fi
  done <<< "$rows"
done

if [ -n "$PIP_PROJECT" ]; then
  outdated="$(python -m pip list --outdated --format json --disable-pip-version-check)"
  majors+="$(OUTDATED="$outdated" python - "$PIP_PROJECT/pyproject.toml" <<'PY'
import json, os, re, sys, tomllib

def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()

def major(version):
    head = re.split(r"[.+-]", version)[0]
    return int(head) if head.isdigit() else 0

with open(sys.argv[1], "rb") as fh:
    project = tomllib.load(fh)["project"]
specs = list(project.get("dependencies", []))
for extra in project.get("optional-dependencies", {}).values():
    specs += extra
direct = {norm(re.split(r"[\s\[<>=!~;]", spec, maxsplit=1)[0]) for spec in specs}

for pkg in json.loads(os.environ["OUTDATED"]):
    if norm(pkg["name"]) not in direct:
        continue
    if major(pkg["version"]) != major(pkg["latest_version"]):
        print(f"| `{pkg['name']}` | {pkg['version']} | {pkg['latest_version']} | python | {sys.argv[1]} |")
PY
)"
  [ -z "$majors" ] || majors="${majors%$'\n'}"$'\n'
fi

# Node, Python and base images are not dependencies Dependabot can move: a Node or Python
# upgrade is a migration of the version file, `engines`, the Dockerfile and CI at once. This
# compares what the repo pins against endoflife.date, so the upgrade shows up here — and so
# does a runtime that has quietly gone out of support.
runtime_report() {
  python3 - "${RUNTIME_ROOT:-.}" <<'PY'
import datetime, json, os, re, sys, urllib.request

root = sys.argv[1]
products = {"node": "nodejs", "python": "python", "docker": "docker-engine"}
today = datetime.date.today().isoformat()
cache = {}

def cycles(product):
    if product not in cache:
        try:
            with urllib.request.urlopen(f"https://endoflife.date/api/{product}.json", timeout=20) as r:
                cache[product] = json.load(r)
        except Exception:
            cache[product] = None
    return cache[product]

def key(cycle):
    return tuple(int(p) for p in re.findall(r"\d+", cycle))

def cycle_of(runtime, version):
    parts = re.findall(r"\d+", version)
    if not parts:
        return None
    return ".".join(parts[:2]) if runtime == "python" else parts[0]

found = []  # (runtime, source, cycle)
for name, runtime in ((".nvmrc", "node"), (".python-version", "python")):
    path = os.path.join(root, name)
    if os.path.exists(path):
        cycle = cycle_of(runtime, open(path).read().strip())
        if cycle:
            found.append((runtime, name, cycle))
dockerfile = os.path.join(root, "Dockerfile")
if os.path.exists(dockerfile):
    for line in open(dockerfile):
        m = re.match(r"\s*(?:FROM(?:\s+--platform=\S+)?|COPY\s+--from=)\s*(\S+)", line, re.I)
        if not m or ":" not in m.group(1):
            continue
        image, tag = m.group(1).split("@")[0].rsplit(":", 1)
        runtime = image.split("/")[-1]
        if runtime in products:
            cycle = cycle_of(runtime, tag)
            row = (runtime, f"Dockerfile ({image}:{tag})", cycle)
            if cycle and row not in found:  # one row per image, however many stages use it
                found.append(row)

if not found:
    print("No version file or base image to check.")
    sys.exit(0)

print("| Runtime | Pinned in | In use | Newest | Support for the one in use ends |")
print("| --- | --- | --- | --- | --- |")
for runtime, source, cycle in found:
    data = cycles(products[runtime])
    if data is None:
        print(f"| {runtime} | {source} | {cycle} | could not reach endoflife.date | |")
        continue
    # Node's "newest" is the newest LTS already in LTS; odd and pre-LTS lines are not
    # upgrade targets for a server. Python and Docker: the newest released cycle.
    candidates = [c for c in data if runtime != "node" or (c.get("lts") and str(c["lts"]) <= today)]
    newest = max((c["cycle"] for c in candidates), key=key, default=cycle)
    mine = next((c for c in data if c["cycle"] == cycle), None)
    eol = str(mine["eol"]) if mine and mine.get("eol") not in (None, False) else "not announced"
    if eol != "not announced" and eol <= today:
        eol = f"**{eol} — out of support**"
    shown = f"**{newest}**" if key(newest) > key(cycle) else f"{newest} (current)"
    print(f"| {runtime} | {source} | {cycle} | {shown} | {eol} |")
PY
}

header=$'| Package | Current | Latest | Type | Used by |\n| --- | --- | --- | --- | --- |'
body="Dependabot does not open major updates here: each one is a migration to plan, not a
routine bump. This issue is rewritten every month by the \`Security audit\` workflow, so
there is nothing to close — it stays open as the list of what is waiting."$'\n\n'
body+="## New majors available"$'\n\n'
if [ -n "$majors" ]; then body+="$header"$'\n'"$majors"; else body+="Nothing pending."$'\n'; fi
if [ -n "$HELD" ]; then
  body+=$'\n'"## Held back in dependabot.yml"$'\n\n'"Updated by hand, together: \`$HELD\`."$'\n\n'
  if [ -n "$held_rows" ]; then body+="$header"$'\n'"$held_rows"; else body+="All current."$'\n'; fi
fi
body+=$'\n'"## Runtimes"$'\n\n'"$(runtime_report)"$'\n\n'
body+="A runtime moves by hand, together: its version file, \`engines\`, the base image and CI (which reads the version file)."$'\n\n'
body+="_Checked on $(date -u +%Y-%m-%d)._"$'\n'

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  printf '%s' "$body" >> "$GITHUB_STEP_SUMMARY"
fi

if [ "${DRY_RUN:-}" = "1" ]; then
  printf '%s' "$body"
  exit 0
fi

body_file="$(mktemp)"
trap 'rm -f "$body_file"' EXIT
printf '%s' "$body" > "$body_file"

gh label create "$LABEL" --color BFD4F2 \
  --description "Breaking dependency releases waiting to be planned" --force >/dev/null
number="$(gh issue list --label "$LABEL" --state open --limit 1 --json number --jq '.[0].number // empty')"
if [ -n "$number" ]; then
  gh issue edit "$number" --body-file "$body_file" >/dev/null
  echo "Updated issue #$number"
else
  gh issue create --title "$TITLE" --label "$LABEL" --body-file "$body_file"
fi
