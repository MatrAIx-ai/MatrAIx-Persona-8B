#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/verifier_env.sh"

# Runs the verifier module rather than pytest: structured_output.json is written by
# test_state.py's main(), which a bare `pytest` invocation never calls.
#
# The command sits in the `if` condition because commands there are exempt from
# `set -e`, so the reward file is written on both paths rather than skipped when the
# verifier fails.
if python3 "${TESTS_DIR}/test_state.py"; then
  echo 1 > "${VERIFIER_DIR}/reward.txt"
else
  echo 0 > "${VERIFIER_DIR}/reward.txt"
  exit 1
fi
