#!/usr/bin/env bash
# Diagnose + Aufraeumen VOR einem erneuten release.sh.
# Aufruf:  bash cleanup_and_check.sh
set -eu
REPO_DIR="/Users/h/Documents/Python/Cammello"
VERSION="0.11.1"
cd "$REPO_DIR"

echo "=== 1. Version im Code (soll 0.11.1 sein) ==="
grep "__version__" cammello/constants.py | head -1

echo "=== 2. Liegen die neuen Dateien im Repo? ==="
git status --short
if [ -z "$(git status --porcelain)" ]; then
  echo ">>> WARNUNG: Keine Aenderungen. Die Dateien aus dem Zip sind NICHT"
  echo ">>> im Repo gelandet - erst kopieren, dann release.sh."
fi

echo "=== 3. Existiert Tag/Release v${VERSION} schon (vom letzten Versuch)? ==="
if git rev-parse "v${VERSION}" >/dev/null 2>&1; then
  echo "Tag v${VERSION} existiert lokal - wird geloescht:"
  git tag -d "v${VERSION}"
fi
git push origin ":refs/tags/v${VERSION}" 2>/dev/null && \
  echo "Remote-Tag geloescht." || echo "Kein Remote-Tag (ok)."
gh release delete "v${VERSION}" --yes 2>/dev/null && \
  echo "Release geloescht." || echo "Kein Release (ok)."

echo "=== Fertig. Wenn oben Aenderungen standen: jetzt  ./release.sh  ==="
