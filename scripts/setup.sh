#!/usr/bin/env bash
# Create .venv with a SUPPORTED interpreter and install the pinned requirements.
# Tested interpreters: Python 3.11 and 3.12. Newer versions (3.13, 3.14) are refused on
# purpose: numpy 2.0.2 / scikit-learn 1.6.1 have no wheels there and pip would try to
# compile them from source. Viewing the dashboard needs no Python at all:
#   open dashboard/decision-dashboard.html
set -euo pipefail
cd "$(dirname "$0")/.."

pick=""
for cand in "${PYTHON:-}" python3.12 python3.11 python3; do
  [ -z "$cand" ] && continue
  command -v "$cand" >/dev/null 2>&1 || continue
  ver="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  case "$ver" in
    3.11|3.12) pick="$cand"; break ;;
    *) echo "skip: $cand is Python $ver (supported: 3.11, 3.12)" ;;
  esac
done

if [ -z "$pick" ]; then
  cat <<'MSG'

No supported Python found (need 3.11 or 3.12).
  * To just view the work: open dashboard/decision-dashboard.html in any browser.
  * To run the pipeline on macOS:  brew install python@3.12   (or: uv python install 3.12)
    then:  PYTHON=python3.12 scripts/setup.sh

MSG
  exit 2
fi

echo "using $pick ($("$pick" --version))"
"$pick" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
if [ "${WITH_DEV:-1}" = "1" ]; then
  .venv/bin/python -m pip install --quiet -r requirements-dev.txt
fi
echo "ok: .venv ready. Next: make sample   (or: make test)"
