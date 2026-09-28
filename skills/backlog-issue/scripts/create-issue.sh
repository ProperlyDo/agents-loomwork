#!/usr/bin/env bash
# Usage: create-issue.sh <repo> <title> <body-file>
# Creates the issue in ProperlyDo/<repo> and prints its URL.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <property|property-webapp> <title> <body-file>" >&2
  exit 2
fi
repo=$1 title=$2 body=$3

if [[ ! -s $body ]]; then
  echo "body file '$body' is missing or empty" >&2
  exit 1
fi
# The house style bans the spaced em dash; catch it before it reaches GitHub.
if grep -q ' — ' "$body" || [[ $title == *' — '* ]]; then
  echo "spaced em dash found in title or body; use a comma, period, colon or parentheses" >&2
  exit 1
fi

gh issue create -R "ProperlyDo/$repo" --title "$title" --body-file "$body"
