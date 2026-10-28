#!/usr/bin/env bash
# V13: fail if anything looking like an API key appears in tracked files.
# Usage: check_no_secrets.sh [extra_dir] — extra dirs are scanned ad hoc only.
set -euo pipefail
targets="$(git ls-files 2>/dev/null || true)"
extra="${1:-}"
if [ -n "$extra" ]; then targets="$targets $extra"; fi
pattern='sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{10,}|MODEL_API_KEY\s*=\s*['\''"][^'\''"]+['\''"]|META_API_KEY\s*=\s*['\''"][^'\''"]+['\''"]'
hits=""
scan_file() {
  case "$1" in *.zip|*.png|*.jpg|*.mp4|.venv/*) return 1;; esac
  grep -InE "$pattern" "$1" >/dev/null 2>&1
}
for t in $targets; do
  if [ -d "$t" ]; then
    found="$(grep -rInE --exclude-dir=.venv "$pattern" "$t" 2>/dev/null || true)"
    [ -n "$found" ] && hits="$hits $found"
  elif [ -f "$t" ]; then
    if scan_file "$t"; then hits="$hits $t"; fi
  fi
done
if [ -n "$hits" ]; then echo "secrets found in:$hits"; exit 1; fi
echo "no secrets found"
