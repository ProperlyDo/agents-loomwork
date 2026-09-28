#!/usr/bin/env bash
# Usage: link-sub-issue.sh <parent-repo> <parent-number> <child-repo> <child-number>
# Makes the child a sub-issue of the parent; the two may live in different ProperlyDo repos.
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 <parent-repo> <parent-number> <child-repo> <child-number>" >&2
  exit 2
fi

issue_id() {
  gh api graphql -f query="{repository(owner:\"ProperlyDo\",name:\"$1\"){issue(number:$2){id}}}" \
    --jq .data.repository.issue.id
}

parent=$(issue_id "$1" "$2")
child=$(issue_id "$3" "$4")
gh api graphql -H "GraphQL-Features: sub_issues" \
  -f query="mutation{addSubIssue(input:{issueId:\"$parent\",subIssueId:\"$child\"}){subIssue{number}}}" \
  --jq '"linked #\(.data.addSubIssue.subIssue.number)"'
