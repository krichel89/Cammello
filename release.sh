#!/usr/bin/env bash
set -euo pipefail

VERSION="0.11.1"
REPO_DIR="/Users/h/Documents/Python/Cammello"

cd "$REPO_DIR"

git add -A
git commit -m "Release v${VERSION}"
git tag -a "v${VERSION}" -m "v${VERSION}"
git push origin main
git push origin "v${VERSION}"

gh release create "v${VERSION}" \
  --title "v${VERSION}" \
  --notes-file notes_0111.md
