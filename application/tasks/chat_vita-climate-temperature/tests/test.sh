#!/bin/bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/verifier_env.sh"

uvx \
  --with pydantic==2.12.5 \
  --with pytest==8.4.1 \
  --with pytest-json-ctrf==0.3.5 \
  pytest --ctrf "${VERIFIER_DIR}/ctrf.json" "${TESTS_DIR}/test_state.py" -rA

echo 1 > "${VERIFIER_DIR}/reward.txt"
