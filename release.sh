#!/usr/bin/env bash
set -euo pipefail

VERSION="0.13.0"
NOTES_FILE="notes_0130.md"
REPO_DIR="/Users/h/Documents/Python/Cammello"
REPO_URL="https://github.com/krichel89/Cammello"

cd "$REPO_DIR"

git add -A
git commit -m "Release v${VERSION}"
git tag -a "v${VERSION}" -m "v${VERSION}"
git push origin main
git push origin "v${VERSION}"

# Keep the release body to a short REFERENCE (a couple of links) so the
# download assets stay as close to the top of the release page as possible -
# GitHub renders the notes body ABOVE the "Assets" section, so a full notes
# text pushes the binaries down. The detailed notes live in the repo at the
# tag (${NOTES_FILE}) and in the changelog.
gh release create "v${VERSION}" \
  --title "v${VERSION}" \
  --notes "📄 Release notes: [${NOTES_FILE}](${REPO_URL}/blob/v${VERSION}/${NOTES_FILE})  ·  Full changelog: [CHANGELOG.md](${REPO_URL}/blob/v${VERSION}/CHANGELOG.md)"

# --- Wikidata: register the new version as P348 -----------------------------
QID="Q140509313"
URL="https://github.com/krichel89/Cammello/releases/tag/v${VERSION}"
OLD_RANK="normal"   # existing versions; the new one becomes "preferred"
# Wrapped so a Wikidata hiccup (or a missing wikibase-cli) never aborts the
# already-published release - remove the "if"/"|| echo" wrapper for a strict
# run. One-time setup: npm install -g wikibase-cli &&
#                      wd config credentials https://www.wikidata.org
if command -v wd >/dev/null 2>&1; then
  {
    # 1) Demote all existing version statements EXCEPT the new one.
    #    (select != $VERSION keeps a re-run from demoting the version it just
    #     promoted.)
    wd data "$QID" --props claims \
      | jq -r --arg v "$VERSION" \
          '.claims.P348[]? | select(.mainsnak.datavalue.value != $v) | .id' \
      | while read -r guid; do
          [ -n "$guid" ] && wd update-claim "$guid" --rank "$OLD_RANK" \
            --summary "demote superseded software version"
        done
    # 2) Add the new version as preferred (date + reference URL, see template).
    wd edit-entity ./wikidata_version.js "$QID" "$VERSION" "$URL" \
      --summary "add software version ${VERSION}"
  } || echo "WARNING: Wikidata P348 update failed - run it manually (see release.sh)."
else
  echo "NOTE: wikibase-cli (wd) not installed - skipping Wikidata P348 update."
  echo "      npm install -g wikibase-cli && wd config credentials https://www.wikidata.org"
fi
