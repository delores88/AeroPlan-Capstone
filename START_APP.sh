#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python launch.py "$@"
fi
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'Python 3.10+ is required. Install it using your operating system package manager or Python.org.' >&2
  exit 1
fi
exec python3 launch.py "$@"
