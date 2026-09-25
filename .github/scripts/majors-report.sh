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
  # `pnpm outdated` exits 1 whenever something is outdated, which is the normal case here.
  # It also prints warnings (engines, …) on stdout ahead of the JSON, hence the sed.
  # An empty or non-JSON answer is a real failure and must not produce an empty report.
  out="$(cd "$dir" && pnpm outdated --recursive --format json 2>/dev/null | sed -n '/^{/,$p')" || true
  [ -n "$out" ] || out="{}"
  echo "$out" | jq -e 'type == "object"' >/dev/null

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
body+=$'\n'"The runtime itself (Node, Python) is not listed: it moves by hand, together with its version file, \`engines\` and any base image."$'\n\n'
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
