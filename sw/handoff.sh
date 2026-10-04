#!/bin/sh
# Make a handoff bundle, name it by the project's convention, and test that it
# can be received. Written after prompt 07-git-handoff, which records a project
# that handed over bundles for 368 iterations before anyone tried to pull one.
#
#   NAME: oisc-vs-accumulator-claude-iter<commits>-<UTC yyyymmdd-hhmmss>.bundle
#
# The iteration number is the commit count, so a folder of these sorts into the
# order they were made and each says which state it carries. The refs are named
# explicitly rather than relying on --all: HEAD must be in the bundle or
# `git pull FILE` has nothing to ask for, and whether --all supplies it has
# varied between git versions.
#
# Usage: sh sw/handoff.sh [output-directory]
set -e

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUTDIR=${1:-/mnt/user-data/outputs}
cd "$ROOT"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
ITER=$(git rev-list --count HEAD)
STAMP=$(date -u +%Y%m%d-%H%M%S)
NAME="oisc-vs-accumulator-claude-iter${ITER}-${STAMP}.bundle"
OUT="$OUTDIR/$NAME"

if [ -n "$(git status --porcelain)" ]; then
    echo "refusing: working tree is dirty, commit first" >&2
    git status --short >&2
    exit 1
fi

mkdir -p "$OUTDIR"
# HEAD first, then the branch, then every tag
git bundle create "$OUT" HEAD "$BRANCH" --tags >/dev/null 2>&1

echo "wrote $NAME"
echo
echo "contains:"
git bundle list-heads "$OUT" | sed 's/^/  /'
echo

# --- the deliverable is the one thing nobody tests, so test it ---
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

git bundle verify "$OUT" >/dev/null 2>&1 || { echo "FAIL: bundle does not verify" >&2; exit 1; }

git clone -q "$OUT" "$TMP/clone"
[ "$(git rev-parse HEAD)" = "$(git -C "$TMP/clone" rev-parse HEAD)" ] \
    || { echo "FAIL: clone HEAD differs" >&2; exit 1; }

# a clone can succeed on a bundle that `git pull` cannot use; check both
git ls-remote "$OUT" 2>/dev/null | grep -q '[[:space:]]HEAD$' \
    || { echo "FAIL: no HEAD in bundle; git pull would have nothing to ask for" >&2; exit 1; }

git init -q "$TMP/pull"
git -C "$TMP/pull" fetch -q "$OUT" HEAD
[ "$(git rev-parse HEAD)" = "$(git -C "$TMP/pull" rev-parse FETCH_HEAD)" ] \
    || { echo "FAIL: fetch gave a different commit" >&2; exit 1; }

N=$(git -C "$TMP/clone" rev-list --count HEAD)
echo "checks: verifies, clones to $(git rev-parse --short HEAD), $N commits, HEAD present, fetch matches"
echo "$OUT"
