#!/usr/bin/env bash
# Usage: scripts/build_site_from_spec.sh <design-spec.json> [template-dir]
#
# Drops a design spec into the BUILD site template and builds it. Leaves the
# template's working tree changed on purpose so you can `npm run dev` and look;
# `git checkout -- content app/globals.css` in the template restores the demo.
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 <design-spec.json> [template-dir]" >&2
  exit 2
fi
spec="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
dir="${2:-$(cd "$(dirname "$0")/../.." && pwd)/../BUILD_TEMPLATE_REPO}"
cd "$dir"

rm -f content/content.json content/seo.json
cp "$spec" content/design-spec.json
npm run content:scaffold
npm run tokens:apply
npm run lint
npm run typecheck
npm run check:tokens
npm run build   # not `npm test`: the template's unit tests hardcode the demo section ids
echo "built from $spec in $(pwd)"
