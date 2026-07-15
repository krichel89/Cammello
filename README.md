# Cammello

Batch upload tool for Wikimedia Commons with full Structured Data on Commons
(SDC) support: captions, creator (P170), copyright status (P6216), license
(P275), depicts (P180), and created-during (P10408).

Cammello is a single-file PyQt5 desktop application aimed at photographers
who upload many related files at once (e.g. a full press-photography session
from a film festival) and want SDC statements set consistently on every file
without post-processing each one on the wiki.

## Highlights

- **Upload settings** hold the metadata that applies to every file in the
  batch: author + creator (P170), source, permission, license text +
  license (P275), copyright (P6216), other templates and fields, gallery
  prefix. The Wikidata QID fields are highlighted in light blue and only
  accept `Q` followed by digits; copyright defaults to Q73566113 (CC-
  licensed) and license to Q18199165 (CC BY-SA 4.0).
- **Base description** shared by every file in the batch: depicts (P180),
  created-during (P10408), categories, gallery suffix, and any extra
  wikitext or templates.
- **Per-file description** for anything that varies from file to file:
  captions in any languages, per-file depicts, per-file categories, extra
  wikitext.
- **Wikidata name search**: on the Creator, Depicts and Created-during fields
  you can type a name (e.g. "Harald Krichel") and pick from a live suggestion
  list showing label, description and QID; selecting inserts the QID. These
  fields are validated to contain real QIDs before upload.
- **Bulk edit**: select several rows and set one field (Depicts, Categories,
  Caption en/de or Date) for all of them at once.
- **Two editing modes**: structured single-line fields (default) or raw
  `description_all` text (expert mode).
- **Drag and drop** image files (or a folder of image files) onto the
  table; multiple files at once are supported, and unsupported entries in
  a mixed drop are silently skipped instead of aborting the whole drop.
- **Settings** (upload defaults, base description, optionally the current
  file's description) can be exported to and imported from a plain text
  file.

## Installation

Requires Python 3.11 or 3.12.

```
pip install PyQt5 requests Pillow
python Cammello.py
```

To build a standalone executable:

```
python -m PyInstaller --onefile --windowed --name Cammello Cammello.py
```

## Login

Cammello uses a MediaWiki BotPassword. Create one at
[Special:BotPasswords](https://commons.wikimedia.org/wiki/Special:BotPasswords)
with the grants required for uploads and structured-data edits (High-volume
editing, Upload new files, Edit existing pages, Edit Wikibase). The username
in the login dialog has the form `YourName@BotName`.

## The `description_all` format

Each row in the table has a per-file description. When the batch is uploaded,
its content is prepended with the base description (which applies to every
file), plus the `creator=…`, `copyright=…`, `license=…` lines taken from
the corresponding Wikidata QID fields in Upload settings. The resulting text
is a mix of `key=value` lines (which drive SDC statements) and free
wikitext:

```
caption_en=Harald Krichel at the Berlinale 2026
caption_de=Harald Krichel auf der Berlinale 2026
creator=Q640
copyright=Q73566113
license=Q18199165
depicts=Q42; Q64
created_during=Q124692383
gallery_suffix=Berlinale 2026

{{en|1=Harald Krichel at the Berlinale 2026}}
[[Category:Harald Krichel]]
```

- `caption_XX=…` sets the SDC caption in language `XX`.
- `creator`, `copyright`, `license`, `depicts`, `created_during` become
  Wikidata-item SDC statements (P170, P6216, P275, P180, P10408). `depicts`
  accepts a semicolon-separated list; `,` is still tolerated for older data.
- `gallery_suffix` is appended to the base gallery path (if any) so that all
  files with the same suffix land in the same gallery page.
- Lines starting with `#` are treated as comments and stripped before upload.
- Everything else (templates, category links, plain wikitext) is passed
  through unchanged into the file's wiki page.

The per-file editor only offers the fields that legitimately vary from file
to file: captions, depicts, categories, and extra wikitext. Everything else
lives in the base description or in Upload settings.

## License

CC0.

## macOS note

The `pyexiv2` wheel links against Homebrew libraries. If `import pyexiv2` fails with `Library not loaded: /opt/homebrew/...`, run `brew install exiv2` (pulls brotli, gettext and friends). Without pyexiv2 the IPTC and Culling tabs are hidden; the MediaWiki side works regardless.

## UI language

The interface is available in English, Deutsch, Español, Français and
Italiano. Pick one under **Settings → Language**; the change takes effect
after a restart (it is stored as `ui_language` in QSettings). On the first
start the system locale decides if it is one of the five, otherwise English
is used. Log messages stay English on purpose, so a log file remains readable
when reporting an issue.

Adding a string: wrap it in `tr('…')` (English text = the key) and add an
entry to `TRANSLATIONS` in `cammello/i18n.py`. `test_i18n.py` fails if a key
is missing, a language is incomplete, or a `{placeholder}` was lost in
translation.

## Mandatory depicts & category suggestions

depicts (P180) is mandatory for the MediaWiki upload: every file needs a QID,
or one of the three override checkboxes under the depicts field ("No Wikidata
item", "Not applicable", "Unidentified"). In a WikiPortraits context (a
{{WikiPortraits ...}} template or a WikiPortraits category) the override adds
the matching maintenance category automatically.

The "Suggest" button next to the per-file categories fills in Commons
categories derived from the depicts entries and the "created during" event
(Wikidata P373, label as fallback); an event without a year in its name gets
the year from the Date column appended.

## FTP / Flickr

FTP and Flickr share one tab: the file list on the left and the status area
serve both services. The Flickr part uploads the files from the table (selection, or all) to your
Flickr account; the Culling tab gets a `-> Flickr` send target. One-time
setup: create an API key/secret at flickr.com/services/apps/create, enter
both on the Flickr tab (or the Settings mirror), then run the two
authorization steps (browser opens, paste the verification code). Files are
uploaded as they are; the Flickr title is the target filename; privacy
follows your account's upload defaults. A license picked in the upload group
(CC BY-SA, CC0, Public Domain Mark, ...) is applied per photo right after
the upload - 'Account default' leaves your Flickr setting untouched.

The IPTC tab is hidden in the release default; start once with
`--enable-tab iptc` to bring it back (the choice persists).

## Application icon

Drop `icon.png` into `cammello/assets/` for the runtime window/Dock icon and
the About tab logo. A real macOS Finder icon needs an app bundle
(PyInstaller with `--icon cammello/assets/icon.icns`).

## Hidden per-tab switches

The Culling, IPTC and FTP tabs can be switched off individually (including
their references elsewhere: the Settings-tab sections, the Culling "-> FTP"
button, the FTP tab's IPTC-driven upload button). There is no UI for this;
flip a switch once from the command line and it is persisted:

```bash
python Cammello.py --disable-tab ftp      # names: culling, iptc, ftp
python Cammello.py --enable-tab ftp
```

The app then starts normally; the flags live in QSettings as
`feature_culling` / `feature_iptc` / `feature_ftp` / `feature_flickr` (default: on). A missing
pyexiv2 still disables all three regardless of the flags.
