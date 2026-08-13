# Shared host/docker verifier path resolution (sourced from test.sh).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRIAL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IS_HOST_SNAPSHOT=0
case "${SCRIPT_DIR}" in
  */host_tests) IS_HOST_SNAPSHOT=1 ;;
esac

if [ "${IS_HOST_SNAPSHOT}" -eq 1 ]; then
  TESTS_DIR="${SCRIPT_DIR}"
  VERIFIER_DIR="${TRIAL_ROOT}/verifier"
else
  TESTS_DIR="${HARBOR_TESTS_DIR:-/tests}"
  if [ ! -f "${TESTS_DIR}/test_state.py" ] && [ -f "${SCRIPT_DIR}/test_state.py" ]; then
    TESTS_DIR="${SCRIPT_DIR}"
  fi
  VERIFIER_DIR="${HARBOR_VERIFIER_DIR:-/logs/verifier}"
  if ! mkdir -p "${VERIFIER_DIR}" 2>/dev/null; then
    VERIFIER_DIR="${TRIAL_ROOT}/verifier"
  fi
fi
mkdir -p "${VERIFIER_DIR}"
