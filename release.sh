#!/usr/bin/env bash
set -euo pipefail

VERSION="0.18.28"
NOTES_FILE="notes_01828.md"
REPO_URL="https://github.com/krichel89/Cammello"

# 30.09.2026: the repo is the folder this script lives in - on the Mac as on
# Windows (Git Bash). The old fixed Mac path made the script die silently on
# Windows: "cd" failed, set -e ended the run, the window closed.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Every failure is reported with its line, never silently.
trap 'echo; echo "FEHLER in release.sh, Zeile ${LINENO}: ${BASH_COMMAND}" >&2' ERR

cd "$REPO_DIR"
echo "== Cammello release v${VERSION}"
echo "   Ordner: ${REPO_DIR}"

# --- Preconditions: stop with a clear sentence before anything is changed ----
command -v git >/dev/null 2>&1 || { echo "FEHLER: git nicht gefunden." >&2; exit 1; }
command -v gh >/dev/null 2>&1 || {
  echo "FEHLER: GitHub-CLI 'gh' nicht gefunden." >&2
  echo "        Mac: brew install gh   Windows: winget install GitHub.cli" >&2
  echo "        danach einmalig: gh auth login" >&2
  exit 1; }
gh auth status >/dev/null 2>&1 || {
  echo "FEHLER: 'gh' ist nicht angemeldet. Einmalig: gh auth login" >&2; exit 1; }
[ -f "$NOTES_FILE" ] || { echo "FEHLER: ${NOTES_FILE} fehlt - Zip eingespielt?" >&2; exit 1; }
grep -q "__version__ = '${VERSION}'" cammello/constants.py || {
  echo "FEHLER: cammello/constants.py steht nicht auf ${VERSION} - Zip eingespielt?" >&2; exit 1; }
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[ "$BRANCH" = "main" ] || { echo "FEHLER: Du bist auf Branch '${BRANCH}', nicht auf main." >&2; exit 1; }
if git ls-remote --exit-code --tags origin "refs/tags/v${VERSION}" >/dev/null 2>&1; then
  echo "FEHLER: Tag v${VERSION} gibt es auf GitHub schon - Version bereits released." >&2
  exit 1
fi
echo "   Voraussetzungen ok (git, gh angemeldet, main, Version ${VERSION})."

echo "== 1/4 Commit"
git add -A
# 0.17.1: nach einem halb durchgelaufenen Versuch ist schon alles
# committet; ohne dieses "oder" bricht set -e hier ab und das Skript
# kommt nie zum Taggen.
git commit -m "Release v${VERSION}" || echo "Nichts zu committen - weiter."
echo "== 2/4 Tag v${VERSION}"
# A local tag from an earlier, aborted run is replaced (it was never pushed -
# the remote check above guarantees that).
git tag -d "v${VERSION}" >/dev/null 2>&1 || true
git tag -a "v${VERSION}" -m "v${VERSION}"
echo "== 3/4 Push"
git push origin main
git push origin "v${VERSION}"

# Keep the release body to a short REFERENCE (a couple of links) so the
# download assets stay as close to the top of the release page as possible -
# GitHub renders the notes body ABOVE the "Assets" section, so a full notes
# text pushes the binaries down. The detailed notes live in the repo at the
# tag (${NOTES_FILE}) and in the changelog.
echo "== 4/4 GitHub-Release (startet die Builds in GitHub Actions)"
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
    # 2) Add the new version as preferred (date + reference URL, see
    #    template) - but ONLY if it is not recorded yet. Without this guard a
    #    RE-RUN at the same version (e.g. after a failed platform build, as
    #    with the Windows job of 0.16.1) creates a SECOND, identical P348
    #    statement. Step 1 above cannot catch that: it deliberately skips
    #    the current version so it does not demote what it just promoted.
    if wd data "$QID" --props claims \
         | jq -e --arg v "$VERSION" \
             '.claims.P348[]? | select(.mainsnak.datavalue.value == $v)' \
             >/dev/null; then
      echo "NOTE: Wikidata already lists version ${VERSION} - not adding it again."
    else
      wd edit-entity ./wikidata_version.js "$QID" "$VERSION" "$URL" \
        --summary "add software version ${VERSION}"
    fi
  } || echo "WARNING: Wikidata P348 update failed - run it manually (see release.sh)."
else
  echo "NOTE: wikibase-cli (wd) not installed - skipping Wikidata P348 update."
  echo "      npm install -g wikibase-cli && wd config credentials https://www.wikidata.org"
fi

echo
echo "FERTIG: v${VERSION} ist released."
echo "Builds: ${REPO_URL}/actions"
