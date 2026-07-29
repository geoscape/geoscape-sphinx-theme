#!/usr/bin/env bash
#
# test-propagation.sh — LOCAL pre-flight check for theme propagation.
#
# Simulates what Read the Docs does when a consumer repo builds: a fresh venv,
# `pip install` of the consumer's docs/requirements.txt (which pulls the theme
# from its git tag), then a Sphinx build with RTD's `singlehtml` builder.
#
# This is READ-ONLY with respect to git: it never checks out, commits, pushes,
# or touches any branch or remote. It only builds into a throwaway temp dir.
# It is NOT a deploy to GitHub or RTD — it just tells you, in ~30s, whether a
# theme change will render correctly once you DO push + rebuild.
#
# Usage:
#   scripts/test-propagation.sh <consumer-repo-path> [builder]
#
#   <consumer-repo-path>  path to a docs repo (must have docs/source/conf.py
#                         and docs/requirements.txt)
#   [builder]             sphinx builder to use; default "singlehtml" (what RTD
#                         uses for these repos). Pass "html" for the desktop build.
#
# Examples:
#   scripts/test-propagation.sh /Users/angelicas/Code/geo-docs/docs_buildings_guide
#   scripts/test-propagation.sh ../docs_buildings_release html
#
set -euo pipefail

# --- args -------------------------------------------------------------------
CONSUMER="${1:-}"
BUILDER="${2:-singlehtml}"

if [[ -z "$CONSUMER" ]]; then
  echo "usage: $0 <consumer-repo-path> [builder]" >&2
  exit 2
fi
if [[ ! -f "$CONSUMER/docs/source/conf.py" ]]; then
  echo "error: $CONSUMER/docs/source/conf.py not found — not a Sphinx docs repo?" >&2
  exit 2
fi
if [[ ! -f "$CONSUMER/docs/requirements.txt" ]]; then
  echo "error: $CONSUMER/docs/requirements.txt not found" >&2
  exit 2
fi

# Prefer python3.13 (closest local match to RTD's 3.11 → Sphinx 9 / alabaster 1.0).
PYBIN="$(command -v python3.13 || command -v python3)"
CONSUMER_NAME="$(basename "$CONSUMER")"

echo "=== test-propagation ======================================================"
echo "consumer : $CONSUMER_NAME"
echo "builder  : $BUILDER"
echo "python   : $PYBIN ($($PYBIN --version 2>&1))"
echo "theme req: $(grep -i geoscape-sphinx-theme "$CONSUMER/docs/requirements.txt" || echo '(none — repo not migrated!)')"
echo "==========================================================================="

# --- throwaway venv + build dir --------------------------------------------
VENV="$(mktemp -d)/venv"
OUT="$(mktemp -d)/out"
cleanup() { rm -rf "$VENV" "$OUT" 2>/dev/null || true; }
trap cleanup EXIT

echo "[1/3] creating fresh venv ..."
"$PYBIN" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip

echo "[2/3] installing consumer requirements (--no-cache-dir, like RTD) ..."
# --no-cache-dir forces a real re-fetch of the theme tag, so a moved tag /
# bumped version is exercised exactly as RTD would.
"$VENV/bin/pip" install --quiet --no-cache-dir -r "$CONSUMER/docs/requirements.txt"

# Report exactly which theme version+commit landed — this is the propagation proof.
echo "    installed theme:"
"$VENV/bin/pip" show geoscape-sphinx-theme 2>/dev/null | grep -E "^(Name|Version)" | sed 's/^/      /' \
  || { echo "      ERROR: geoscape-sphinx-theme not installed (is it in requirements.txt?)" >&2; exit 1; }

echo "[3/3] building '$BUILDER' ..."
if ! "$VENV/bin/sphinx-build" -b "$BUILDER" -q "$CONSUMER/docs/source" "$OUT" 2>build_warnings.log; then
  echo "      BUILD FAILED — see build_warnings.log" >&2
  tail -20 build_warnings.log >&2
  exit 1
fi

# --- render checks: did the CUSTOM theme actually take effect? --------------
INDEX="$OUT/index.html"
pass=0; fail=0
check() { # <label> <grep-pattern> <expected: yes|no>
  if grep -q "$2" "$INDEX" 2>/dev/null; then found=yes; else found=no; fi
  if [[ "$found" == "$3" ]]; then echo "      ✓ $1"; pass=$((pass+1))
  else echo "      ✗ $1 (expected $3, got $found)"; fail=$((fail+1)); fi
}

echo "    render checks (against $INDEX):"
check "geoscape.css linked"          "geoscape.css"        yes
check "custom sidebar nav present"   "gs-nav__global"      yes
if [[ "$BUILDER" != "singlehtml" ]]; then
  # search box is intentionally suppressed under singlehtml, so only assert on html
  check "custom search box present"  "gs-search-section"   yes
  check "no default 'Go' search box" 'value="Go"'          no
fi

echo "==========================================================================="
if [[ $fail -eq 0 ]]; then
  echo "RESULT: PASS — theme propagated & rendered ($pass checks). Safe to push + rebuild on RTD."
  exit 0
else
  echo "RESULT: FAIL — $fail check(s) failed. Do NOT rely on RTD picking this up; investigate first."
  exit 1
fi
