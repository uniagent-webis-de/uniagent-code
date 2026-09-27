#!/usr/bin/env bash
# Runs near-duplicate detection on the 'hessian-law-de' corpus.
# See detect-near-duplicates.sh for configuration options (env variables)
# and background/runtime notes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/detect-near-duplicates.sh" "hessian-law-de"
