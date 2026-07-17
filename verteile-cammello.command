#!/bin/bash
#
# verteile-cammello.command  —  Cammello-Auslieferung aus einer ZIP ins Repo
#
# Doppelklick (oder im Terminal ausfuehren). Nimmt eine ZIP aus Claude und
# legt jede Datei an ihren richtigen Platz im Cammello-Repo:
#   cammello/foo.py            -> <repo>/cammello/foo.py
#   requirements.txt           -> <repo>/requirements.txt
#   .github/workflows/build.yml-> <repo>/.github/workflows/build.yml
#   notes_XXXX.md, CHANGELOG.md, release.sh, Cammello.py -> <repo>/
#
# Die ZIP muss die Dateien in repo-relativer Struktur enthalten (so werden
# sie geliefert). Ein umschliessender Ordner (z. B. "outputs/") wird
# automatisch erkannt und uebersprungen.
#
# Es wird NICHTS geloescht - nur ueberschrieben/hinzugefuegt. Vor dem Kopieren
# gibt es eine Vorschau und eine Rueckfrage.
#
set -euo pipefail

# ── Konfiguration ────────────────────────────────────────────────────────────
# Repo-Pfad: per Umgebungsvariable CAMMELLO_REPO ueberschreibbar, sonst Default.
REPO="${CAMMELLO_REPO:-/Users/h/Documents/Python/Cammello}"
DOWNLOADS="${HOME}/Downloads"

# Verzeichnisnamen, die ECHTER Repo-Inhalt sind und daher NIE als umschliessender
# Wrapper-Ordner abgestreift werden duerfen.
REPO_TOPDIRS=("cammello" ".github")

say()  { printf '%s\n' "$*"; }
err()  { printf 'FEHLER: %s\n' "$*" >&2; }
die()  { err "$*"; say ""; read -r -p "Enter zum Schliessen…" _; exit 1; }

# ── ZIP bestimmen ────────────────────────────────────────────────────────────
# 1. Argument, sonst 2. neueste *.zip in ~/Downloads.
ZIP="${1:-}"
if [[ -z "${ZIP}" ]]; then
    ZIP="$(ls -t "${DOWNLOADS}"/*.zip 2>/dev/null | head -1 || true)"
    [[ -n "${ZIP}" ]] || die "Keine ZIP angegeben und keine *.zip in ${DOWNLOADS} gefunden."
    say "Neueste ZIP in Downloads gewaehlt:"
fi
[[ -f "${ZIP}" ]] || die "ZIP nicht gefunden: ${ZIP}"
[[ -d "${REPO}/.git" ]] || die "Kein Git-Repo unter: ${REPO}
Setze bei Bedarf CAMMELLO_REPO=/pfad/zum/repo."

say "  ZIP : ${ZIP}"
say "  Repo: ${REPO}"
say ""

# ── ZIP in ein temporaeres Verzeichnis entpacken ─────────────────────────────
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
unzip -q "${ZIP}" -d "${TMP}"

# macOS-Muell entfernen, der sonst als Wrapper-Ordner missverstanden wird.
rm -rf "${TMP}/__MACOSX" 2>/dev/null || true

# ── Umschliessenden Wrapper-Ordner abstreifen ────────────────────────────────
# Solange die Ebene genau EINEN Eintrag hat, der ein Verzeichnis ist UND nicht
# zu den echten Repo-Top-Ordnern gehoert, eine Ebene tiefer gehen.
SRC="${TMP}"
while true; do
    # sichtbare Eintraege zaehlen (ohne . und ..)
    shopt -s nullglob dotglob
    entries=( "${SRC}"/* )
    shopt -u nullglob dotglob
    [[ ${#entries[@]} -eq 1 ]] || break
    only="${entries[0]}"
    [[ -d "${only}" ]] || break
    base="$(basename "${only}")"
    is_repo_dir=false
    for d in "${REPO_TOPDIRS[@]}"; do
        [[ "${base}" == "${d}" ]] && is_repo_dir=true && break
    done
    ${is_repo_dir} && break        # echter Inhalt, nicht abstreifen
    SRC="${only}"                  # Wrapper -> eine Ebene tiefer
done

# ── Zu kopierende Dateien einsammeln ─────────────────────────────────────────
# Relativpfade unterhalb von SRC; .DS_Store und __MACOSX ausklammern.
FILES=()
while IFS= read -r -d '' f; do
    rel="${f#"${SRC}"/}"
    case "${rel}" in
        *.DS_Store|__MACOSX/*) continue ;;
    esac
    FILES+=( "${rel}" )
done < <(find "${SRC}" -type f -print0)

[[ ${#FILES[@]} -gt 0 ]] || die "Die ZIP enthaelt keine Dateien."

# ── Vorschau ─────────────────────────────────────────────────────────────────
say "Folgende Dateien werden ins Repo gelegt:"
say ""
NEW=0; OVER=0
for rel in "${FILES[@]}"; do
    if [[ -e "${REPO}/${rel}" ]]; then
        tag="[ueberschreiben]"; OVER=$((OVER+1))
    else
        tag="[neu]         "; NEW=$((NEW+1))
    fi
    printf '  %s %s\n' "${tag}" "${rel}"
done
say ""
say "  ${NEW} neu, ${OVER} werden ueberschrieben."
say ""
read -r -p "Kopieren? [j/N] " ans
case "${ans}" in
    j|J|y|Y) ;;
    *) say "Abgebrochen. Nichts geaendert."; read -r -p "Enter zum Schliessen…" _; exit 0 ;;
esac

# ── Kopieren (Struktur anlegen, Datei fuer Datei) ────────────────────────────
for rel in "${FILES[@]}"; do
    dest="${REPO}/${rel}"
    mkdir -p "$(dirname "${dest}")"
    cp -f "${SRC}/${rel}" "${dest}"
    printf '  -> %s\n' "${rel}"
done

say ""
say "Fertig. ${#FILES[@]} Datei(en) verteilt."
say ""
say "Naechster Schritt im Repo:"
say "  cd \"${REPO}\""
say "  git status        # pruefen, was sich geaendert hat"
say ""
read -r -p "Enter zum Schliessen…" _
