#!/usr/bin/env bash
set -euo pipefail

VERSION="0.12.0"
REPO_DIR="/Users/h/Documents/Python/Cammello"

cd "$REPO_DIR"

git add -A
git commit -m "Release v${VERSION}"
git tag -a "v${VERSION}" -m "v${VERSION}"
git push origin main
git push origin "v${VERSION}"

gh release create "v${VERSION}" \
  --title "v${VERSION}" \
  --notes-file notes_0120.md




# --- Wikidata: neue Version als P348 eintragen ------------------------------
QID="Q140509313"
URL="https://github.com/krichel89/Cammello/releases/tag/v${VERSION}"
OLD_RANK="normal"   # bisherige Versionen; die neue wird "preferred"

# 1) Alle bestehenden Versions-Statements AUSSER der neuen herabstufen.
#    (select != $VERSION verhindert, dass ein erneuter Lauf die gerade
#     bevorzugte Version wieder herunterstuft.)
wd data "$QID" --props claims \
  | jq -r --arg v "$VERSION" \
      '.claims.P348[]? | select(.mainsnak.datavalue.value != $v) | .id' \
  | while read -r guid; do
      [ -n "$guid" ] && wd update-claim "$guid" --rank "$OLD_RANK" \
        --summary "demote superseded software version"
    done

# 2) Neue Version als bevorzugt hinzufuegen (Datum + Referenz-URL, siehe Template)
wd edit-entity ./wikidata_version.js "$QID" "$VERSION" "$URL" \
  --summary "add software version ${VERSION}"
