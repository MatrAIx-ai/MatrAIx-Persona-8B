#!/usr/bin/env bash
# Keep exactly one rebase-conflict comment per PR, always current.
#
# The weekly rebase runs forever, so posting a fresh comment on every failed
# attempt would bury the PR in identical notices. Instead we edit one comment
# in place, and skip entirely when neither side has moved since last week.
#
# Usage: upsert-rebase-comment.sh <pr-number> <head-sha> <base-sha>
set -euo pipefail

pr="$1"
head_sha="$2"
base_sha="$3"
marker="<!-- weekly-rebase -->"
stamp="<!-- head:${head_sha} base:${base_sha} -->"

body="${marker}
${stamp}
This branch no longer rebases cleanly onto \`${BASE_BRANCH}\`.

The weekly rebase job tried to replay your commits onto \`${BASE_BRANCH}\` at
\`${base_sha:0:7}\` and hit conflicts, so it stopped and left your branch exactly
as you pushed it — nothing here was changed.

To pick it up locally:

\`\`\`bash
git fetch upstream ${BASE_BRANCH}
git rebase upstream/${BASE_BRANCH}
# resolve conflicts, then
git push --force-with-lease
\`\`\`

This comment is edited in place, not repeated, and disappears from the job's
warnings once the rebase succeeds."

existing=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${pr}/comments" --paginate \
  --jq "[.[] | select(.body | startswith(\"${marker}\"))] | last // empty")

if [ -n "$existing" ]; then
  # Same head and same base as last time: nothing has moved, stay quiet.
  if printf '%s' "$existing" | jq -e --arg s "$stamp" '.body | contains($s)' >/dev/null; then
    echo "PR #${pr}: conflict unchanged since last run, no comment posted."
    exit 0
  fi
  comment_id=$(printf '%s' "$existing" | jq -r '.id')
  gh api --method PATCH "repos/${GITHUB_REPOSITORY}/issues/comments/${comment_id}" \
    -f body="$body" >/dev/null
  echo "PR #${pr}: updated existing conflict comment."
else
  gh api --method POST "repos/${GITHUB_REPOSITORY}/issues/${pr}/comments" \
    -f body="$body" >/dev/null
  echo "PR #${pr}: posted conflict comment."
fi
