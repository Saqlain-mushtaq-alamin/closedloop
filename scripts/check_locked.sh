#!/usr/bin/env bash
# H6: verify locked files against LOCKED_HASHES.txt (stub until Phase 01 locks them).
set -euo pipefail
if [ ! -f LOCKED_HASHES.txt ]; then
  echo "locked check: LOCKED_HASHES.txt not present yet (pre-Phase-01 stub); PASS"
  exit 0
fi
sha256sum -c LOCKED_HASHES.txt
