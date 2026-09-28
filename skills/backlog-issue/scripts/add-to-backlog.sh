#!/usr/bin/env bash
# Usage: add-to-backlog.sh <issue-url> [<issue-url> ...]
# Adds each issue to project 3 of ProperlyDo (https://github.com/orgs/ProperlyDo/projects/3) with Status "Backlog".
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <issue-url> [<issue-url> ...]" >&2
  exit 2
fi

# Exit 3 tells the caller the token lacks the scope: the user has to run the browser login themselves.
if ! gh auth status 2>&1 | grep -q "'project'"; then
  echo "the gh token has no 'project' scope; ask the user to run: gh auth refresh -s project" >&2
  exit 3
fi

project_id=$(gh project view 3 --owner ProperlyDo --format json --jq .id)
fields=$(gh project field-list 3 --owner ProperlyDo --format json)
status_field=$(jq -r '.fields[] | select(.name=="Status") | .id' <<<"$fields")
backlog=$(jq -r '.fields[] | select(.name=="Status") | .options[] | select(.name=="Backlog") | .id' <<<"$fields")

if [[ -z $backlog ]]; then
  echo "the Status field has no 'Backlog' option; existing options:" >&2
  jq -r '.fields[] | select(.name=="Status") | .options[].name' <<<"$fields" >&2
  exit 4
fi

for url in "$@"; do
  item=$(gh project item-add 3 --owner ProperlyDo --url "$url" --format json --jq .id)
  gh project item-edit --project-id "$project_id" --id "$item" \
    --field-id "$status_field" --single-select-option-id "$backlog" >/dev/null
  echo "backlog: $url"
done
